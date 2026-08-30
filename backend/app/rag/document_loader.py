"""
Loads a PDF and extracts per-page raw text using PyMuPDF, plus lightweight
document-type detection so the parser_router can pick the right parser.
"""
import os
import re
from typing import List, Dict


def extract_pages(pdf_path: str) -> List[str]:
    """Return a list of raw text strings, one per page."""
    import fitz  # PyMuPDF (imported lazily so this module is testable without it)
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return pages


def detect_document_type(pages: List[str], filename: str) -> str:
    """
    Heuristic document-type detection used to route to the correct parser.
    Looks at the first few pages and the filename.
    """
    sample = "\n".join(pages[:5]).lower()
    fname = filename.lower()

    if "constitution of india" in sample or "constitution" in fname:
        return "constitution"

    judgment_markers = ["versus", " vs. ", " vs ", "appellant", "respondent", "judgment", "bench:"]
    if any(m in sample for m in judgment_markers) and ("court" in sample):
        return "judgment"

    if re.search(r"\brules?\b.*\bregulations?\b", sample) or "rules" in fname:
        return "rules"

    if re.search(r"\bact,?\s*\d{4}\b", sample) or "act" in fname:
        return "act"

    return "generic"


def detect_toc_pages(pages: List[str]) -> set:
    """
    Identify pages that are Table-of-Contents pages so downstream parsing can
    tag entries found there as TOC (never actual_law), and optionally exclude
    them from chunking.

    Heuristic: a page is TOC-like if a large fraction of its non-empty lines
    are short "<number>." lines or "<number>. <title>" lines with NO em-dash
    and no legal body text (no "shall", "means", etc. in long sentences).
    """
    toc_pages = set()
    for idx, text in enumerate(pages):
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            continue
        numbered = [ln for ln in lines if re.match(r"^\d{1,4}[A-Z]?\.$", ln) or
                    re.match(r"^\d{1,4}[A-Z]?\.\s+\S", ln)]
        has_em_dash_body = any("—" in ln and len(ln) > 60 for ln in lines)
        ratio = len(numbered) / max(len(lines), 1)
        if ratio > 0.5 and not has_em_dash_body:
            toc_pages.add(idx)
    return toc_pages


def load_document(pdf_path: str) -> Dict:
    filename = os.path.basename(pdf_path)
    pages = extract_pages(pdf_path)
    doc_type = detect_document_type(pages, filename)
    toc_pages = detect_toc_pages(pages)
    return {
        "filename": filename,
        "document_id": re.sub(r"[^a-z0-9_]+", "_", os.path.splitext(filename)[0].lower()).strip("_"),
        "pages": pages,
        "document_type": doc_type,
        "toc_pages": toc_pages,
    }
