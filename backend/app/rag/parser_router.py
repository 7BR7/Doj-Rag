"""
Routes a loaded document to the correct structure-aware parser based on
its detected document_type, and normalizes each parser's output into a
common "unit" shape consumed by chunker.py.

Common unit shape:
{
  "unit_type": "article" | "section" | "rule" | "paragraph",
  "number": "21",
  "title": "Protection of life and personal liberty",   # may be None
  "body": "full legal text...",
  "part": "PART III",       # constitution only
  "chapter": "CHAPTER I",   # act/constitution
  "document_id": ..., "document_name": ..., "document_type": ...,
  "page_start": ..., "page_end": ...,
  "source_type": "actual_law",
  "extra": {...}  # judgment case fields, act_name, etc.
}
"""
from typing import List, Dict
from app.rag.constitution_parser import parse_constitution
from app.rag.act_parser import parse_act
from app.rag.judgment_parser import parse_judgment


def route_and_parse(document: Dict) -> List[Dict]:
    doc_type = document["document_type"]
    document_id = document["document_id"]
    document_name = document.get("document_name") or document["filename"]
    pages = document["pages"]
    toc_pages = document["toc_pages"]

    if doc_type == "constitution":
        raw_units = parse_constitution(document_id, document_name, pages, toc_pages)
        return [_normalize_constitution(u) for u in raw_units]

    if doc_type in ("act", "rules"):
        raw_units = parse_act(document_id, document_name, pages, toc_pages)
        unit_type = "rule" if doc_type == "rules" else "section"
        return [_normalize_act(u, unit_type) for u in raw_units]

    if doc_type == "judgment":
        raw_units = parse_judgment(document_id, document_name, pages, toc_pages)
        return [_normalize_judgment(u) for u in raw_units]

    # generic fallback: treat as an "act"-like document (best-effort)
    raw_units = parse_act(document_id, document_name, pages, toc_pages)
    if raw_units:
        return [_normalize_act(u, "section") for u in raw_units]

    return _generic_fallback(document)


def _normalize_constitution(u: Dict) -> Dict:
    return {
        "unit_type": "article",
        "number": u["number"],
        "title": u["title"],
        "body": u["body"],
        "part": u.get("part"),
        "chapter": u.get("chapter"),
        "document_id": u["document_id"],
        "document_name": u["document_name"],
        "document_type": u["document_type"],
        "page_start": u["page_start"],
        "page_end": u["page_end"],
        "source_type": u["source_type"],
        "extra": {},
    }


def _normalize_act(u: Dict, unit_type: str) -> Dict:
    return {
        "unit_type": unit_type,
        "number": u["number"],
        "title": u["title"],
        "body": u["body"],
        "part": None,
        "chapter": u.get("chapter"),
        "document_id": u["document_id"],
        "document_name": u["document_name"],
        "document_type": u["document_type"],
        "page_start": u["page_start"],
        "page_end": u["page_end"],
        "source_type": u["source_type"],
        "extra": {"act_name": u.get("act_name")},
    }


def _normalize_judgment(u: Dict) -> Dict:
    return {
        "unit_type": "paragraph",
        "number": u["number"],
        "title": None,
        "body": u["body"],
        "part": None,
        "chapter": None,
        "document_id": u["document_id"],
        "document_name": u["document_name"],
        "document_type": u["document_type"],
        "page_start": None,
        "page_end": None,
        "source_type": u["source_type"],
        "extra": {
            "case_name": u.get("case_name"),
            "court": u.get("court"),
            "judges": u.get("judges"),
            "date": u.get("date"),
        },
    }


def _generic_fallback(document: Dict) -> List[Dict]:
    """Last-resort: chunk generic documents by page, no structural metadata."""
    units = []
    for page_num, text in enumerate(document["pages"], start=1):
        text = text.strip()
        if not text or (page_num - 1) in document["toc_pages"]:
            continue
        units.append({
            "unit_type": "paragraph",
            "number": str(page_num),
            "title": None,
            "body": text,
            "part": None,
            "chapter": None,
            "document_id": document["document_id"],
            "document_name": document.get("document_name") or document["filename"],
            "document_type": document["document_type"],
            "page_start": page_num,
            "page_end": page_num,
            "source_type": "actual_law",
            "extra": {},
        })
    return units
