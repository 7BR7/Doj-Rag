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
from app.services.llm import generate_raw, OllamaUnavailableError

logger = logging.getLogger("doj_rag.translator")

TRANSLATE_SYSTEM_PROMPT = """You are a precise legal-document translator.
Translate the following English legal text into {language}. Preserve the
legal meaning and any Article/Section numbers exactly. Do not add
commentary, explanations, or extra text - output ONLY the translation."""


def _cache_key(text: str, language: str) -> str:
    digest = hashlib.sha256(f"{language}::{text}".encode("utf-8")).hexdigest()
    return digest


def translate_text(text: str, language: str) -> str:
    """
    Returns the translated text, or the original text unchanged if
    translation isn't needed (English) or the LLM is unavailable (graceful
    degrade - an English answer is better than a failed request).
    """
    if not text or language == "English":
        return text

    cache_key = _cache_key(text, language)

    try:
        from app.database.mongodb import get_db
        db = get_db()
        cached = db.translations.find_one({"cache_key": cache_key})
        if cached:
            return cached["translated_text"]
    except Exception:
        db = None  # Mongo unavailable - proceed without caching rather than failing

    try:
        system_prompt = TRANSLATE_SYSTEM_PROMPT.format(language=language)
        translated = generate_raw(
            system_prompt, text,
            model=settings.OLLAMA_TRANSLATE_MODEL,  # falls back to OLLAMA_MODEL if unset
            num_predict=settings.OLLAMA_TRANSLATE_NUM_PREDICT,
        )
        translated = translated.strip() or text
    except OllamaUnavailableError:
        logger.warning("Translation skipped: Ollama unavailable, returning source-language text.")
        return text

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
