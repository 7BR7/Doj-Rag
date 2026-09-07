"""
Faster-Whisper based speech-to-text. Model is loaded once (singleton).
"""
import logging
import tempfile
import os
from typing import Tuple, Optional
from app.config import settings
from app.i18n.messages import LANGUAGE_LOCALES

logger = logging.getLogger("doj_rag.stt")

_model = None

NAME_TO_CODE = {name.lower(): info["code"] for name, info in LANGUAGE_LOCALES.items()}
CODE_TO_NAME = {info["code"]: name for name, info in LANGUAGE_LOCALES.items()}


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


def transcribe_audio_bytes(audio_bytes: bytes, filename_hint: str = "audio.wav",
                           language_hint: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Saves the uploaded audio to a temp file and transcribes it.
    Returns (text, detected_language_code, detected_language_name).
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

        # Map language_hint to 2-letter Whisper code if specified
        target_lang = None
        if language_hint and language_hint.lower() not in ("auto", "auto-detect"):
            cleaned = language_hint.strip().lower()
            if cleaned in CODE_TO_NAME:
                target_lang = cleaned
            elif cleaned in NAME_TO_CODE:
                target_lang = NAME_TO_CODE[cleaned]

        segments, info = model.transcribe(
            tmp_path,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
            condition_on_previous_text=False,
            language=target_lang,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()

        if not text:
            raise TranscriptionError("Could not detect any speech in the audio.")

        detected_code = target_lang or info.language or "en"
        detected_name = CODE_TO_NAME.get(detected_code, "English")

        return text, detected_code, detected_name
    except TranscriptionError:
        raise
    except Exception as e:
        logger.exception("Transcription failed")
        raise TranscriptionError(f"Failed to transcribe audio: {e}") from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

