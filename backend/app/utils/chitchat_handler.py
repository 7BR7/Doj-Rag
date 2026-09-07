"""
Detects casual conversational messages (greetings, "do you know Hindi?",
"who are you", thanks, etc.) so they can be answered instantly and directly
in the user's selected language, WITHOUT going through legal retrieval or
an LLM call.

Why this matters: without this, a message like "Hindi aati hai?" (colloquial
Hindi for "do you know Hindi?") was falling through to hybrid RAG retrieval,
where BM25 could match on the word "Hindi" against something like the Eighth
Schedule's list of official languages, and the LLM would then generate a full
essay from that irrelevant context instead of just answering the question
that was actually asked. This module intercepts that class of message first.

Actual response text lives in app.i18n.messages, so all supported languages
share one source of truth.
"""
import re
from typing import Optional
from app.i18n.messages import get_message

# Casual small talk regexes:

# How are you (including greetings + how are you):
HOW_ARE_YOU_RE = re.compile(
    r"^(?:(?:hi|hii+|hello+|hey+|namaste|namaskar|good\s*(?:morning|afternoon|evening))\s*[,!.]*\s*)?"
    r"(?:how\s*(?:are|r)\s*(?:you|u)|how(?:'s|s|\s+is)\s*(?:it\s*going|everything|life)|how\s*(?:are|r)\s*(?:you|u)\s*doing|"
    r"what(?:'s|\s+is)\s*up|whats\s*up|sup|how\s*do\s*you\s*do|how\s*have\s*you\s*been|"
    r"kaise\s*ho|kaisi\s*ho|kaise\s*hain|aap\s*kaise\s*(?:ho|hain)|tum\s*kaise\s*ho|kya\s*ha+l(?:\s*chaal)?(?:\s*hai)?|kya\s*chal\s*raha(?:\s*hai)?|sab\s*kaisa(?:\s*hai)?|sab\s*theek(?:\s*hai)?|kese\s*ho|"
    r"ela\s*unnaru|ela\s*unnav|ela\s*unaru|ela\s*unavu|bagunnara|bagunnava|kushalama|enti\s*sangathulu|em\s*chestunnav|"
    r"eppadi\s*irukkinga|eppadi\s*irukeenga|eppadi\s*irukkeergal|epdi\s*iruk(?:inga|a)?|nalama|sowkiyama|eppadi\s*irukkindreergal|"
    r"hegiddeera|hegiddira|hegidiya|chennagiddira|hegidhdheera|"
    r"enganeyundu|sugamano|sukhamano|entha\s*visesham|"
    r"kemon\s*achho|kemon\s*achen|kemon\s*acho|ki\s*khobor|"
    r"kasa\s*ahes|kase\s*ahat|kashi\s*ahes|kay\s*challay|"
    r"kem\s*cho|majama|maja\s*ma|"
    r"ki\s*haal\s*hai|kiddan|kive\s*o|kive\s*ho|"
    r"kemiti\s*achhanti|kemiti\s*achhu|bhala\s*achhanti|"
    r"బాగున్నారా|ఎలా\s*ఉన్నారు|ఎలా\s*ఉన్నావు|आप\s*कैसे\s*हैं|कैसे\s*हो|எப்படி\s*இருக்கிறீர்கள்|எப்படி\s*இருக்கீங்க|কেমন\s*আছেন|സുഖമാണോ|ಹೇಗಿದ್ದೀರಾ|કેમ\s*છો)"
    r"\s*[!?.]*$",
    re.IGNORECASE | re.UNICODE,
)

# User communicating state/status ("I am fine", "I'm good", etc.)
STATUS_FINE_RE = re.compile(
    r"^(?:i\s*am\s*fine|i'?m\s*fine|im\s*fine|i\s*am\s*good|i'?m\s*good|im\s*good|all\s*good|doing\s*well|doing\s*good|"
    r"fine|good|great|awesome|super|i\s*am\s*doing\s*well|i'?m\s*doing\s*well|"
    r"mai\s*theek\s*hu|main\s*theek\s*hoon|hum\s*theek\s*hain|theek\s*hu|theek\s*hai|main\s*achha\s*hu|sab\s*theek|"
    r"nenu\s*bagunnanu|bagunnanu|chala\s*bagunnanu|naan\s*nalam|nandraga\s*irukiren|"
    r"బాగున్నాను|నేను\s*బాగున్నాను|मैं\s*ठीक\s*हूँ|ठीक\s*हूँ|நல்லா\s*இருக்கேன்)\s*[!?.]*$",
    re.IGNORECASE | re.UNICODE,
)

# Greetings:
GREETING_RE = re.compile(
    r"^\s*(hi|hii+|hello+|hey+|namaste|namaskar|namaskaram|namaskara|vanakkam|nomoshkar|"
    r"sat\s*sri\s*akal|assalam.*alaikum|adaab|pranam|good\s*(?:morning|afternoon|evening|day)|greetings|"
    r"నమస్తే|నమస్కారం|नमस्ते|नमस्कार|வணக்கம்|নমস্কার|ਸਤਿ\s*ਸ੍ਰੀ\s*ਅਕਾਲ|നമസ്കാരം|ನಮಸ್ಕಾರ)\s*[!.?]*\s*$",
    re.IGNORECASE | re.UNICODE,
)

# Thanks:
THANKS_RE = re.compile(
    r"^\s*(thanks?|thank\s*you|thanku|thx|ty|thanks\s*a\s*lot|thank\s*you\s*so\s*much|thank\s*you\s*very\s*much|"
    r"dhanyavad|dhanyawad|shukriya|nandri|nandi|dhonnobad|aabhar|dhanvaad|dhanyabad|"
    r"ధన్యవాదాలు|ధన్యవాదం|धन्यवाद|शुक्रिया|நன்றி|ধন্যবাদ)\s*[!.?]*\s*$",
    re.IGNORECASE | re.UNICODE,
)

# Goodbye:
GOODBYE_RE = re.compile(
    r"^\s*(bye|goodbye|good\s*bye|see\s*you|bye\s*bye|tata|alvida|take\s*care|good\s*night|shubh\s*ratri|selavu|"
    r"సెలవు|अलविदा|शुभ\s*रात्रि|বিদায়|விருப்பம்)\s*[!.?]*\s*$",
    re.IGNORECASE | re.UNICODE,
)

# Who are you / Bot Identity / Capabilities:
WHO_ARE_YOU_RE = re.compile(
    r"\b(who\s*are\s*you|what\s*are\s*you|what\s*is\s*your\s*name|tell\s*me\s*your\s*name|your\s*name|"
    r"who\s*made\s*you|who\s*created\s*you|who\s*developed\s*you|what\s*can\s*you\s*(?:do|help)|"
    r"can\s*you\s*help\s*me|aap\s*kaun\s*ho|tum\s*kaun\s*ho|meeru\s*evaru|neevu\s*yaaru|neengal\s*yaar|"
    r"నువ్వు\s*ఎవరు|మీరు\s*ఎవరు|आप\s*कौन\s*हैं|आप\s*कौन\s*हो)\b",
    re.IGNORECASE | re.UNICODE,
)

# Casual "do you know/speak <language>?" in English or transliterated Indian-
# language phrasing - a capability question, not a legal question.
_LANG_WORDS = r"(hindi|tamil|telugu|english|kannada|malayalam|bengali|marathi|gujarati|punjabi|odia|oriya|urdu)"
LANGUAGE_CAPABILITY_RE = re.compile(
    rf"^\s*{_LANG_WORDS}\s*(aati|aata|bolte|samajhte|vare)\s*(hai|hain)\s*\??\s*$"
    rf"|^\s*{_LANG_WORDS}\s*(gottha|gottide|barutha|baruthade|theriyuma|telusa|ariyamo|ariyumo)\s*\??\s*$"
    rf"|\bdo you (know|speak|understand)\s+{_LANG_WORDS}\b",
    re.IGNORECASE,
)


def detect_chitchat(message: str) -> Optional[str]:
    """
    Returns a canned response category if this message is small talk / a
    meta question about the assistant rather than a legal question, else None.
    """
    text = message.strip()
    if not text:
        return None

    # Check how are you first so "hi how are you" maps to how_are_you
    if HOW_ARE_YOU_RE.match(text):
        return "how_are_you"
    if STATUS_FINE_RE.match(text):
        return "status_fine"
    if GREETING_RE.match(text):
        return "greeting"
    if THANKS_RE.search(text):
        return "thanks"
    if GOODBYE_RE.match(text):
        return "goodbye"
    if WHO_ARE_YOU_RE.search(text):
        return "who_are_you"
    if LANGUAGE_CAPABILITY_RE.search(text):
        return "language_capability"

    return None


def get_chitchat_response(category: str, language: str) -> str:
    return get_message(category, language)
