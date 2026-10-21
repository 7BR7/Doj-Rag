"""
Intelligent Query Routing and Context Construction Module for DOJ-RAG.

Classifies incoming queries into 4 precise architectural categories:
1. GENERAL_QUERY: General knowledge/chitchat/casual questions that do NOT require legal retrieval.
   -> Answered directly via the LLM with general knowledge. Zero forced/irrelevant PDF context.
2. LEGAL_QUERY: Questions regarding Indian laws, Acts (BNS, BNSS, BSA, etc.), Constitution,
   Judiciary, procedure, court hierarchy, legal remedies, or writs.
   -> Grounded in retrieved legal document chunks, concept retriever, or authoritative corpus.
   -> If authoritative context is unavailable, transparently acknowledges the limitation.
3. PDF_SPECIFIC_QUERY: Questions asking about an uploaded or selected document (e.g. "what does this document say?",
   "summarize this manual", or when document_id is provided).
   -> Retrieved strictly from the specified document or user-uploaded PDF chunks with exact citations.
4. HYBRID_QUERY: Questions connecting an uploaded document/manual with general legal rules or procedural context
   (e.g., "How does this bail application follow the BNSS procedure?").
   -> Synthesizes document-specific evidence with broader legal provisions, clearly distinguishing between the two.
"""
import re
import logging
from typing import Dict, Any, Optional, List
from app.utils.legal_query_parser import is_legal_query, parse_legal_query
from app.utils.chitchat_handler import detect_chitchat

logger = logging.getLogger("doj_rag.query_router")

# Classification types
QUERY_TYPE_GENERAL = "GENERAL_QUERY"
QUERY_TYPE_LEGAL = "LEGAL_QUERY"
QUERY_TYPE_PDF_SPECIFIC = "PDF_SPECIFIC_QUERY"
QUERY_TYPE_HYBRID = "HYBRID_QUERY"

# Regex for document-referencing phrasing
DOCUMENT_REFERENCE_RE = re.compile(
    r"\b(?:this\s+(?:document|pdf|file|manual|upload)|the\s+uploaded\s+(?:document|file|pdf)|in\s+this\s+file|attached\s+pdf|uploaded\s+document)\b|"
    r"(?:इस\s+(?:दस्तावेज़|फ़ाइल|पीडीएफ़)|இந்த\s+(?:ஆவணம்|கோப்பு)|ఈ\s+(?:పత్రం|ఫైల్)|ಈ\s+ದಾಖಲೆ|ഈ\s+രേഖ|এই\s+নথি|આ\s+દસ્તાવેજ|ਇਹ\s+ਦਸਤਾਵੇਜ਼|ଏହି\s+ଦଲିଲ|یہ\s+دستاویز)",
    re.IGNORECASE | re.UNICODE
)

GENERAL_TOPIC_RE = re.compile(
    r"\b(?:weather|recipe|who\s+are\s+you|what\s+is\s+your\s+name|hello|hi|hey|good\s+morning|good\s+evening|"
    r"how\s+are\s+you|tell\s+me\s+a\s+joke|poem|math|translate|capital\s+of|distance\s+between|president\s+of\s+usa)\b",
    re.IGNORECASE
)


def classify_query(
    message: str,
    document_id: Optional[str] = None,
    has_active_upload: bool = False
) -> Dict[str, Any]:
    """
    Intelligently classifies the user's message into one of four routing modes:
    - GENERAL_QUERY
    - LEGAL_QUERY
    - PDF_SPECIFIC_QUERY
    - HYBRID_QUERY
    """
    clean_text = message.strip()
    is_explicit_doc = bool(document_id or has_active_upload)
    has_doc_reference = bool(DOCUMENT_REFERENCE_RE.search(clean_text))
    legal_check = is_legal_query(clean_text)

    # 1. Pure chitchat or meta query
    if detect_chitchat(clean_text) or GENERAL_TOPIC_RE.search(clean_text):
        if not legal_check and not is_explicit_doc and not has_doc_reference:
            return {
                "route": QUERY_TYPE_GENERAL,
                "confidence": 0.95,
                "reason": "Chitchat or general non-legal query",
                "use_retrieval": False
            }

    # 2. Document-specific or Hybrid
    if is_explicit_doc or has_doc_reference:
        if legal_check and ("compare" in clean_text.lower() or "with law" in clean_text.lower() or "statute" in clean_text.lower() or "act" in clean_text.lower()):
            return {
                "route": QUERY_TYPE_HYBRID,
                "confidence": 0.90,
                "reason": "Query links uploaded document with external statutory provisions",
                "use_retrieval": True
            }
        return {
            "route": QUERY_TYPE_PDF_SPECIFIC,
            "confidence": 0.95,
            "reason": "Targeted document inquiry",
            "use_retrieval": True
        }

    # 3. Legal query
    if legal_check:
        return {
            "route": QUERY_TYPE_LEGAL,
            "confidence": 0.92,
            "reason": "Indian constitutional, statutory, or judicial query",
            "use_retrieval": True
        }

    # 4. Default: General query if no legal terms detected
    return {
        "route": QUERY_TYPE_GENERAL,
        "confidence": 0.85,
        "reason": "No legal or document-specific keywords detected; routing as general query",
        "use_retrieval": False
    }
