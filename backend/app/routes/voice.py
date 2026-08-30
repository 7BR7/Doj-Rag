"""
POST /api/transcribe
"""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.schemas import TranscribeResponse
from app.services.speech_to_text import transcribe_audio_bytes, TranscriptionError

router = APIRouter(prefix="/api", tags=["voice"])
logger = logging.getLogger("doj_rag.routes.voice")

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...)):
    content = await audio.read()

    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25MB).")

    try:
        text, detected_language = transcribe_audio_bytes(content, audio.filename or "audio.wav")
        return TranscribeResponse(text=text, detected_language=detected_language)
    except TranscriptionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unexpected transcription error")
        raise HTTPException(status_code=500, detail="Failed to process audio.")
