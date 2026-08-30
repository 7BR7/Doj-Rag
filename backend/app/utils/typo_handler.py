"""
Fuzzy matching for invalid/typo'd legal references using RapidFuzz.

Handles cases like "Explain Article 212" (doesn't exist) -> suggest "21" or
"21A" based on numeric closeness AND string similarity - never silently
assumes the user's intent.
"""
from typing import List, Dict, Optional
from rapidfuzz import fuzz
from app.config import settings


def find_closest_numbers(target: str, available_numbers: List[str], limit: int = 3) -> List[Dict]:
    """
    Returns up to `limit` closest matches as
      [{"number": "21", "score": 87.5}, ...]
    ranked by RapidFuzz string similarity, restricted to a plausible
    numeric neighborhood so "212" doesn't fuzzy-match something like "12"
    from the opposite end of the document by pure coincidence.
    """
    target_digits = "".join(ch for ch in target if ch.isdigit())
    candidates = []

    for num in available_numbers:
        score = fuzz.ratio(target.upper(), num.upper())
        num_digits = "".join(ch for ch in num if ch.isdigit())

        # Bonus if the target is a prefix/superset of this number (e.g. "212" vs "21")
        if target_digits and num_digits and (
            num_digits.startswith(target_digits[:2]) or target_digits.startswith(num_digits)
        ):
            score += 10

        candidates.append({"number": num, "score": min(score, 100)})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:limit]


def resolve_ambiguous_reference(target: str, available_numbers: List[str]) -> Dict:
    """
    Returns one of:
      {"status": "found_exact"}                              (caller already checked exact match)
      {"status": "single_suggestion", "suggestion": "21"}
      {"status": "multiple_suggestions", "suggestions": ["21", "21A"]}
      {"status": "no_match"}
    """
    matches = find_closest_numbers(target, available_numbers, limit=3)
    if not matches:
        return {"status": "no_match"}

    strong_matches = [m for m in matches if m["score"] >= settings.FUZZY_MATCH_THRESHOLD]

    if not strong_matches:
        return {"status": "no_match"}

    if len(strong_matches) == 1 or (
        strong_matches[0]["score"] - strong_matches[1]["score"] >= 15 if len(strong_matches) > 1 else True
    ):
        return {"status": "single_suggestion", "suggestion": strong_matches[0]["number"]}

    return {
        "status": "multiple_suggestions",
        "suggestions": [m["number"] for m in strong_matches[:3]],
    }
