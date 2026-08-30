"""
Faster-Whisper based speech-to-text. Model is loaded once (singleton).
"""
import logging
import tempfile
import os
from typing import Tuple
from app.config import settings

logger = logging.getLogger("doj_rag.stt")

_model = None


class TranscriptionError(Exception):
    pass


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info(f"Loading Whisper model: {settings.WHISPER_MODEL}")
        _model = WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe_audio_bytes(audio_bytes: bytes, filename_hint: str = "audio.wav") -> Tuple[str, str]:
    """
    Saves the uploaded audio to a temp file and transcribes it.
    Returns (text, detected_language).
    """
    if not audio_bytes:
        raise TranscriptionError("Empty audio file received.")

    suffix = os.path.splitext(filename_hint)[1] or ".wav"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        model = get_model()
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()

        if not text:
            raise TranscriptionError("Could not detect any speech in the audio.")

        return text, info.language
    except TranscriptionError:
        raise
    except Exception as e:
        logger.exception("Transcription failed")
        raise TranscriptionError(f"Failed to transcribe audio: {e}") from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
