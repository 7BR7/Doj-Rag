"""
Ollama-backed local LLM client. All generation is grounded strictly in
retrieved legal context - the model is instructed never to use outside
knowledge, to avoid hallucinated legal facts.

Generation is STREAMED end-to-end (Ollama -> FastAPI -> browser) rather than
"wait for the whole answer, then send it back":
  - The user sees the answer appear as it's generated instead of staring at
    a blank screen for however long full generation takes - the biggest
    single improvement to *perceived* speed.
  - It makes the request genuinely cancellable: if the user starts editing
    an earlier message while a response is still streaming, the frontend
    can abort the fetch, which (because this uses httpx's async streaming
    with a real context manager) closes the underlying connection to
    Ollama and stops generation server-side too, instead of wasting
    compute on an answer nobody will see.
"""
import json
import logging
from typing import List, Dict, Optional, AsyncGenerator
import httpx
import requests
from app.config import settings
from app.prompts.system_prompt import (
    BASE_SYSTEM_PROMPT, CLARIFICATION_PROMPT, NOT_FOUND_PROMPT, NO_CONTEXT_PROMPT
)

logger = logging.getLogger("doj_rag.llm")


class OllamaUnavailableError(Exception):
    pass


def _build_messages(system_prompt: str, user_message: str, history: List[Dict] = None) -> list:
    messages = [{"role": "system", "content": system_prompt}]
    for turn in (history or []):
        messages.append({"role": turn["sender"] == "user" and "user" or "assistant",
                          "content": turn["message"]})
    messages.append({"role": "user", "content": user_message})
    return messages


async def stream_ollama_chat(system_prompt: str, user_message: str, history: List[Dict] = None,
                              model: str = None, num_predict: int = None) -> AsyncGenerator[str, None]:
    """
    Async-streams the answer as it's generated, yielding text deltas.
    Raises OllamaUnavailableError (before yielding anything) if Ollama can't
    be reached or the model isn't available, so callers can show a clean
    error instead of a half-streamed response.
    """
    messages = _build_messages(system_prompt, user_message, history)
    use_model = model or settings.OLLAMA_MODEL
    payload = {
        "model": use_model,
        "messages": messages,
        "stream": True,
        "options": {
            "num_predict": num_predict or settings.OLLAMA_NUM_PREDICT,
            "num_ctx": settings.OLLAMA_NUM_CTX,
            "temperature": 0.3,
        },
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }

    # Generous read timeout since streaming keeps the connection alive with
    # a steady trickle of tokens (unlike the old wait-for-everything call,
    # this won't go silent for minutes) - but connect must fail fast if
    # Ollama isn't running at all.
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
            "Ollama took too long to respond. The model may be too large for this machine - "
            "try a smaller one (see OLLAMA_MODEL in .env)."
        ) from e


async def collect_stream(agen: AsyncGenerator[str, None]) -> str:
    """Drains a streaming generator into a single string - used by callers
    (like translation) that need the full text rather than incremental
    delivery, while still benefiting from the same cancellable connection."""
    parts = []
    async for delta in agen:
        parts.append(delta)
    return "".join(parts).strip()


def _call_ollama(system_prompt: str, user_message: str, history: List[Dict] = None,
                  model: str = None, num_predict: int = None) -> str:
    """
    Synchronous, non-streaming call - kept for the short, fixed-shape
    template calls (clarification/not-found/no-context messages) where a
    full round trip is already fast and streaming would add complexity for
    no benefit.
    """
    messages = _build_messages(system_prompt, user_message, history)
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
                    "temperature": 0.3,
                },
                "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout as e:
        raise OllamaUnavailableError(
            f"Ollama took too long to respond (over {timeout_s}s). The model may be too large "
            f"for this machine, or it's still loading. Try a smaller model, or increase "
            f"OLLAMA_TIMEOUT_SECONDS in .env if this happens consistently on a slow first run."
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


def generate_answer(message: str, chunks: List[Dict], language: str,
                     history: List[Dict] = None) -> str:
    context_text = build_context_text(chunks)
    system_prompt = BASE_SYSTEM_PROMPT.format(context=context_text, language=language)
    user_message = _with_language_reminder(message, language)
    return _call_ollama(system_prompt, user_message, history)


async def stream_answer(message: str, chunks: List[Dict], language: str,
                         history: List[Dict] = None) -> AsyncGenerator[str, None]:
    """Streaming counterpart of generate_answer - used for the general/hybrid
    question path (the only path that still needs open-ended generation)."""
    context_text = build_context_text(chunks)
    system_prompt = BASE_SYSTEM_PROMPT.format(context=context_text, language=language)
    user_message = _with_language_reminder(message, language)
    async for delta in stream_ollama_chat(system_prompt, user_message, history):
        yield delta


def _with_language_reminder(message: str, language: str) -> str:
    """Redundant language directive placed right next to the actual
    question, not just buried in the system prompt - models tend to follow
    instructions positioned near the end of the input more reliably. This is
    what makes a Telugu question actually get answered in Telugu instead of
    silently drifting to English."""
    if language == "English":
        return message
    return f"{message}\n\n(Please answer in {language}.)"


def generate_clarification(query_ref: str, suggestions: List[str], language: str) -> str:
    prompt = CLARIFICATION_PROMPT.format(
        query_ref=query_ref, suggestions=", ".join(suggestions), language=language
    )
    return _call_ollama(prompt, "Please ask me to clarify.", None)


def generate_not_found(query_ref: str, language: str) -> str:
    prompt = NOT_FOUND_PROMPT.format(query_ref=query_ref, language=language)
    return _call_ollama(prompt, "Please write the not-found message.", None)


def generate_no_context(language: str) -> str:
    prompt = NO_CONTEXT_PROMPT.format(language=language)
    return _call_ollama(prompt, "Please write the no-context message.", None)


def generate_raw(system_prompt: str, user_message: str, model: str = None, num_predict: int = None) -> str:
    """Public entry point for one-off LLM calls outside the main chat flow
    (e.g. translation) that don't need the full grounded-answer prompting,
    and may want a different (faster/smaller) model or output cap."""
    return _call_ollama(system_prompt, user_message, history=None, model=model, num_predict=num_predict)
