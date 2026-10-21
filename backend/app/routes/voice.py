"""
POST /api/transcribe  — Faster-Whisper speech-to-text
GET  /api/tts         — Google Translate TTS with local pyttsx3 fallback
"""
import hashlib
import logging
import re
import subprocess
import sys
import tempfile
import os
from typing import Optional
import urllib.parse
import urllib.request
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Response
from app.models.schemas import TranscribeResponse
from app.services.speech_to_text import transcribe_audio_bytes, TranscriptionError

router = APIRouter(prefix="/api", tags=["voice"])
logger = logging.getLogger("doj_rag.routes.voice")

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB

# ---------------------------------------------------------------------------
# Transcription endpoint
# ---------------------------------------------------------------------------

@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...), language: Optional[str] = Query(None)):
    """
    Accept a WebM/WAV/OGG audio blob and return the transcribed text.

    - ``language``: optional BCP-47 or display-name hint (e.g. "hi", "Hindi", "ta").
      If omitted or "auto", Whisper auto-detects the spoken language.
    - Returns 400 if the file is empty, too large, or speech cannot be detected.
    """
    content = await audio.read()

    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file received.")

    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25MB).")

    try:
        text, detected_code, detected_name = transcribe_audio_bytes(
            content, audio.filename or "audio.webm", language_hint=language
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


# ---------------------------------------------------------------------------
# TTS helpers
# ---------------------------------------------------------------------------

# In-memory TTS audio cache: sha256(lang:text) -> MP3 bytes
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

LANG_NAME_TO_CODE: dict[str, str] = {
    "tamil": "ta", "telugu": "te", "hindi": "hi", "kannada": "kn",
    "malayalam": "ml", "bengali": "bn", "marathi": "mr", "gujarati": "gu",
    "punjabi": "pa", "odia": "or", "urdu": "ur", "english": "en",
}


def _resolve_lang(text: str, lang_hint: Optional[str]) -> str:
    """Return a 2-letter language code: script detection first, then hint, then 'en'."""
    for pattern, code in SCRIPT_LANG_PATTERNS:
        if pattern.search(text):
            return code
    if lang_hint:
        normalized = lang_hint.strip().lower()
        return LANG_NAME_TO_CODE.get(normalized, normalized.split("-")[0][:2])
    return "en"


def _fetch_google_tts(text: str, lang: str, timeout: int = 6) -> bytes:
    """Fetch MP3 from Google Translate TTS. Raises on failure."""
    encoded = urllib.parse.quote(text[:180])
    url = (
        f"https://translate.google.com/translate_tts"
        f"?ie=UTF-8&tl={lang}&client=tw-ob&q={encoded}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise OSError(f"HTTP {resp.status}")
        return resp.read()


def _try_pyttsx3_tts(text: str) -> Optional[bytes]:
    """
    Local TTS fallback using pyttsx3 (Windows SAPI / espeak).
    Returns raw WAV bytes, or None if pyttsx3 is unavailable.
    NOTE: pyttsx3 has very limited Indic language support on Windows.
    This fallback is only for English when the network is unavailable.
    """
    try:
        import pyttsx3  # type: ignore
    except ImportError:
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.save_to_file(text[:300], tmp_path)
        engine.runAndWait()
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            with open(tmp_path, "rb") as f:
                return f.read()
    except Exception as exc:
        logger.debug(f"pyttsx3 fallback failed: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return None


# ---------------------------------------------------------------------------
# TTS endpoint
# ---------------------------------------------------------------------------

@router.get("/tts")
def text_to_speech(text: str = Query(...), lang: Optional[str] = Query(None)):
    """
    Return MP3 audio for the given text chunk.

    - Script auto-detection takes precedence over the ``lang`` query param.
    - Cached in-memory; evicts LRU-style when the cache exceeds 500 entries.
    - Falls back to pyttsx3 local TTS (English only) if Google is unreachable.
    - Returns 502 if no TTS source can produce audio.
    """
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text parameter is required.")

    resolved_lang = _resolve_lang(cleaned, lang)

    # Cache look-up
    cache_key = hashlib.sha256(f"{resolved_lang}:{cleaned}".encode("utf-8")).hexdigest()
    if cache_key in _tts_cache:
        return Response(
            content=_tts_cache[cache_key],
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=86400", "X-TTS-Source": "cache"},
        )

    # Primary: Google Translate TTS
    audio_bytes: Optional[bytes] = None
    tts_source = "upstream"
    try:
        audio_bytes = _fetch_google_tts(cleaned, resolved_lang)
    except Exception as google_exc:
        logger.warning(f"Google TTS failed ('{cleaned[:40]}'…): {google_exc}")

        # Fallback: pyttsx3 local engine (English only; may not produce MP3)
        if resolved_lang == "en":
            wav_bytes = _try_pyttsx3_tts(cleaned)
            if wav_bytes:
                audio_bytes = wav_bytes
                tts_source = "pyttsx3"
                # Return WAV directly since we can't convert without ffmpeg
                return Response(
                    content=wav_bytes,
                    media_type="audio/wav",
                    headers={"Cache-Control": "no-store", "X-TTS-Source": "pyttsx3"},
                )

        if audio_bytes is None:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"TTS unavailable for language '{resolved_lang}'. "
                    "The Google TTS service is unreachable and no local fallback is available. "
                    "The browser's built-in SpeechSynthesis will be used instead."
                ),
            )

    # Store in cache (evict oldest if full)
    if len(_tts_cache) >= MAX_TTS_CACHE_SIZE:
        _tts_cache.pop(next(iter(_tts_cache)))
    _tts_cache[cache_key] = audio_bytes

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400", "X-TTS-Source": tts_source},
    )

