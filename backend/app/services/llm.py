"""
Unified LLM client supporting two providers:

  1. Groq Cloud (PRIMARY when GROQ_API_KEY is set in .env)
     - Uses OpenAI-compatible /chat/completions endpoint
     - 50-200x faster than local Ollama on CPU (tokens/sec in hundreds)
     - Free tier at https://console.groq.com

  2. Ollama (LOCAL FALLBACK when Groq key is absent or API fails)
     - Runs llama3.2:3b (or whichever model is configured) locally
     - No internet required; private/offline mode

Both providers support streaming so the user sees tokens appear in real time.
Legal answers are grounded in retrieved context; general questions use a
separate assistant prompt without legal-document context.
"""
import json
import logging
import time
from typing import List, Dict, Optional, AsyncGenerator
import httpx
import requests
from app.config import settings
from app.prompts.system_prompt import (
    BASE_SYSTEM_PROMPT, GENERAL_SYSTEM_PROMPT, CLARIFICATION_PROMPT,
    NOT_FOUND_PROMPT, NO_CONTEXT_PROMPT
)

logger = logging.getLogger("doj_rag.llm")


class OllamaUnavailableError(Exception):
    pass


class GroqUnavailableError(Exception):
    pass


class LLMUnavailableError(Exception):
    """Raised when ALL configured LLM providers fail."""
    pass


# ─── Message Building ─────────────────────────────────────────────────────────

def _build_messages(system_prompt: str, user_message: str, history: List[Dict] = None,
                    language: str = "English") -> list:
    messages = [{"role": "system", "content": system_prompt}]
    for turn in (history or []):
        role = "user" if turn["sender"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["message"]})
    if history:
        lang_directive = (
            f"[CRITICAL LANGUAGE DIRECTIVE] The user is now asking in {language}. "
            f"Disregard the language of previous messages. You MUST respond strictly in {language}."
            if language != "English"
            else "[LANGUAGE DIRECTIVE] The user is asking in English. Respond in English."
        )
        messages.append({"role": "system", "content": lang_directive})
    messages.append({"role": "user", "content": user_message})
    return messages


# ─── Groq Provider ───────────────────────────────────────────────────────────

async def _stream_groq_chat(system_prompt: str, user_message: str, history: List[Dict] = None,
                              language: str = "English") -> AsyncGenerator[str, None]:
    """
    Async-stream from Groq's OpenAI-compatible API.
    Raises GroqUnavailableError if the API is unreachable or returns an error.
    """
    messages = _build_messages(system_prompt, user_message, history, language=language)
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": messages,
        "stream": True,
        "max_tokens": settings.GROQ_MAX_TOKENS,
        "temperature": 0.2,
    }

    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code == 401:
                    raise GroqUnavailableError(
                        "Invalid GROQ_API_KEY. Get a free key at https://console.groq.com"
                    )
                if resp.status_code == 429:
                    raise GroqUnavailableError(
                        "Groq rate limit hit. Falling back to local Ollama."
                    )
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise GroqUnavailableError(
                        f"Groq API error HTTP {resp.status_code}: {body[:300]}"
                    )
                async for line in resp.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                            delta = event.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
    except httpx.ConnectError as e:
        raise GroqUnavailableError(f"Could not reach Groq API: {e}") from e
    except httpx.ReadTimeout as e:
        raise GroqUnavailableError("Groq API timed out.") from e


def _call_groq_sync(system_prompt: str, user_message: str, history: List[Dict] = None,
                     language: str = "English") -> str:
    """Synchronous Groq call for short template messages."""
    messages = _build_messages(system_prompt, user_message, history, language=language)
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": min(settings.GROQ_MAX_TOKENS, 400),
        "temperature": 0.2,
    }
    try:
        resp = requests.post(
            f"{settings.GROQ_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.HTTPError as e:
        raise GroqUnavailableError(f"Groq API error: {e}") from e
    except requests.exceptions.RequestException as e:
        raise GroqUnavailableError(f"Groq unreachable: {e}") from e


# ─── Ollama Provider ──────────────────────────────────────────────────────────

async def stream_ollama_chat(system_prompt: str, user_message: str, history: List[Dict] = None,
                              model: str = None, num_predict: int = None,
                              language: str = "English") -> AsyncGenerator[str, None]:
    """
    Async-streams the answer as it's generated, yielding text deltas.
    Raises OllamaUnavailableError (before yielding anything) if Ollama can't
    be reached or the model isn't available.
    """
    messages = _build_messages(system_prompt, user_message, history, language=language)
    use_model = model or settings.OLLAMA_MODEL
    payload = {
        "model": use_model,
        "messages": messages,
        "stream": True,
        "options": {
            "num_predict": num_predict or settings.OLLAMA_NUM_PREDICT,
            "num_ctx": settings.OLLAMA_NUM_CTX,
            "temperature": 0.2,
        },
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }

    timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise OllamaUnavailableError(
                        f"Ollama returned an error (HTTP {resp.status_code}). Is the model "
                        f"'{use_model}' pulled? Try: ollama pull {use_model}\n{body[:300]}"
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = event.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if event.get("done"):
                        break
    except httpx.ConnectError as e:
        raise OllamaUnavailableError(
            f"Could not reach Ollama at {settings.OLLAMA_BASE_URL}. Is `ollama serve` running?"
        ) from e
    except httpx.ReadTimeout as e:
        raise OllamaUnavailableError(
            "Ollama took too long to respond. The model may be too large for this machine."
        ) from e


async def collect_stream(agen: AsyncGenerator[str, None]) -> str:
    """Drains a streaming generator into a single string."""
    parts = []
    async for delta in agen:
        parts.append(delta)
    return "".join(parts).strip()


def _call_ollama(system_prompt: str, user_message: str, history: List[Dict] = None,
                  model: str = None, num_predict: int = None, language: str = "English") -> str:
    """Synchronous Ollama call for short template messages."""
    messages = _build_messages(system_prompt, user_message, history, language=language)
    timeout_s = settings.OLLAMA_TIMEOUT_SECONDS
    try:
        resp = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model or settings.OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": num_predict or settings.OLLAMA_NUM_PREDICT,
                    "num_ctx": settings.OLLAMA_NUM_CTX,
                    "temperature": 0.2,
                },
                "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout as e:
        raise OllamaUnavailableError(
            f"Ollama took too long (over {timeout_s}s). Try a smaller model or increase "
            f"OLLAMA_TIMEOUT_SECONDS in .env."
        ) from e
    except requests.exceptions.ConnectionError as e:
        raise OllamaUnavailableError(
            f"Could not reach Ollama at {settings.OLLAMA_BASE_URL}. "
            "Is `ollama serve` running?"
        ) from e
    except requests.exceptions.HTTPError as e:
        raise OllamaUnavailableError(
            f"Ollama returned an error. Is the model '{model or settings.OLLAMA_MODEL}' pulled? "
            f"Try: ollama pull {model or settings.OLLAMA_MODEL}"
        ) from e

    data = resp.json()
    return data.get("message", {}).get("content", "").strip()


# ─── Unified Public API ───────────────────────────────────────────────────────

def build_context_text(chunks: List[Dict]) -> str:
    parts = []
    for c in chunks:
        label_bits = []
        if c.get("article"):
            label_bits.append(f"Article {c['article']}")
        if c.get("section"):
            label_bits.append(f"Section {c['section']}")
        if c.get("rule"):
            label_bits.append(f"Rule {c['rule']}")
        if c.get("title"):
            label_bits.append(c["title"])
        label = " - ".join(label_bits) if label_bits else c.get("document_name", "")
        parts.append(f"[{label}] {c['text']}")
    return "\n\n".join(parts)


def _with_language_reminder(message: str, language: str) -> str:
    """Redundant language directive placed right next to the question."""
    if language == "English":
        return message
    return f"{message}\n\n[Important: Please answer strictly in {language}. Use {language} script.]"


async def stream_answer(message: str, chunks: List[Dict], language: str,
                         history: List[Dict] = None) -> AsyncGenerator[str, None]:
    """
    Primary entry point for streaming an answer.
    Uses Groq if configured, falls back to Ollama automatically.
    Raises LLMUnavailableError if both fail.
    """
    context_text = build_context_text(chunks)
    system_prompt = BASE_SYSTEM_PROMPT.format(context=context_text, language=language)
    user_message = _with_language_reminder(message, language)

    if settings.use_groq:
        try:
            logger.info("Using Groq as LLM provider (model: %s)", settings.GROQ_MODEL)
            async for delta in _stream_groq_chat(system_prompt, user_message, history, language=language):
                yield delta
            return
        except (GroqUnavailableError, Exception) as groq_err:
            logger.warning("Groq failed (%s), falling back to Ollama.", groq_err)

    # Fallback: Ollama
    try:
        logger.info("Using Ollama as LLM provider (model: %s)", settings.OLLAMA_MODEL)
        async for delta in stream_ollama_chat(system_prompt, user_message, history, language=language):
            yield delta
    except OllamaUnavailableError as e:
        raise LLMUnavailableError(str(e)) from e


async def stream_general_answer(message: str, language: str,
                                history: List[Dict] = None) -> AsyncGenerator[str, None]:
    """Stream a general answer without adding legal-document context."""
    system_prompt = GENERAL_SYSTEM_PROMPT.format(language=language)
    user_message = _with_language_reminder(message, language)

    if settings.use_groq:
        try:
            logger.info("Using Groq for a general chat response (model: %s)", settings.GROQ_MODEL)
            async for delta in _stream_groq_chat(system_prompt, user_message, history, language=language):
                yield delta
            return
        except Exception as groq_err:
            logger.warning("Groq failed (%s), falling back to Ollama.", groq_err)

    try:
        logger.info("Using Ollama for a general chat response (model: %s)", settings.OLLAMA_MODEL)
        async for delta in stream_ollama_chat(system_prompt, user_message, history, language=language):
            yield delta
    except OllamaUnavailableError as e:
        raise LLMUnavailableError(str(e)) from e


async def stream_raw(system_prompt: str, user_message: str, model: str = None,
                     num_predict: int = None) -> AsyncGenerator[str, None]:
    """Stream an auxiliary generation such as a long legal-text translation."""
    if settings.use_groq:
        emitted = False
        try:
            async for delta in _stream_groq_chat(system_prompt, user_message):
                emitted = True
                yield delta
            return
        except Exception as groq_err:
            if emitted:
                raise LLMUnavailableError(f"Groq stream failed: {groq_err}") from groq_err
            logger.warning("Groq raw stream failed (%s), trying Ollama.", groq_err)

    try:
        async for delta in stream_ollama_chat(
            system_prompt, user_message, model=model, num_predict=num_predict
        ):
            yield delta
    except OllamaUnavailableError as e:
        raise LLMUnavailableError(str(e)) from e


def generate_answer(message: str, chunks: List[Dict], language: str,
                     history: List[Dict] = None) -> str:
    """Synchronous wrapper — used by non-streaming callers (tests, scripts)."""
    context_text = build_context_text(chunks)
    system_prompt = BASE_SYSTEM_PROMPT.format(context=context_text, language=language)
    user_message = _with_language_reminder(message, language)

    if settings.use_groq:
        try:
            return _call_groq_sync(system_prompt, user_message, history, language=language)
        except GroqUnavailableError as e:
            logger.warning("Groq sync call failed (%s), trying Ollama.", e)

    return _call_ollama(system_prompt, user_message, history, language=language)


def generate_raw(system_prompt: str, user_message: str, model: str = None,
                  num_predict: int = None) -> str:
    """
    One-off LLM call for auxiliary tasks (e.g. translation).
    Uses Groq if available, otherwise Ollama.
    """
    if settings.use_groq:
        try:
            return _call_groq_sync(system_prompt, user_message)
        except GroqUnavailableError as e:
            logger.warning("Groq raw call failed (%s), trying Ollama.", e)
    return _call_ollama(system_prompt, user_message, model=model, num_predict=num_predict)


def generate_clarification(query_ref: str, suggestions: List[str], language: str) -> str:
    prompt = CLARIFICATION_PROMPT.format(
        query_ref=query_ref, suggestions=", ".join(suggestions), language=language
    )
    return generate_raw(prompt, "Please ask me to clarify.")


def generate_not_found(query_ref: str, language: str) -> str:
    prompt = NOT_FOUND_PROMPT.format(query_ref=query_ref, language=language)
    return generate_raw(prompt, "Please write the not-found message.")


def generate_no_context(language: str) -> str:
    prompt = NO_CONTEXT_PROMPT.format(language=language)
    return generate_raw(prompt, "Please write the no-context message.")


# Keep backward-compat alias for any code still importing this
class LLMProvider:
    """Utility for health checks."""
    @staticmethod
    def active_provider() -> str:
        return "groq" if settings.use_groq else "ollama"

    @staticmethod
    def active_model() -> str:
        return settings.GROQ_MODEL if settings.use_groq else settings.OLLAMA_MODEL
