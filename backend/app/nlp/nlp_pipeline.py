"""
Advanced NLP pipeline for the DOJ-RAG legal chatbot.

Provides three core capabilities without any external NLP server or paid API:

1. Legal Named Entity Recognition (NER)
   - Extracts mentions of: Acts/Statutes, Articles, Sections, Rules, Chapters,
     Constitutional concepts, Courts, Rights, and Amendment types.
   - Runs entirely with compiled regex — zero latency overhead.

2. Intent Detection
   - Classifies user queries into legal intent categories:
     DEFINITION, RIGHTS, PROCEDURE, COMPARISON, TIMELINE, GENERAL, CHITCHAT
   - Used by the RAG pipeline to tune retrieval and prompting strategy.

3. Query Decomposition
   - Splits complex multi-part legal questions ("What are Articles 14 and 21?
     How do they relate to Article 19?") into atomic sub-queries that can
     each be answered precisely by exact lookup, then the answers merged.

4. Query Rewriting / Normalization
   - Expands common legal abbreviations ("FIR", "PIL", "HC", "SC", "CrPC")
   - Normalises spelling variants

Why this matters:
  - Without NER, the chatbot treated "right to equality" as pure bag-of-words,
    missing constitutional provisions that use the exact phrase.
  - Without intent detection, definition queries and procedural queries got the
    same generic RAG path, producing verbose LLM answers for simple lookups.
  - Without query decomposition, "compare Articles 14 and 21" retrieved
    whichever article happened to score higher, missing the other entirely.
"""
import re
from typing import List, Dict, Optional

# ─── Legal Abbreviation Expansions ───────────────────────────────────────────

LEGAL_EXPANSIONS = {
    r"\bFIR\b": "First Information Report",
    r"\bPIL\b": "Public Interest Litigation",
    r"\bin\s+SC\b|\bat\s+SC\b|\bthe\s+SC\b|\bSC\b": "Supreme Court",
    r"\bin\s+HC\b|\bat\s+HC\b|\bthe\s+HC\b|\bHC\b": "High Court",
    r"\bCJ\b": "Chief Justice",
    r"\bCJI\b": "Chief Justice of India",
    r"\bCrPC\b": "Code of Criminal Procedure",
    r"\bCPC\b": "Code of Civil Procedure",
    r"\bIPC\b": "Indian Penal Code",
    r"\bDPSP\b": "Directive Principles of State Policy",
    r"\bFR\b": "Fundamental Rights",
    r"\bFD\b": "Fundamental Duties",
    r"\bNHRC\b": "National Human Rights Commission",
    r"\bSHRC\b": "State Human Rights Commission",
    r"\bST\b": "Scheduled Tribe",
    r"\bOBC\b": "Other Backward Class",
    r"\bEWS\b": "Economically Weaker Section",
    r"\bCAA\b": "Citizenship Amendment Act",
    r"\bRTI\b": "Right to Information",
    r"\bRTE\b": "Right to Education",
    r"\bWPS\b": "Writ of Prohibition",
}

INTENT_PATTERNS = {
    "DEFINITION": re.compile(
        r"\b(what\s+is|what\s+are|define|meaning\s+of|explain|describe|tell\s+me\s+about"
        r"|what\s+does\s+.{1,30}mean|what\s+do\s+you\s+mean|elaborat|clarif)\b",
        re.IGNORECASE,
    ),
    "RIGHTS": re.compile(
        r"\b(rights?|entitled|can\s+i|am\s+i\s+allowed|fundamental|freedom|liberty|equality"
        r"|protection|guaranteed|constitutional\s+right|my\s+right)\b",
        re.IGNORECASE,
    ),
    "PROCEDURE": re.compile(
        r"\b(how\s+to|how\s+can|steps?\s+to|procedure|process|file|apply|approach|challenge"
        r"|petition|appeal|writ|remedy|enforce|mechanism|lodge\s+a|register\s+a)\b",
        re.IGNORECASE,
    ),
    "COMPARISON": re.compile(
        r"\b(difference\s+between|compare|vs\.?|versus|similar|contrast|distinguish|relation"
        r"between|both\s+articles?|both\s+sections?)\b",
        re.IGNORECASE,
    ),
    "TIMELINE": re.compile(
        r"\b(when\s+was|history|origin|amendment|amended|enacted|came\s+into\s+force|1950|1976"
        r"|added|inserted|repealed|modified|before|after)\b",
        re.IGNORECASE,
    ),
    "PENALTY": re.compile(
        r"\b(penalty|punishment|sentence|fine|imprisonment|offence|offense|violation"
        r"|consequences|liable|culpable|convicted)\b",
        re.IGNORECASE,
    ),
}


# ─── Multi-reference detection ────────────────────────────────────────────────

# Detects queries that reference more than one numbered legal provision
# e.g. "Article 14 and Article 21" or "Articles 14, 19 and 21"
MULTI_ARTICLE_RE = re.compile(
    r"(?:article|art\.?|अनुच्छेद|ఆర్టికల్|அரசியலமைப்பு\s+சரத்து)[s\s]*"
    r"(\d{1,3}[A-Za-z]?)"
    r"(?:\s*(?:,|and|&|తో|और|மற்றும்)\s*"
    r"(?:article|art\.?|अनुच्छेद|ఆర్టికల్)?\s*"
    r"(\d{1,3}[A-Za-z]?))+",
    re.IGNORECASE,
)
NUMBER_IN_QUERY_RE = re.compile(r"\b(\d{1,3}[A-Za-z]?)\b")

MULTI_SECTION_RE = re.compile(
    r"(?:section|sec\.?|धारा|సెక్షన్)[s\s]*(\d{1,4}[A-Za-z]?)"
    r"(?:\s*(?:,|and|&)\s*(?:section|sec\.?)?\s*(\d{1,4}[A-Za-z]?))+",
    re.IGNORECASE,
)

COMPARISON_INDICATORS = re.compile(
    r"\b(difference|compare|vs\.?|versus|contrast|distinguish|both)\b",
    re.IGNORECASE,
)


# ─── Legal NER ───────────────────────────────────────────────────────────────

ACT_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z\s,&']{2,60}Act(?:,?\s*\d{4})?)\b",
    re.UNICODE,
)

COURT_PATTERN = re.compile(
    r"\b(Supreme Court|High Court|District Court|Sessions Court|Magistrate Court"
    r"|Family Court|Labour Court|Consumer Court|NHRC|State Commission)\b",
    re.IGNORECASE,
)

CONSTITUTIONAL_CONCEPT_PATTERN = re.compile(
    r"\b(Fundamental Rights?|Directive Principles?|Fundamental Duties?"
    r"|Preamble|Basic Structure|Emergency|President's Rule|Governor"
    r"|Parliament|Legislature|Judiciary|Executive|Separation of Powers"
    r"|Rule of Law|Equality|Liberty|Fraternity|Justice|Secularism|Socialism"
    r"|Federal|Unitary|Republic|Democratic|Sovereign)\b",
    re.IGNORECASE,
)

WRIT_PATTERN = re.compile(
    r"\b(Habeas Corpus|Mandamus|Certiorari|Prohibition|Quo Warranto)\b",
    re.IGNORECASE,
)


def extract_legal_entities(text: str) -> Dict:
    """
    Extract legal named entities from user query.

    Returns a dict with keys: acts, courts, concepts, writs, articles, sections.
    All values are lists of unique strings found in the text.
    """
    from app.utils.legal_query_parser import normalize_indic_digits

    normalized = normalize_indic_digits(text)

    acts = list({m.group(1).strip() for m in ACT_PATTERN.finditer(normalized)})
    courts = list({m.group(1) for m in COURT_PATTERN.finditer(normalized)})
    concepts = list({m.group(1) for m in CONSTITUTIONAL_CONCEPT_PATTERN.finditer(normalized)})
    writs = list({m.group(1) for m in WRIT_PATTERN.finditer(normalized)})

    # Simple article/section number extraction (supplementing the full parser)
    articles = []
    sections = []
    for m in re.finditer(
        r"\b(?:article|art\.?|अनुच्छेद|ఆర్టికల్)\s*(\d{1,3}[A-Za-z]?)\b",
        normalized, re.IGNORECASE
    ):
        articles.append(m.group(1).upper())
    for m in re.finditer(
        r"\b(?:section|sec\.?|धारा)\s*(\d{1,4}[A-Za-z]?)\b",
        normalized, re.IGNORECASE
    ):
        sections.append(m.group(1).upper())

    return {
        "acts": acts,
        "courts": courts,
        "concepts": concepts,
        "writs": writs,
        "articles": list(dict.fromkeys(articles)),  # unique, preserve order
        "sections": list(dict.fromkeys(sections)),
    }


# ─── Intent Detection ─────────────────────────────────────────────────────────

def detect_intent(text: str) -> str:
    """
    Returns the dominant intent category:
      DEFINITION | RIGHTS | PROCEDURE | COMPARISON | TIMELINE | PENALTY | GENERAL
    """
    # Score each intent by number of pattern matches
    scores = {}
    for intent, pattern in INTENT_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            scores[intent] = len(matches)

    if not scores:
        return "GENERAL"

    # Comparison gets priority if detected alongside anything else
    if "COMPARISON" in scores:
        return "COMPARISON"

    return max(scores, key=scores.get)


# ─── Query Decomposition ──────────────────────────────────────────────────────

def decompose_query(text: str) -> List[str]:
    """
    Splits a complex multi-part query into atomic sub-queries.

    Examples:
      "What are Articles 14 and 21?" -> ["What is Article 14?", "What is Article 21?"]
      "Compare Articles 19 and 21"  -> ["What is Article 19?", "What is Article 21?",
                                         "Compare Article 19 and Article 21"]

    Returns a list with either:
      - The original query (unchanged) if it's already atomic
      - Multiple atomic sub-queries + optionally a synthesis query
    """
    from app.utils.legal_query_parser import normalize_indic_digits
    normalized = normalize_indic_digits(text.strip())

    # Find all article numbers in the query
    article_matches = list(re.finditer(
        r"\b(?:article|art\.?|अनुच्छेद|ఆర్టికల్|அரசியலமைப்பு\s+சரத்து)"
        r"\s*(\d{1,3}[A-Za-z]?)\b",
        normalized, re.IGNORECASE
    ))

    # Also catch "Articles 14 and 21" pattern (number list after one keyword)
    comma_article_match = re.search(
        r"\b(?:articles?|art\.?)\s+(\d{1,3}[A-Za-z]?)(?:\s*,\s*(\d{1,3}[A-Za-z]?))*"
        r"(?:\s+and\s+(\d{1,3}[A-Za-z]?))?",
        normalized, re.IGNORECASE
    )
    extra_numbers = []
    if comma_article_match:
        # Extract all number groups from this match
        raw_match = comma_article_match.group(0)
        extra_numbers = [n.upper() for n in NUMBER_IN_QUERY_RE.findall(raw_match)]

    all_articles = list(dict.fromkeys(
        [m.group(1).upper() for m in article_matches] + extra_numbers
    ))

    # Find all section numbers
    section_matches = list(re.finditer(
        r"\b(?:section|sec\.?|धारा)\s*(\d{1,4}[A-Za-z]?)\b",
        normalized, re.IGNORECASE
    ))
    all_sections = list(dict.fromkeys([m.group(1).upper() for m in section_matches]))

    # If only one entity referenced, it's already atomic
    if len(all_articles) <= 1 and len(all_sections) <= 1:
        return [text]

    sub_queries = []

    # Generate atomic lookup queries for each article
    for art_num in all_articles:
        sub_queries.append(f"What is Article {art_num} of the Indian Constitution?")

    # Generate atomic lookup queries for each section
    for sec_num in all_sections:
        sub_queries.append(f"What does Section {sec_num} say?")

    # If it's a comparison, add the original query as a synthesis step
    if COMPARISON_INDICATORS.search(normalized) and len(all_articles) > 1:
        sub_queries.append(text)  # original complex query as final synthesis

    return sub_queries if sub_queries else [text]


# ─── Query Normalization ──────────────────────────────────────────────────────

def normalize_query(text: str) -> str:
    """
    Expands legal abbreviations and normalises common spelling variants.
    Applied before retrieval to improve BM25/FAISS recall.
    """
    result = text
    for pattern, expansion in LEGAL_EXPANSIONS.items():
        result = re.sub(pattern, expansion, result)
    # Common spelling variants
    result = re.sub(r"\bfundamental right\b", "fundamental rights", result, flags=re.IGNORECASE)
    result = re.sub(r"\bbasic structure doctrin\b", "basic structure doctrine", result, flags=re.IGNORECASE)
    return result
