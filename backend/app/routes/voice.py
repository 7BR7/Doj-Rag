"""
POST /api/transcribe
"""
import hashlib
import logging
import re
from typing import Optional
import urllib.parse
import urllib.request
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Response
from app.models.schemas import TranscribeResponse
from app.services.speech_to_text import transcribe_audio_bytes, TranscriptionError

router = APIRouter(prefix="/api", tags=["voice"])
logger = logging.getLogger("doj_rag.routes.voice")

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...), language: Optional[str] = Query(None)):
    content = await audio.read()

    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25MB).")

    try:
        text, detected_code, detected_name = transcribe_audio_bytes(
            content, audio.filename or "audio.wav", language_hint=language
        )
        return TranscribeResponse(
            text=text,
            detected_language=detected_name,
            language_code=detected_code,
        )
    except TranscriptionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unexpected transcription error")
        raise HTTPException(status_code=500, detail="Failed to process audio.")


# In-memory TTS audio cache: (hash) -> bytes
_tts_cache: dict[str, bytes] = {}
MAX_TTS_CACHE_SIZE = 500

SCRIPT_LANG_PATTERNS = [
    (re.compile(r"[\u0B80-\u0BFF]"), "ta"),  # Tamil
    (re.compile(r"[\u0C00-\u0C7F]"), "te"),  # Telugu
    (re.compile(r"[\u0C80-\u0CFF]"), "kn"),  # Kannada
    (re.compile(r"[\u0D00-\u0D7F]"), "ml"),  # Malayalam
    (re.compile(r"[\u0980-\u09FF]"), "bn"),  # Bengali
    (re.compile(r"[\u0A80-\u0AFF]"), "gu"),  # Gujarati
    (re.compile(r"[\u0A00-\u0A7F]"), "pa"),  # Punjabi
    (re.compile(r"[\u0B00-\u0B7F]"), "or"),  # Odia
    (re.compile(r"[\u0600-\u06FF]"), "ur"),  # Urdu
    (re.compile(r"[\u0900-\u097F]"), "hi"),  # Devanagari (Hindi/Marathi)
]

LANG_NAME_TO_CODE = {
    "tamil": "ta",
    "telugu": "te",
    "hindi": "hi",
    "kannada": "kn",
    "malayalam": "ml",
    "bengali": "bn",
    "marathi": "mr",
    "gujarati": "gu",
    "punjabi": "pa",
    "odia": "or",
    "urdu": "ur",
    "english": "en",
}


@router.get("/tts")
def text_to_speech(text: str = Query(...), lang: Optional[str] = Query(None)):
    """
    Stream high-fidelity MP3 audio for a given sentence/chunk.
    Auto-detects Indian language scripts (Tamil, Telugu, Hindi, etc.)
    and caches audio frames to deliver sub-50ms replays.
    """
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text parameter is required.")

    # 1. Resolve language code: script detection takes precedence
    resolved_lang = "en"
    for pattern, code in SCRIPT_LANG_PATTERNS:
        if pattern.search(cleaned):
            resolved_lang = code
            break
    else:
        if lang:
            normalized = lang.strip().lower()
            resolved_lang = LANG_NAME_TO_CODE.get(normalized, normalized.split("-")[0])

    # Check cache
    cache_key = hashlib.sha256(f"{resolved_lang}:{cleaned}".encode("utf-8")).hexdigest()
    if cache_key in _tts_cache:
        return Response(
            content=_tts_cache[cache_key],
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-TTS-Source": "cache",
            },
        )

    # Truncate to max 180 chars if single utterance exceeds API limit
    query_text = cleaned[:180]
    encoded_query = urllib.parse.quote(query_text)
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl={resolved_lang}&client=tw-ob&q={encoded_query}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="Upstream TTS failed")
            audio_bytes = response.read()

        # Cache eviction if full
        if len(_tts_cache) >= MAX_TTS_CACHE_SIZE:
            # Drop an arbitrary key
            _tts_cache.pop(next(iter(_tts_cache)))

        _tts_cache[cache_key] = audio_bytes

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-TTS-Source": "upstream",
            },
        )
    except Exception as e:
        logger.warning(f"TTS fetch failed for '{cleaned[:30]}...': {e}")
        raise HTTPException(status_code=502, detail=f"TTS service unavailable: {e}")

