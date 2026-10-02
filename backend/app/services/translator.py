"""
Translates arbitrary legal text (Article/Section/Rule bodies, which only
exist in the source PDF's language - normally English) into the user's
selected language, using the local Ollama LLM.

This is what makes "if Tamil is selected, the answer must be in Tamil"
actually true for the fast, no-general-generation exact-match path - before
this existed, exact-match answers were always returned in the source
document's language regardless of the language selector, because that path
was deliberately built to skip the LLM for speed. Translation only runs when
the selected language differs from English, and results are cached in
MongoDB per (chunk signature, language) so the same Article is never
re-translated on every request.
"""
import hashlib
import logging
from typing import Optional
from app.config import settings
from app.services.llm import generate_raw, stream_raw, OllamaUnavailableError, LLMUnavailableError
from app.services.language import detect_script_language
from app.i18n.messages import get_message

logger = logging.getLogger("doj_rag.translator")


class TranslationUnavailableError(Exception):
    pass

TRANSLATE_SYSTEM_PROMPT = """You are a precise legal-document translator.
Translate the COMPLETE English legal text into {language}. Preserve every
sentence, example, condition, name, and Article/Section number. Use the correct
legal meaning; do not summarize, omit text, or add commentary. Output only the
full translation."""


def _has_target_script(text: str, language: str) -> bool:
    if language == "English":
        return True
    if language in ("Hindi", "Marathi"):
        return any("\u0900" <= char <= "\u097f" for char in text)
    return detect_script_language(text) == language


def _translation_unavailable(language: str) -> str:
    return get_message("translation_unavailable", language)


def _cache_key(text: str, language: str) -> str:
    digest = hashlib.sha256(f"{language}::{text}".encode("utf-8")).hexdigest()
    return digest


def translate_text(text: str, language: str) -> str:
    """
    Returns text in the requested language. If translation fails or returns
    the source language, return a localized status instead of silently
    displaying English as though it were translated.
    """
    if not text or language == "English":
        return text

    cache_key = _cache_key(text, language)

    try:
        from app.database.mongodb import get_db
        db = get_db()
        cached = db.translations.find_one({"cache_key": cache_key})
        if cached and _has_target_script(cached.get("translated_text", ""), language):
            return cached["translated_text"]
    except Exception:
        db = None  # Mongo unavailable - proceed without caching rather than failing

    try:
        system_prompt = TRANSLATE_SYSTEM_PROMPT.format(language=language)
        translated = generate_raw(
            system_prompt, text,
            model=settings.OLLAMA_TRANSLATE_MODEL,  # falls back to OLLAMA_MODEL if unset
            num_predict=max(settings.OLLAMA_TRANSLATE_NUM_PREDICT, min(900, len(text))),
        )
        translated = translated.strip()
        if not translated or not _has_target_script(translated, language):
            logger.warning("Translation returned no %s script; refusing source-language fallback.", language)
            return _translation_unavailable(language)
    except OllamaUnavailableError:
        logger.warning("Translation unavailable for %s; returning localized status.", language)
        return _translation_unavailable(language)

    if db is not None:
        try:
            db.translations.update_one(
                {"cache_key": cache_key},
                {"$set": {
                    "cache_key": cache_key,
                    "language": language,
                    "source_text": text,
                    "translated_text": translated,
                }},
                upsert=True,
            )
        except Exception:
            pass  # caching is a best-effort optimization, never fail the request over it

    return translated


async def stream_translate_text(text: str, language: str):
    """Yield translated text as it is generated and cache it once complete."""
    if not text or language == "English":
        if text:
            yield text
        return

    cache_key = _cache_key(text, language)
    db = None
    try:
        from app.database.mongodb import get_db
        db = get_db()
        cached = db.translations.find_one({"cache_key": cache_key})
        if cached and _has_target_script(cached.get("translated_text", ""), language):
            yield cached["translated_text"]
            return
    except Exception:
        db = None

    translated_parts = []
    try:
        async for delta in stream_raw(
            TRANSLATE_SYSTEM_PROMPT.format(language=language),
            text,
            model=settings.OLLAMA_TRANSLATE_MODEL,
            num_predict=max(settings.OLLAMA_TRANSLATE_NUM_PREDICT, min(900, len(text))),
        ):
            translated_parts.append(delta)
            yield delta
    except LLMUnavailableError as e:
        logger.warning("Streaming translation unavailable for %s: %s", language, e)
        raise TranslationUnavailableError(str(e)) from e

    translated = "".join(translated_parts).strip()
    if not translated or not _has_target_script(translated, language):
        logger.warning("Streaming translation returned no %s script.", language)
        raise TranslationUnavailableError(f"Translation did not produce {language} text.")

    if db is not None:
        try:
            db.translations.update_one(
                {"cache_key": cache_key},
                {"$set": {
                    "cache_key": cache_key,
                    "language": language,
                    "source_text": text,
                    "translated_text": translated,
                }},
                upsert=True,
            )
        except Exception:
            pass
