"""
Lightweight language detection/normalization helpers, driven off the
single language table in app.i18n.messages.
"""
from app.i18n.messages import LANGUAGE_LOCALES, DEFAULT_LANGUAGE

CODE_TO_NAME = {info["code"]: name for name, info in LANGUAGE_LOCALES.items()}


def normalize_language_name(language: str) -> str:
    """Accepts either a display name ('Hindi') or a code ('hi') and returns
    the canonical display name, defaulting to English if unrecognized."""
    if language in LANGUAGE_LOCALES:
        return language
    if language in CODE_TO_NAME:
        return CODE_TO_NAME[language]
    return DEFAULT_LANGUAGE


def detect_language_from_text(text: str) -> str:
    """Best-effort detection using langdetect; falls back to English."""
    try:
        from langdetect import detect
        code = detect(text)
        return CODE_TO_NAME.get(code, DEFAULT_LANGUAGE)
    except Exception:
        return DEFAULT_LANGUAGE
