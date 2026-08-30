"""
Parser for court judgments. Judgment PDFs are far less structurally uniform
than Acts/the Constitution, so this parser extracts what it reliably can via
heuristics and otherwise falls back to numbered-paragraph chunking.
"""
import re
from typing import List, Dict, Optional

COURT_RE = re.compile(r"(SUPREME COURT OF INDIA|HIGH COURT OF [A-Z ]+|DISTRICT COURT[A-Z ]*)", re.IGNORECASE)
DATE_RE = re.compile(r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|"
                      r"August|September|October|November|December)\s*,?\s*\d{4})\b", re.IGNORECASE)
VS_RE = re.compile(r"^(?P<pet>.{2,120}?)\s+(?:V/S|VS\.?|VERSUS)\s+(?P<resp>.{2,120})$", re.IGNORECASE | re.MULTILINE)
JUDGE_RE = re.compile(r"(?:CORAM|BENCH|BEFORE)\s*[:\-]\s*(.+)", re.IGNORECASE)
PARA_ANCHOR_RE = re.compile(r"(?:^|\n)\s*(?P<num>\d{1,3})\.\s+(?=[A-Z(])")


def _extract_header_fields(text_head: str) -> Dict:
    court_m = COURT_RE.search(text_head)
    date_m = DATE_RE.search(text_head)
    vs_m = VS_RE.search(text_head)
    judge_m = JUDGE_RE.search(text_head)

    case_name = None
    if vs_m:
        case_name = f"{vs_m.group('pet').strip()} vs {vs_m.group('resp').strip()}"

    return {
        "court": court_m.group(0).strip() if court_m else None,
        "date": date_m.group(0).strip() if date_m else None,
        "case_name": case_name,
        "judges": judge_m.group(1).strip() if judge_m else None,
    }


def parse_judgment(document_id: str, document_name: str, pages: List[str],
                    toc_pages: set) -> List[Dict]:
    """
    Returns a list of paragraph-level chunk dicts for the judgment, each
    carrying the shared case-level metadata (case_name, court, judges, date).
    """
    full_text = "\n".join(pages)
    header_fields = _extract_header_fields("\n".join(pages[:2]))

    anchors = list(PARA_ANCHOR_RE.finditer(full_text))
    paragraphs = []

    if len(anchors) < 3:
        # Not enough numbered-paragraph structure detected; fall back to
        # splitting on blank lines / page breaks as coarse paragraphs.
        raw_paras = [p.strip() for p in full_text.split("\n\n") if len(p.strip()) > 80]
        for i, p in enumerate(raw_paras, start=1):
            paragraphs.append({
                "number": str(i),
                "body": p,
                **header_fields,
                "source_type": "actual_law",
                "document_id": document_id,
                "document_name": document_name,
                "document_type": "judgment",
            })
        return paragraphs

    for i, m in enumerate(anchors):
        num = m.group("num")
        start = m.end()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(full_text)
        body = full_text[start:end].strip()
        if len(body) < 30:
            continue
        paragraphs.append({
            "number": num,
            "body": body,
            **header_fields,
            "source_type": "actual_law",
            "document_id": document_id,
            "document_name": document_name,
            "document_type": "judgment",
        })

    return paragraphs
