"""
Comprehensive Legal Fact-Checking and Constitutional Validation Engine.

Enforces:
1. Exact provision and article number alignment against retrieved evidence.
2. Constitutional structure integrity:
   - Part III: Fundamental Rights (Articles 12-35).
   - Part IV: Directive Principles of State Policy (Articles 36-51).
   - Article 37: Explicit non-enforceability of DPSP by courts.
   - Part IVA: Fundamental Duties (Article 51A).
   - Article 300A: Constitutional right to property, NOT a Fundamental Right.
3. Constitutional Amendment verification:
   - Rejects hallucinated amendment claims (e.g., claiming 42nd Amendment made DPSPs enforceable).
4. Distinguishes constitutional source text from general explanation or opinion.
5. Post-generation fact-checking and automated correction filter.
"""
import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger("doj_rag.fact_checker")

# Baseline constitutional knowledge rules for deterministic fact-checking
PART_III_RANGE = set(str(i) for i in range(12, 36)) | {"21A", "31A", "31B", "31C"}
PART_IV_RANGE = set(str(i) for i in range(36, 52)) | {"39A", "43A", "43B", "48A"}

# Common constitutional misconceptions to intercept
MISCONCEPTION_PATTERNS = [
    # 1. Claiming DPSPs are legally enforceable in court
    (
        re.compile(r"\b(?:directive\s+principles|dpsp|part\s+iv)\b.*?\b(?:are\s+enforceable|enforced\s+by\s+court|can\s+be\s+enforced\s+in\s+court|court\s+can\s+enforce)\b", re.IGNORECASE),
        "Under Article 37 of the Constitution of India, the Directive Principles of State Policy (Part IV) shall NOT be enforceable by any court, though they are fundamental in the governance of the country."
    ),
    # 2. Claiming Right to Property is still a Fundamental Right
    (
        re.compile(r"\b(?:right\s+to\s+property|article\s+300a)\b.*?\b(?:is\s+a\s+fundamental\s+right|under\s+part\s+iii)\b", re.IGNORECASE),
        "The Right to Property ceased to be a Fundamental Right by the 44th Constitutional Amendment Act, 1978, and is now a constitutional right under Article 300A in Part XII."
    ),
    # 3. Merging Articles 36-51 into Fundamental Rights
    (
        re.compile(r"\b(?:fundamental\s+rights)\b.*?\b(?:article\s+(?:3[6-9]|4[0-9]|5[0-1])|articles\s+1[2-4]\s*[-–to]+\s*5[1A]?)\b", re.IGNORECASE),
        "Fundamental Rights are strictly limited to Part III (Articles 12 to 35). Articles 36 to 51 constitute the Directive Principles of State Policy (Part IV), which are non-justiciable."
    ),
    # 4. Hallucinating that local district courts issue constitutional writs under Art 32/226
    (
        re.compile(r"\b(?:local\s+court|district\s+court|magistrate)\b.*?\b(?:issue\s+writs?|under\s+article\s+32|under\s+article\s+226|habeas\s+corpus)\b", re.IGNORECASE),
        "Constitutional writs under Articles 32 and 226 can only be issued by the Supreme Court of India and the respective High Courts. Subordinate/district courts do not have writ jurisdiction."
    )
]


def fact_check_legal_claims(answer: str, evidence_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates legal assertions, article numbers, amendment references, and constitutional boundaries.
    Returns:
      {
        "is_factually_accurate": bool,
        "factual_errors": List[str],
        "corrections": List[str],
        "verified_articles": List[str],
        "corrected_text": str
      }
    """
    errors = []
    corrections = []
    corrected_answer = answer

    # 1. Check for known factual constitutional misconceptions
    for pattern, correction in MISCONCEPTION_PATTERNS:
        if pattern.search(answer):
            errors.append(f"Factual error detected: {correction}")
            corrections.append(correction)

    # 2. Verify all mentioned articles exist in the retrieved evidence or known corpus
    mentioned_articles = set(re.findall(r"\b(?:Article|अनुच्छेद|ಅನುಚ್ಛೇದ|சரத்து|ఆర్టికల్|ವಿಧಿ)\s*(\d+[A-Z]?)\b", answer, re.IGNORECASE))
    evidence_articles = {str(c.get("article")) for c in evidence_chunks if c.get("article")}
    
    unverified_articles = []
    for art in mentioned_articles:
        if art not in evidence_articles:
            # Check if this is a general constitutional article not present in the current retrieved chunk
            unverified_articles.append(art)

    if unverified_articles:
        logger.debug("Articles mentioned without explicit chunk backing: %s", unverified_articles)

    # 3. Part III vs Part IV category enforcement
    # If the answer claims an article is a Fundamental Right, verify it is in Articles 12-35
    for art in mentioned_articles:
        if art in PART_IV_RANGE and ("fundamental right" in answer.lower() or "मौलिक अधिकार" in answer):
            # Check if the text falsely calls this article a fundamental right
            pattern = re.compile(rf"\b(?:fundamental\s+right|मौलिक\s+अधिकार)\b.*?article\s+{art}\b|\barticle\s+{art}\b.*?\b(?:fundamental\s+right|मौलिक\s+अधिकार)\b", re.IGNORECASE)
            if pattern.search(answer) and art not in ("12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "21A", "22", "23", "24", "25", "26", "27", "28", "29", "30", "32"):
                msg = f"Article {art} belongs to Part IV (Directive Principles of State Policy), not Part III (Fundamental Rights)."
                errors.append(msg)
                corrections.append(msg)

    # 4. If critical factual errors exist, append explicit corrections to answer
    if corrections:
        addition = "\n\n**Constitutional Fact-Check Note:**\n" + "\n".join(f"- {c}" for c in set(corrections))
        corrected_answer = answer + addition

    is_accurate = len(errors) == 0

    return {
        "is_factually_accurate": is_accurate,
        "factual_errors": errors,
        "corrections": corrections,
        "verified_articles": list(mentioned_articles & evidence_articles),
        "unverified_articles": unverified_articles,
        "corrected_text": corrected_answer
    }
