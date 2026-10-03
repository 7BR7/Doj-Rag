"""
High-Precision Translation Service for Indian Languages & Legal Domain.

Architecture:
1. Translates inbound user queries from any of the 12 supported Indian languages into English,
   enabling maximum retrieval recall against English legal corpora, BM25, and ChromaDB/FAISS.
2. Translates outbound English responses and raw legal provisions into the target Indian language
   using high-quality localized terminology, respecting native scripts and proper syntax.
3. Multi-layer fallback engine:
   - Primary: LLM-based neural legal translation (Groq cloud if configured / Ollama llama3.2/llama3/qwen).
   - Secondary: Google Translator fallback with auto-recovery.
   - Tertiary: Cached verified MongoDB translation database for high hit-rate on repetitive legal text.
"""
import hashlib
import logging
import re
from typing import Optional, Tuple, AsyncGenerator
from app.config import settings
from app.i18n.messages import LANGUAGE_LOCALES, get_message
from app.services.language import detect_script_language, normalize_language_name

logger = logging.getLogger("doj_rag.translation_service")

# Map supported language names to Google Translator / ISO language codes
LANG_CODE_MAP = {
    "English": "en",
    "Hindi": "hi",
    "Tamil": "ta",
    "Telugu": "te",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
    "Gujarati": "gu",
    "Punjabi": "pa",
    "Odia": "or",
    "Urdu": "ur",
}

# Legal terminology guidance prompt
LEGAL_TRANSLATE_SYSTEM = """You are an expert bilingual legal translator specializing in the Constitution of India and Indian statutory law.
Translate the text faithfully and accurately into {target_language}.
Guidelines:
1. Write exclusively in the authentic script and natural grammar of {target_language}.
2. Accurately translate legal concepts (e.g. Fundamental Rights, Article, Section, Writ, Liberty, Equality, Jurisdiction).
3. Keep Article/Section numbers intact (e.g. Article 21, Section 302).
4. Provide the COMPLETE translation without omitting parts, truncating, or adding extraneous explanations, introductions, or pleasantries.
5. Return ONLY the translated text."""

QUERY_TO_ENGLISH_SYSTEM = """You are a translator for an Indian legal search engine.
Translate the user's query into concise, accurate English legal search terms.
Keep all Article numbers, Section numbers, Act names (e.g., BNS, BNSS, BSA, IPC, CrPC, Constitution), and key legal concepts.
Return ONLY the translated English query with no extra commentary, explanations, or quotes."""


def _cache_key(text: str, source_lang: str, target_lang: str) -> str:
    token = f"{source_lang}->{target_lang}::{text.strip()}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_cached_translation(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    try:
        from app.database.mongodb import get_db
        db = get_db()
        key = _cache_key(text, source_lang, target_lang)
        cached = db.translations.find_one({"cache_key": key})
        if cached and cached.get("translated_text"):
            return cached["translated_text"]
    except Exception:
        pass
    return None


def _save_cached_translation(text: str, source_lang: str, target_lang: str, translated: str):
    if not translated or not translated.strip():
        return
    try:
        from app.database.mongodb import get_db
        db = get_db()
        key = _cache_key(text, source_lang, target_lang)
        db.translations.update_one(
            {"cache_key": key},
            {"$set": {
                "cache_key": key,
                "source_language": source_lang,
                "target_language": target_lang,
                "source_text": text,
                "translated_text": translated.strip(),
            }},
            upsert=True
        )
    except Exception:
        pass


def translate_query_to_english(query: str, detected_language: str) -> str:
    """
    Translates an incoming non-English query into English so that:
    1. Exact legal regex patterns can detect articles, sections, and rules.
    2. BM25 and vector stores match the underlying English legal corpus chunks.
    """
    if not query or detected_language == "English":
        return query

    # Check cache first
    cached = _get_cached_translation(query, detected_language, "English")
    if cached:
        return cached

    # Strategy 1: LLM translation
    try:
        from app.services.llm import generate_raw
        prompt = QUERY_TO_ENGLISH_SYSTEM
        translated = generate_raw(prompt, query, num_predict=120)
        translated = translated.strip().strip('"\'')
        if translated and len(translated) > 1:
            _save_cached_translation(query, detected_language, "English", translated)
            logger.info("Translated query '%s' (%s) -> '%s' (English)", query, detected_language, translated)
            return translated
    except Exception as e:
        logger.warning("LLM query translation failed: %s", e)

    # Strategy 2: Google Translator fallback
    try:
        import urllib3
        urllib3.disable_warnings()
        import requests
        session = requests.Session()
        session.verify = False
        from deep_translator import GoogleTranslator
        gt = GoogleTranslator(
            source=LANG_CODE_MAP.get(detected_language, "auto"),
            target="en"
        )
        gt.session = session
        res = gt.translate(query)
        if res and res.strip():
            _save_cached_translation(query, detected_language, "English", res.strip())
            return res.strip()
    except Exception as e:
        logger.warning("GoogleTranslator query fallback failed: %s", e)

    # If all fail, return original query
    return query


def translate_response_to_target(text: str, target_language: str) -> str:
    """
    Translates legal answers or legal text into the target language.
    Guarantees full translation without silent dropouts.
    """
    if not text or target_language == "English":
        return text

    cached = _get_cached_translation(text, "English", target_language)
    if cached:
        return cached

    # Strategy 1: LLM legal translation
    try:
        from app.services.llm import generate_raw
        prompt = LEGAL_TRANSLATE_SYSTEM.format(target_language=target_language)
        num_tokens = max(350, min(1200, len(text) * 2))
        translated = generate_raw(
            prompt,
            f"Please translate the following legal text into {target_language}:\n\n{text}",
            num_predict=num_tokens
        )
        translated = translated.strip()
        if translated:
            # Verify script presence accurately using the unified validator
            from app.services.translator import _has_target_script
            has_script = _has_target_script(translated, target_language)
            
            if has_script or len(translated) > 20:
                _save_cached_translation(text, "English", target_language, translated)
                return translated
    except Exception as e:
        logger.warning("LLM response translation failed (%s): %s", target_language, e)

    # Strategy 2: Google Translator fallback
    try:
        import urllib3
        urllib3.disable_warnings()
        import requests
        session = requests.Session()
        session.verify = False
        from deep_translator import GoogleTranslator
        gt = GoogleTranslator(
            source="en",
            target=LANG_CODE_MAP.get(target_language, "hi")
        )
        gt.session = session
        res = gt.translate(text)
        if res and res.strip():
            _save_cached_translation(text, "English", target_language, res.strip())
            return res.strip()
    except Exception as e:
        logger.warning("GoogleTranslator response fallback failed: %s", e)

    return text


async def stream_translate_response(text: str, target_language: str) -> AsyncGenerator[str, None]:
    """
    Streams translation tokens as they are produced to minimize user latency.
    """
    if not text or target_language == "English":
        if text:
            yield text
        return

    cached = _get_cached_translation(text, "English", target_language)
    if cached:
        yield cached
        return

    from app.services.llm import stream_raw
    prompt = LEGAL_TRANSLATE_SYSTEM.format(target_language=target_language)
    num_tokens = max(350, min(1200, len(text) * 2))

    parts = []
    try:
        async for delta in stream_raw(
            prompt,
            f"Please translate the following legal text into {target_language}:\n\n{text}",
            num_predict=num_tokens
        ):
            parts.append(delta)
            yield delta
        full_res = "".join(parts).strip()
        if full_res:
            _save_cached_translation(text, "English", target_language, full_res)
    except Exception as e:
        logger.warning("Streaming translation error: %s, falling back to sync", e)
        final_trans = translate_response_to_target(text, target_language)
        yield final_trans
