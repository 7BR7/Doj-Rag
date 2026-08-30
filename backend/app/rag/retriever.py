"""
The core retrieval pipeline. Implements the required priority order:

  1. EXACT legal identifier match (MongoDB metadata lookup) - highest priority,
     FAISS/BM25 can never override a verified exact match.
  2. BM25 keyword search
  3. FAISS semantic search
  4. Hybrid merge (dedupe + combine) for general questions

Also implements RapidFuzz-based typo/invalid-reference handling: if an exact
match for "Article 212" doesn't exist, it looks for close numeric neighbors
and either suggests one match, asks the user to disambiguate between several,
or reports "not found" - it never silently guesses.
"""
import logging
from typing import List, Dict, Optional
from app.config import settings
from app.database.mongodb import chunks_col
from app.utils.legal_query_parser import parse_legal_query
from app.utils.typo_handler import resolve_ambiguous_reference
from app.rag import embeddings, vectorstore, bm25_search

logger = logging.getLogger("doj_rag.retriever")

FIELD_BY_TYPE = {"article": "article", "section": "section", "rule": "rule"}


def _exact_lookup(query_type: str, number: str) -> List[Dict]:
    field = FIELD_BY_TYPE.get(query_type)
    if not field:
        return []
    cursor = chunks_col().find({field: number, "source_type": "actual_law"}).sort("child_index", 1)
    return list(cursor)


def _available_numbers(query_type: str, document_hint: Optional[str]) -> List[str]:
    field = FIELD_BY_TYPE.get(query_type)
    if not field:
        return []
    filt = {field: {"$ne": None}, "source_type": "actual_law"}
    if document_hint:
        filt["document_type"] = document_hint
    return list(chunks_col().distinct(field, filt))


def retrieve_exact_or_suggest(message: str) -> Dict:
    """
    Handles Priority-1 exact identifier retrieval + fuzzy fallback.

    Returns one of:
      {"mode": "exact", "chunks": [...]}
      {"mode": "clarify", "suggestions": [...], "query_type": "...", "number": "..."}
      {"mode": "not_found", "query_type": "...", "number": "..."}
      {"mode": "none"}   # query wasn't a specific-identifier query at all
    """
    intent = parse_legal_query(message)
    if intent["query_type"] not in ("article", "section", "rule"):
        return {"mode": "none", "intent": intent}

    chunks = _exact_lookup(intent["query_type"], intent["number"])
    if chunks:
        return {"mode": "exact", "chunks": chunks, "intent": intent}

    # Not found exactly -> try fuzzy resolution against known numbers
    available = _available_numbers(intent["query_type"], intent.get("document_hint"))
    resolution = resolve_ambiguous_reference(intent["number"], available)

    if resolution["status"] == "single_suggestion":
        suggested_chunks = _exact_lookup(intent["query_type"], resolution["suggestion"])
        if suggested_chunks:
            return {
                "mode": "suggested",
                "chunks": suggested_chunks,
                "suggested_number": resolution["suggestion"],
                "intent": intent,
            }

    if resolution["status"] == "multiple_suggestions":
        return {
            "mode": "clarify",
            "suggestions": resolution["suggestions"],
            "intent": intent,
        }

    return {"mode": "not_found", "intent": intent}


def hybrid_retrieve(message: str, top_k: int = None) -> List[Dict]:
    """
    Priority 2+3: BM25 + FAISS hybrid retrieval for general legal questions
    (no specific Article/Section/Rule number detected).
    """
    top_k = top_k or settings.TOP_K_FINAL

    bm25_hits = bm25_search.search(message, top_k=settings.TOP_K_BM25)
    query_vec = embeddings.embed_query(message)
    faiss_hits = vectorstore.search(query_vec, top_k=settings.TOP_K_FAISS)

    # Combine with simple weighted-rank fusion (reciprocal rank fusion)
    scores: Dict[str, float] = {}
    for rank, (cid, _) in enumerate(bm25_hits):
        scores[cid] = scores.get(cid, 0) + 1.0 / (rank + 1)
    for rank, (cid, _) in enumerate(faiss_hits):
        scores[cid] = scores.get(cid, 0) + 1.0 / (rank + 1)

    ranked_ids = [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    top_ids = ranked_ids[:top_k]

    if not top_ids:
        return []

    docs = list(chunks_col().find({"chunk_id": {"$in": top_ids}}))
    docs_by_id = {d["chunk_id"]: d for d in docs}
    return [docs_by_id[cid] for cid in top_ids if cid in docs_by_id]


def retrieve(message: str) -> Dict:
    """
    Top-level entry point used by chat_service. Applies the full priority
    order and returns a normalized result the chat service can turn into
    a response (or a clarification prompt).
    """
    exact_result = retrieve_exact_or_suggest(message)

    if exact_result["mode"] in ("exact", "suggested"):
        return {
            "mode": exact_result["mode"],
            "chunks": exact_result["chunks"],
            "intent": exact_result["intent"],
            "suggested_number": exact_result.get("suggested_number"),
        }

    if exact_result["mode"] == "clarify":
        return {
            "mode": "clarify",
            "suggestions": exact_result["suggestions"],
            "intent": exact_result["intent"],
            "chunks": [],
        }

    if exact_result["mode"] == "not_found":
        return {
            "mode": "not_found",
            "intent": exact_result["intent"],
            "chunks": [],
        }

    # General question -> hybrid retrieval
    chunks = hybrid_retrieve(message)
    return {"mode": "hybrid", "chunks": chunks, "intent": exact_result["intent"]}
