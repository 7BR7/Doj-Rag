"""
The core retrieval pipeline. Implements the required priority order:

  1. EXACT legal identifier match (MongoDB metadata lookup) — highest priority,
     FAISS/BM25 can never override a verified exact match.
  2. BM25 keyword search
  3. FAISS semantic search
  4. Hybrid merge (reciprocal rank fusion) for general questions
  5. Knowledge Graph augmentation — when an exact article is found, also fetch
     its related provisions (sibling articles, concepts it enables, etc.)
  6. Query decomposition — if the user asks about multiple articles,
     each is retrieved independently and merged

Also implements RapidFuzz-based typo/invalid-reference handling: if an exact
match for "Article 212" doesn't exist, it looks for close numeric neighbors
and either suggests one match, asks the user to disambiguate between several,
or reports "not found" — it never silently guesses.
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
ACT_DOCUMENT_IDS = {"BNS": "bns", "BNSS": "bnss", "BSA": "bsa"}


def _exact_lookup(query_type: str, number: str, act_name: Optional[str] = None) -> List[Dict]:
    field = FIELD_BY_TYPE.get(query_type)
    if not field:
        return []
    filters = {field: number, "source_type": "actual_law"}
    if act_name and act_name.upper() in ACT_DOCUMENT_IDS:
        filters["document_id"] = ACT_DOCUMENT_IDS[act_name.upper()]
    cursor = chunks_col().find(filters).sort("child_index", 1)
    return list(cursor)


def _available_numbers(query_type: str, document_hint: Optional[str],
                       act_name: Optional[str] = None) -> List[str]:
    field = FIELD_BY_TYPE.get(query_type)
    if not field:
        return []
    filt = {field: {"$ne": None}, "source_type": "actual_law"}
    if document_hint:
        filt["document_type"] = document_hint
    if act_name and act_name.upper() in ACT_DOCUMENT_IDS:
        filt["document_id"] = ACT_DOCUMENT_IDS[act_name.upper()]
    return list(chunks_col().distinct(field, filt))


def retrieve_exact_or_suggest(message: str) -> Dict:
    """
    Handles Priority-1 exact identifier retrieval + fuzzy fallback.

    Returns one of:
      {"mode": "exact",    "chunks": [...]}
      {"mode": "clarify",  "suggestions": [...], "query_type": "...", "number": "..."}
      {"mode": "not_found","query_type": "...", "number": "..."}
      {"mode": "none"}   # query wasn't a specific-identifier query at all
    """
    intent = parse_legal_query(message)
    if intent["query_type"] not in ("article", "section", "rule"):
        return {"mode": "none", "intent": intent}

    chunks = _exact_lookup(intent["query_type"], intent["number"], intent.get("act_name"))
    if chunks:
        if intent["query_type"] == "section" and not intent.get("act_name"):
            act_names = sorted({
                name.upper() for name, document_id in ACT_DOCUMENT_IDS.items()
                if any(chunk.get("document_id") == document_id for chunk in chunks)
            })
            if len(act_names) > 1:
                return {"mode": "clarify_act", "act_names": act_names, "intent": intent}
        return {"mode": "exact", "chunks": chunks, "intent": intent}

    # Not found exactly -> try fuzzy resolution against known numbers
    available = _available_numbers(
        intent["query_type"], intent.get("document_hint"), intent.get("act_name")
    )
    resolution = resolve_ambiguous_reference(intent["number"], available)

    if resolution["status"] == "single_suggestion":
        suggested_chunks = _exact_lookup(
            intent["query_type"], resolution["suggestion"], intent.get("act_name")
        )
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


def _graph_augmented_chunks(query_type: str, number: str, existing_chunk_ids: set) -> List[Dict]:
    """
    Uses the knowledge graph to find related provisions and fetches them.
    Returns additional chunks not already in the existing set.

    This is how asking "What is Article 21?" also surfaces Article 14 and 19
    as related context, improving the quality of the LLM answer.
    """
    try:
        from app.nlp.knowledge_graph import get_related_provisions
        related = get_related_provisions(
            query_type.capitalize(), number,
            max_hops=1,  # only immediate neighbors for targeted retrieval
            max_results=3,
        )
        extra_chunks = []
        for rel in related:
            if rel["node_type"] == "Article":
                chunks = _exact_lookup("article", rel["identifier"])
                for c in chunks:
                    cid = c.get("chunk_id", "")
                    if cid not in existing_chunk_ids:
                        existing_chunk_ids.add(cid)
                        c["_graph_relation"] = rel["relation"]  # annotate with why it's included
                        extra_chunks.append(c)
                        break  # just the first chunk per related article for brevity
        return extra_chunks
    except Exception as e:
        logger.debug("Knowledge graph augmentation skipped: %s", e)
        return []


def hybrid_retrieve(message: str, top_k: int = None) -> List[Dict]:
    """
    Priority 2+3: BM25 + FAISS hybrid retrieval for general legal questions
    (no specific Article/Section/Rule number detected).
    Uses reciprocal rank fusion to merge the two ranked lists.
    """
    # Apply NLP normalization to expand abbreviations before retrieval
    try:
        from app.nlp.nlp_pipeline import normalize_query
        search_message = normalize_query(message)
    except Exception:
        search_message = message

    top_k = top_k or settings.TOP_K_FINAL

    bm25_hits = bm25_search.search(search_message, top_k=settings.TOP_K_BM25)
    query_vec = embeddings.embed_query(search_message)
    faiss_hits = vectorstore.search(query_vec, top_k=settings.TOP_K_FAISS)

    # Reciprocal rank fusion (k=60 is the standard constant)
    k = 60
    scores: Dict[str, float] = {}
    for rank, (cid, _) in enumerate(bm25_hits):
        scores[cid] = scores.get(cid, 0) + 1.0 / (rank + k)
    for rank, (cid, _) in enumerate(faiss_hits):
        scores[cid] = scores.get(cid, 0) + 1.0 / (rank + k)

    ranked_ids = [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    top_ids = ranked_ids[:top_k]

    if not top_ids:
        return []

    docs = list(chunks_col().find({"chunk_id": {"$in": top_ids}}))
    docs_by_id = {d["chunk_id"]: d for d in docs}
    return [docs_by_id[cid] for cid in top_ids if cid in docs_by_id]


def _multi_article_retrieve(query_numbers: List[str], query_type: str) -> List[Dict]:
    """Retrieve chunks for multiple article/section numbers (for decomposed queries)."""
    all_chunks = []
    seen_ids: set = set()
    for number in query_numbers:
        chunks = _exact_lookup(query_type, number)
        for c in chunks:
            cid = c.get("chunk_id", "")
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_chunks.append(c)
    return all_chunks


def retrieve(message: str) -> Dict:
    """
    Top-level entry point used by chat_service. Applies the full priority
    order and returns a normalized result the chat service can turn into
    a response (or a clarification prompt).

    Enhanced with:
      - Knowledge graph augmentation for exact matches
      - Query decomposition for multi-article queries
      - NLP-based query normalization for hybrid retrieval
    """
    # Try query decomposition first — if user asks about multiple articles,
    # retrieve each independently then merge
    try:
        from app.nlp.nlp_pipeline import decompose_query, extract_legal_entities
        sub_queries = decompose_query(message)
        entities = extract_legal_entities(message)

        # If multiple articles detected in one query, do multi-retrieval
        if len(entities.get("articles", [])) > 1:
            all_numbers = entities["articles"]
            chunks = _multi_article_retrieve(all_numbers, "article")
            if chunks:
                return {
                    "mode": "exact",
                    "chunks": chunks,
                    "intent": {"query_type": "article", "number": all_numbers[0],
                               "document_hint": "constitution", "act_name": None},
                    "multi_reference": True,
                }
    except Exception as e:
        logger.debug("NLP decomposition skipped: %s", e)

    exact_result = retrieve_exact_or_suggest(message)

    if exact_result["mode"] in ("exact", "suggested"):
        chunks = exact_result["chunks"]
        intent = exact_result["intent"]

        # Graph augmentation: add related provisions as supplementary context
        existing_ids = {c.get("chunk_id", "") for c in chunks}
        if intent["query_type"] == "article" and intent.get("number"):
            extra = _graph_augmented_chunks("article", intent["number"], existing_ids)
            if extra:
                # Append graph-sourced chunks (they're secondary context, not the primary answer)
                chunks = chunks + extra

        return {
            "mode": exact_result["mode"],
            "chunks": chunks,
            "intent": intent,
            "suggested_number": exact_result.get("suggested_number"),
        }

    if exact_result["mode"] == "clarify":
        return {
            "mode": "clarify",
            "suggestions": exact_result["suggestions"],
            "intent": exact_result["intent"],
            "chunks": [],
        }

    if exact_result["mode"] == "clarify_act":
        return {
            "mode": "clarify_act",
            "act_names": exact_result["act_names"],
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
