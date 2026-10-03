"""
Reranking module for Hybrid RAG.
Reranks retrieved candidate chunks from ChromaDB and BM25 using reciprocal rank fusion,
cross-attention scoring heuristics, exact legal provision matching, and entity alignment.
"""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("doj_rag.reranker")


def score_exact_match(chunk: Dict[str, Any], query_entities: Dict[str, Any], query: str) -> float:
    """Computes exact match boost for legal identifiers."""
    boost = 0.0
    
    # 1. Section match
    sections = query_entities.get("sections", [])
    chunk_sec = str(chunk.get("section") or "").strip()
    if chunk_sec and any(s == chunk_sec for s in sections):
        boost += 5.0
        
    # 2. Article match
    articles = query_entities.get("articles", [])
    chunk_art = str(chunk.get("article") or "").strip()
    if chunk_art and any(a == chunk_art for a in articles):
        boost += 5.0
        
    # 3. Act / Document match
    acts = query_entities.get("acts", [])
    doc_name = str(chunk.get("document_name") or "").lower()
    for act in acts:
        if act.lower() in doc_name:
            boost += 3.0
            break
            
    # 4. Source type preference
    if chunk.get("source_type") == "actual_law":
        boost += 1.0
        
    return boost


def rerank_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    query_entities: Optional[Dict[str, Any]] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Reranks candidate chunks using multi-signal scoring:
    - Base retrieval score / position
    - Exact section/article match
    - Legal keyword & entity overlap
    - Document relevance
    """
    if not chunks:
        return []
        
    if query_entities is None:
        try:
            from app.nlp.nlp_pipeline import extract_legal_entities
            query_entities = extract_legal_entities(query)
        except Exception:
            query_entities = {}
            
    query_words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", query.lower()))
    scored = []
    
    for idx, chunk in enumerate(chunks):
        # Initial score based on reciprocal ranking in candidate list
        score = 1.0 / (idx + 1.0)
        
        # Exact match boost
        match_boost = score_exact_match(chunk, query_entities, query)
        score += match_boost
        
        # Word overlap
        content = chunk.get("text", "") or chunk.get("searchable_text", "")
        chunk_words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", content.lower()))
        if query_words and chunk_words:
            overlap = len(query_words.intersection(chunk_words)) / len(query_words)
            score += overlap * 2.0
            
        chunk_copy = dict(chunk)
        chunk_copy["_rerank_score"] = round(score, 4)
        scored.append((score, chunk_copy))
        
    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
