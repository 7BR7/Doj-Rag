"""
BM25 keyword search over chunk text, persisted to disk alongside FAISS.
"""
import os
import re
import pickle
import logging
from typing import List, Tuple
from rank_bm25 import BM25Okapi
from app.config import settings

logger = logging.getLogger("doj_rag.bm25")

_bm25 = None
_id_map: List[str] = []

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def build_bm25(texts: List[str], chunk_ids: List[str]):
    global _bm25, _id_map
    tokenized_corpus = [_tokenize(t) for t in texts]
    _bm25 = BM25Okapi(tokenized_corpus)
    _id_map = list(chunk_ids)

    with open(settings.BM25_PATH, "wb") as f:
        pickle.dump({"bm25": _bm25, "id_map": _id_map}, f)
    logger.info(f"Built BM25 index with {len(texts)} documents.")


def load_bm25():
    global _bm25, _id_map
    if not os.path.exists(settings.BM25_PATH):
        raise FileNotFoundError(
            "BM25 index not found. Run `python scripts/process_documents.py` first."
        )
    with open(settings.BM25_PATH, "rb") as f:
        data = pickle.load(f)
    _bm25 = data["bm25"]
    _id_map = data["id_map"]
    return _bm25


def get_bm25():
    global _bm25
    if _bm25 is None:
        load_bm25()
    return _bm25


def search(query: str, top_k: int = 8) -> List[Tuple[str, float]]:
    bm25 = get_bm25()
    tokens = _tokenize(query)
    scores = bm25.get_scores(tokens)

    ranked = sorted(zip(_id_map, scores), key=lambda x: x[1], reverse=True)
    ranked = [(cid, s) for cid, s in ranked if s > 0][:top_k]
    return ranked
