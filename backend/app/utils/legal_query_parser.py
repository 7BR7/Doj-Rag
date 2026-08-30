"""
Deterministic (regex-based) legal query understanding.

We NEVER call an LLM just to detect "Article 21" - that's slow, expensive,
and unreliable. Regex handles this reliably and instantly.
"""
import re
from typing import Optional, Dict

ARTICLE_RE = re.compile(r"\barticle\s*[-:]?\s*(\d{1,3}[A-Za-z]?)\b", re.IGNORECASE)
SECTION_RE = re.compile(r"\bsection\s*[-:]?\s*(\d{1,4}[A-Za-z]?)\b", re.IGNORECASE)
RULE_RE = re.compile(r"\brule\s*[-:]?\s*(\d{1,4}[A-Za-z]?)\b", re.IGNORECASE)
CHAPTER_RE = re.compile(r"\bchapter\s*[-:]?\s*([IVXLCDM\d]{1,6})\b", re.IGNORECASE)

# A handful of common Act name patterns (extendable)
ACT_NAME_RE = re.compile(
    r"\b((?:indian\s+)?[a-z][a-z ,'&]{3,60}act,?\s*\d{4})\b", re.IGNORECASE
)

CONSTITUTION_HINT_RE = re.compile(r"\bconstitution\b", re.IGNORECASE)


def parse_legal_query(message: str) -> Dict:
    """
    Returns a structured intent, e.g.:
      {"query_type": "article", "number": "21", "document_hint": "constitution"}
      {"query_type": "section", "number": "302", "document_hint": None}
      {"query_type": "general", "number": None, "document_hint": None}
    """
    text = message.strip()

    art_m = ARTICLE_RE.search(text)
    if art_m:
        return {
            "query_type": "article",
            "number": art_m.group(1).upper(),
            "document_hint": "constitution",
            "act_name": None,
        }

    sec_m = SECTION_RE.search(text)
    if sec_m:
        act_m = ACT_NAME_RE.search(text)
        return {
            "query_type": "section",
            "number": sec_m.group(1).upper(),
            "document_hint": "act",
            "act_name": act_m.group(1).strip() if act_m else None,
        }

    rule_m = RULE_RE.search(text)
    if rule_m:
        return {
            "query_type": "rule",
            "number": rule_m.group(1).upper(),
            "document_hint": "rules",
            "act_name": None,
        }

    chap_m = CHAPTER_RE.search(text)
    if chap_m and (ARTICLE_RE.search(text) is None):
        return {
            "query_type": "chapter",
            "number": chap_m.group(1).upper(),
            "document_hint": "constitution" if CONSTITUTION_HINT_RE.search(text) else None,
            "act_name": None,
        }

    return {"query_type": "general", "number": None, "document_hint": None, "act_name": None}
