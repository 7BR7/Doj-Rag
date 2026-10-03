"""
Translates arbitrary legal text into the user's selected language using
a robust multi-engine translation strategy:
1. Cached translations from MongoDB (instant response).
2. Deep Translation Service (LLM Legal Translation + deep_translator fallback).
3. Script verification to prevent silent English/corrupted fallbacks.
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


TRANSLATE_SYSTEM_PROMPT = """You are an expert Indian legal translator.
Translate the following legal text faithfully and accurately into {language}.
Preserve all Article/Section/Rule numbers, named statutes, and legal meaning.
Output ONLY the clean, translated text in the authentic script of {language} without any commentary, explanation, or introduction."""


def _has_target_script(text: str, language: str) -> bool:
    if language == "English":
        return True
    if language in ("Hindi", "Marathi"):
        return any("\u0900" <= char <= "\u097f" for char in text)
    if language == "Tamil":
        return any("\u0b80" <= char <= "\u0bff" for char in text)
    if language == "Telugu":
        return any("\u0c00" <= char <= "\u0c7f" for char in text)
    if language == "Kannada":
        return any("\u0c80" <= char <= "\u0cff" for char in text)
    if language == "Malayalam":
        return any("\u0d00" <= char <= "\u0d7f" for char in text)
    if language == "Bengali":
        return any("\u0980" <= char <= "\u09ff" for char in text)
    if language == "Gujarati":
        return any("\u0a80" <= char <= "\u0aff" for char in text)
    if language == "Punjabi":
        return any("\u0a00" <= char <= "\u0a7f" for char in text)
    if language == "Odia":
        return any("\u0b00" <= char <= "\u0b7f" for char in text)
    if language == "Urdu":
        return any("\u0600" <= char <= "\u06ff" for char in text)
    return detect_script_language(text) == language


def _translation_unavailable(language: str) -> str:
    return get_message("translation_unavailable", language)


def _cache_key(text: str, language: str) -> str:
    digest = hashlib.sha256(f"{language}::{text}".encode("utf-8")).hexdigest()
    return digest


def translate_text(text: str, language: str) -> str:
    """
    Returns text in the requested language. Uses cached translations,
    followed by the translation_service LLM/Deep-translator pipeline.
    """
    if not text or language == "English":
        return text

    cache_key = _cache_key(text, language)

    # 1. Check MongoDB cache
    try:
        from app.database.mongodb import get_db
        db = get_db()
        cached = db.translations.find_one({"cache_key": cache_key})
        if cached and _has_target_script(cached.get("translated_text", ""), language):
            return cached["translated_text"]
    except Exception:
        db = None

    # 2. Try high-precision translation service
    try:
        from app.nlp.translation_service import translate_response_to_target
        res = translate_response_to_target(text, language)
        if res and res.strip() and _has_target_script(res, language):
            return res.strip()
    except Exception as e:
        logger.warning("Translation service call failed: %s, trying direct LLM", e)

    # 3. Direct LLM call fallback
    try:
        system_prompt = TRANSLATE_SYSTEM_PROMPT.format(language=language)
        num_pred = max(settings.OLLAMA_TRANSLATE_NUM_PREDICT, min(1200, len(text) * 2))
        translated = generate_raw(
            system_prompt,
            f"Translate to {language}:\n\n{text}",
            model=settings.OLLAMA_TRANSLATE_MODEL,
            num_predict=num_pred,
        )
        translated = translated.strip()
        if translated and _has_target_script(translated, language):
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
            return translated
    except Exception as e:
        logger.warning("Direct LLM translation fallback failed: %s", e)

    return _translation_unavailable(language)


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
    except Exception as e:
        logger.warning("Streaming translation error: %s, falling back to sync", e)
        fallback = translate_text(text, language)
        yield fallback
        return

    translated = "".join(translated_parts).strip()
    if translated and _has_target_script(translated, language) and db is not None:
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
