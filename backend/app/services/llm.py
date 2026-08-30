"""
Ollama-backed local LLM client. All generation is grounded strictly in
retrieved legal context - the model is instructed never to use outside
knowledge, to avoid hallucinated legal facts.
"""
import logging
import requests
from typing import List, Dict, Optional
from app.config import settings
from app.prompts.system_prompt import (
    BASE_SYSTEM_PROMPT, CLARIFICATION_PROMPT, NOT_FOUND_PROMPT, NO_CONTEXT_PROMPT
)

logger = logging.getLogger("doj_rag.llm")


class OllamaUnavailableError(Exception):
    pass


def _call_ollama(system_prompt: str, user_message: str, history: List[Dict] = None,
                  model: str = None, num_predict: int = None) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    for turn in (history or []):
        messages.append({"role": turn["sender"] == "user" and "user" or "assistant",
                          "content": turn["message"]})
    messages.append({"role": "user", "content": user_message})

    try:
        resp = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model or settings.OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                # Speed-oriented generation options:
                #  - num_predict caps output length. Requirement 14 already
                #    asks for "short to medium" answers, so this doesn't lose
                #    anything - but on CPU, generation time scales almost
                #    linearly with output tokens, so this is the single
                #    biggest lever for cutting a 2-3 minute wait down.
                #  - num_ctx is capped since our grounded context is a few
                #    small legal chunks, not a huge document - a smaller
                #    context window means faster prompt processing.
                #  - keep_alive keeps the model loaded in memory between
                #    requests so it isn't reloaded from disk every message
                #    (reloading a multi-GB model from disk is often the
                #    actual cause of a multi-minute wait, not generation
                #    itself).
                "options": {
                    "num_predict": num_predict or settings.OLLAMA_NUM_PREDICT,
                    "num_ctx": settings.OLLAMA_NUM_CTX,
                    "temperature": 0.3,
                },
                "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            },
            timeout=120,
        )
        resp.raise_for_status()
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
    return _call_ollama(system_prompt, message, history)


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
