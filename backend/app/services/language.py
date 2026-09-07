"""
Language detection/normalization helpers, driven off the single language
table in app.i18n.messages.

Detection is primarily SCRIPT-based (Unicode code-point ranges), not
statistical (langdetect). For a chat message, script detection is both
faster and far more reliable than langdetect, which is tuned for longer
prose and frequently misfires on short strings - and script alone is
already unambiguous for 11 of our 12 supported languages, since each has
its own dedicated Unicode block. The one genuine ambiguity is Hindi vs.
Marathi (both use Devanagari) - langdetect is used ONLY as a tiebreaker
there, with Hindi as the default if that also fails.
"""
import re
from typing import Optional
from app.i18n.messages import LANGUAGE_LOCALES, DEFAULT_LANGUAGE

CODE_TO_NAME = {info["code"]: name for name, info in LANGUAGE_LOCALES.items()}

# Unicode block -> language. Order doesn't matter (ranges don't overlap)
# except Devanagari, which is ambiguous between Hindi and Marathi.
SCRIPT_RANGES = [
    (0x0980, 0x09FF, "Bengali"),
    (0x0A00, 0x0A7F, "Punjabi"),      # Gurmukhi
    (0x0A80, 0x0AFF, "Gujarati"),
    (0x0B00, 0x0B7F, "Odia"),
    (0x0B80, 0x0BFF, "Tamil"),
    (0x0C00, 0x0C7F, "Telugu"),
    (0x0C80, 0x0CFF, "Kannada"),
    (0x0D00, 0x0D7F, "Malayalam"),
    (0x0600, 0x06FF, "Urdu"),         # Arabic block (Urdu is our only Arabic-script language)
    (0x0750, 0x077F, "Urdu"),         # Arabic Supplement
    (0xFB50, 0xFDFF, "Urdu"),         # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF, "Urdu"),         # Arabic Presentation Forms-B
]
DEVANAGARI_RANGE = (0x0900, 0x097F)  # Hindi or Marathi


def normalize_language_name(language: str) -> str:
    """Accepts either a display name ('Hindi') or a code ('hi') and returns
    the canonical display name, defaulting to English if unrecognized."""
    if language in LANGUAGE_LOCALES:
        return language
    if language in CODE_TO_NAME:
        return CODE_TO_NAME[language]
    return DEFAULT_LANGUAGE


def detect_script_language(text: str) -> str:
    """
    Detects language from the Unicode script of the message text itself.
    Returns a supported language name, or "English" if the text is (or
    appears to be) written in Latin script / has no dominant non-Latin
    script - "English" here means "no strong signal", not necessarily that
    the text is grammatically English.
    """
    counts = {}
    devanagari_count = 0

    for ch in text:
        cp = ord(ch)
        if DEVANAGARI_RANGE[0] <= cp <= DEVANAGARI_RANGE[1]:
            devanagari_count += 1
            continue
        for start, end, lang in SCRIPT_RANGES:
            if start <= cp <= end:
                counts[lang] = counts.get(lang, 0) + 1
                break

    if devanagari_count > 0 and devanagari_count >= max(counts.values(), default=0):
        return _resolve_devanagari(text)

    if counts:
        return max(counts, key=counts.get)

    return "English"


def _resolve_devanagari(text: str) -> str:
    """Devanagari is shared by Hindi and Marathi - try langdetect as a
    tiebreaker; default to Hindi (the more common of the two) if that's
    inconclusive or unavailable."""
    try:
        from langdetect import detect
        code = detect(text)
        if code == "mr":
            return "Marathi"
    except Exception:
        pass
    return "Hindi"


# Common romanized / transliterated markers for Indian languages
ROMANIZED_MARKERS = {
    "Hindi": re.compile(r"\b(kya|hai|hain|kaise|kaisi|kisko|kiske|batao|bataiye|samvidhan|adhikar|anuchhed|kanoon|dharaye|dhara|theek|haal|kiddan)\b", re.IGNORECASE),
    "Telugu": re.compile(r"\b(ela|unnaru|unnav|bagunnara|bagunnava|emiti|enti|gurinchi|cheppandi|cheppu|evariki|rajyangam|adhikaram|chattam|vivarinchandi|nenu|telusa)\b", re.IGNORECASE),
    "Tamil": re.compile(r"\b(enna|sollinga|sollunga|patthi|irukku|eppadi|irukkinga|irukeenga|epdi|nalama|sowkiyama|sattam|urimai|ariciyalamaipu|kurithu|theriyuma)\b", re.IGNORECASE),
    "Kannada": re.compile(r"\b(enu|heli|bagge|ide|hegiddeera|hegiddira|chennagiddira|kanunu|samvidhana|hakku|vivarisi|gottha)\b", re.IGNORECASE),
    "Malayalam": re.compile(r"\b(enth|entha|parayu|enganeyundu|sugamano|sukhamano|niyamam|bharanaghadana|avakasam|ariyamo)\b", re.IGNORECASE),
    "Bengali": re.compile(r"\b(ki|kemon|achho|achen|bolun|shangbidhan|odhikar|ain)\b", re.IGNORECASE),
    "Marathi": re.compile(r"\b(kay|kasa|ahes|kase|ahat|sanga|sanvidhan|kayda|adhikar)\b", re.IGNORECASE),
    "Gujarati": re.compile(r"\b(shu|kem|cho|majama|kaho|bandharan|kaydo|adhikar)\b", re.IGNORECASE),
}

STRONG_ENGLISH_PATTERNS = re.compile(
    r"\b(what\s+is|what\s+are|how\s+to|how\s+does|can\s+a|who\s+is|tell\s+me\s+about|explain\s+the|under\s+the)\b",
    re.IGNORECASE,
)
ENGLISH_MARKERS = re.compile(
    r"\b(what|is|are|the|in|of|for|about|explain|tell|how|can|who|which|does|under|constitution|rights)\b",
    re.IGNORECASE,
)


def detect_language_from_text(text: str) -> str:
    """Best-effort detection: script-based first for native scripts,
    followed by Romanized pattern heuristics and langdetect."""
    script_lang = detect_script_language(text)
    if script_lang != "English":
        return script_lang

    # Check for strong English sentence structures first
    if STRONG_ENGLISH_PATTERNS.search(text):
        return "English"

    # If text is written in Latin script, check Romanized markers
    for lang, pat in ROMANIZED_MARKERS.items():
        if pat.search(text):
            return lang

    return "English"


def resolve_turn_language(message: str, requested_language: Optional[str] = None,
                          override_language: bool = False) -> str:
    """
    Authoritative language resolution for the CURRENT user turn:
      1. If the user explicitly set a manual override for this request
         (override_language=True) with a valid language (not 'auto'), respect it.
      2. If the message contains native Indian script, the detected script language
         ALWAYS wins over any stale dropdown.
      3. If the message is written in Latin script:
         - If strong English sentence structures ("what is", "explain the") match, English wins.
         - If Romanized Indian language keywords ("kya hai", "gurinchi cheppandi") match, that language wins.
         - If general English words match, English wins.
         - If text is purely numeric or ambiguous and requested_language is valid (not 'auto'),
           use requested_language.
         - Otherwise default to English.
    """
    req_norm = normalize_language_name(requested_language) if requested_language and requested_language.lower() != "auto" else None

    # 1. Manual user override
    if override_language and req_norm:
        return req_norm

    # 2. Native script detection (100% reliable for non-Latin scripts)
    script_lang = detect_script_language(message)
    if script_lang != "English":
        return script_lang

    # 3. Strong English sentence pattern check (e.g. "What is Article 21?")
    if STRONG_ENGLISH_PATTERNS.search(message):
        return "English"

    # 4. Romanized Indian language keywords (e.g. "Article 21 kya hai?")
    for lang, pat in ROMANIZED_MARKERS.items():
        if pat.search(message):
            return lang

    # 5. General English vocabulary check
    if ENGLISH_MARKERS.search(message):
        return "English"

    # 6. Purely numeric/short ambiguous reference (e.g. "21", "302") with a requested language
    digits_only = re.sub(r"[\s\d\-.,:?!]", "", message)
    if not digits_only and req_norm:
        return req_norm

    return "English"

