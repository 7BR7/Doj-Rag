"""
Thin wrapper around SentenceTransformers so the rest of the codebase doesn't
depend directly on the library, and the model is loaded exactly once
(singleton) - important given limited RAM on a student laptop.
"""
import os
import logging
from typing import List
import numpy as np
from app.config import settings

# Enforce offline mode so Hugging Face Hub doesn't waste time on network/SSL retries
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logger = logging.getLogger("doj_rag.embeddings")

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        try:
            _model = SentenceTransformer(settings.EMBEDDING_MODEL, local_files_only=True)
        except Exception:
            _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def embed_texts(texts: List[str], batch_size: int = 32) -> np.ndarray:
    """Embed a list of texts, returning a (N, dim) float32 numpy array."""
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 50,
        convert_to_numpy=True,
        normalize_embeddings=True,  # so we can use inner product = cosine similarity
    )
    return embeddings.astype("float32")


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]
