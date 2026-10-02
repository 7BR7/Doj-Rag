"""
NLP Analysis endpoint: POST /api/nlp/analyze

Returns named entities, detected intent, and query decomposition for a query.
Used by the frontend to show entity highlights and intent badges on queries.
No auth required (read-only, stateless).
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/nlp", tags=["nlp"])
logger = logging.getLogger("doj_rag.routes.nlp")


class AnalyzeRequest(BaseModel):
    text: str


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    """
    Analyzes a user query and returns:
    - entities: legal NER results
    - intent: detected intent category
    - sub_queries: decomposed sub-queries (if multi-part)
    - normalized: abbreviation-expanded version of the query
    """
    if not req.text.strip():
        return {"entities": {}, "intent": "GENERAL", "sub_queries": [], "normalized": ""}

    try:
        from app.nlp.nlp_pipeline import extract_legal_entities, detect_intent, decompose_query, normalize_query
        entities = extract_legal_entities(req.text)
        intent = detect_intent(req.text)
        sub_queries = decompose_query(req.text)
        normalized = normalize_query(req.text)
        return {
            "entities": entities,
            "intent": intent,
            "sub_queries": sub_queries if len(sub_queries) > 1 else [],
            "normalized": normalized if normalized != req.text else "",
        }
    except Exception as e:
        logger.error("NLP analysis error: %s", e)
        return {"entities": {}, "intent": "GENERAL", "sub_queries": [], "normalized": "", "error": str(e)}


@router.get("/graph/summary")
def graph_summary():
    """Returns knowledge graph statistics."""
    try:
        from app.nlp.knowledge_graph import get_graph_summary
        return get_graph_summary()
    except Exception as e:
        logger.error("Graph summary error: %s", e)
        return {"error": str(e)}


@router.get("/graph/related")
def graph_related(node_type: str, identifier: str, hops: int = 2):
    """Returns provisions related to the given node in the knowledge graph."""
    try:
        from app.nlp.knowledge_graph import get_related_provisions
        related = get_related_provisions(node_type, identifier, max_hops=hops)
        return {"related": related}
    except Exception as e:
        logger.error("Graph related error: %s", e)
        return {"related": [], "error": str(e)}
