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

GREETING_RE = re.compile(
    r"^\s*(hi|hii+|hello+|hey+|namaste|namaskar|namaskaram|namaskara|vanakkam|nomoshkar|"
    r"sat\s*sri\s*akal|assalam.*alaikum|good\s*(morning|afternoon|evening))\s*[!.?]*\s*$",
    re.IGNORECASE,
)

THANKS_RE = re.compile(
    r"^\s*(thanks?|thank\s*you|thanku|dhanyavad|dhanyawad|shukriya|nandri|nandi|"
    r"dhonnobad|aabhar|dhanvaad|dhanyabad)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

WHO_ARE_YOU_RE = re.compile(
    r"\b(who are you|what are you|what can you (do|help)|aap kaun ho|tum kaun ho)\b",
    re.IGNORECASE,
)

# Casual "do you know/speak <language>?" in English or transliterated Indian-
# language phrasing - a capability question, not a legal question.
# Anchored to the WHOLE message (^...$) so this doesn't false-positive on
# something like "...explain this in Hindi" (a legitimate in-context
# translation request, not a meta question about capability).
_LANG_WORDS = r"(hindi|tamil|telugu|english|kannada|malayalam|bengali|marathi|gujarati|punjabi|odia|oriya|urdu)"
LANGUAGE_CAPABILITY_RE = re.compile(
    rf"^\s*{_LANG_WORDS}\s*(aati|aata|bolte|samajhte|vare)\s*(hai|hain)\s*\??\s*$"
    rf"|^\s*{_LANG_WORDS}\s*(gottha|gottide|barutha|baruthade|theriyuma|telusa|ariyamo|ariyumo)\s*\??\s*$"
    rf"|\bdo you (know|speak|understand)\s+{_LANG_WORDS}\b",
    re.IGNORECASE,
)

HOW_ARE_YOU_RE = re.compile(
    r"^\s*(how are you|kaise ho|kaisi ho|kem cho|eppadi irukkinga|ela unnaru)\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def detect_chitchat(message: str) -> Optional[str]:
    """
    Returns a canned response category if this message is small talk / a
    meta question about the assistant rather than a legal question, else None.
    """
    text = message.strip()

    if GREETING_RE.match(text):
        return "greeting"
    if THANKS_RE.match(text):
        return "thanks"
    if HOW_ARE_YOU_RE.match(text):
        return "how_are_you"
    if WHO_ARE_YOU_RE.search(text):
        return "who_are_you"
    if LANGUAGE_CAPABILITY_RE.search(text):
        return "language_capability"

    return None


def get_chitchat_response(category: str, language: str) -> str:
    return get_message(category, language)
