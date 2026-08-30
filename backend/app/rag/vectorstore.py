"""
FAISS vector store wrapper. Stores embeddings + a mapping from FAISS row
index -> MongoDB chunk_id, persisted to disk so it doesn't need to be
rebuilt every server restart.
"""
import os
import pickle
import logging
from typing import List, Tuple
import numpy as np
from app.config import settings

logger = logging.getLogger("doj_rag.vectorstore")

_index = None
_id_map: List[str] = []  # row index -> chunk_id


def build_index(embeddings: np.ndarray, chunk_ids: List[str]):
    import faiss
    global _index, _id_map

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors = cosine sim
    index.add(embeddings)

    _index = index
    _id_map = list(chunk_ids)

    faiss.write_index(index, settings.FAISS_INDEX_PATH)
    with open(settings.FAISS_META_PATH, "wb") as f:
        pickle.dump(_id_map, f)

    logger.info(f"Built FAISS index with {index.ntotal} vectors.")


def load_index():
    import faiss
    global _index, _id_map

    if not os.path.exists(settings.FAISS_INDEX_PATH):
        raise FileNotFoundError(
            "FAISS index not found. Run `python scripts/process_documents.py` first."
        )

    _index = faiss.read_index(settings.FAISS_INDEX_PATH)
    with open(settings.FAISS_META_PATH, "rb") as f:
        _id_map = pickle.load(f)
    return _index


def get_index():
    global _index
    if _index is None:
        load_index()
    return _index


def search(query_embedding: np.ndarray, top_k: int = 8) -> List[Tuple[str, float]]:
    """Returns list of (chunk_id, similarity_score), best first."""
    index = get_index()
    query_vec = query_embedding.reshape(1, -1).astype("float32")
    scores, indices = index.search(query_vec, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        results.append((_id_map[idx], float(score)))
    return results
