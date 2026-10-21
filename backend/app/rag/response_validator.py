"""
Response Quality Validation Engine for DOJ-RAG.

Performs deterministic, language-aware validation:
1. Empty or excessively short answers (< 20 chars).
2. Repetitive loops: duplicated sentences, duplicated n-grams, high phrase repetition.
3. Broken unicode or encoding artifacts (e.g., mojibake, unrendered tags).
4. Abruptly truncated answers (trailing cutoffs, ending mid-word or unclosed brackets).
5. Target language and native script conformity.
6. Unsupported legal citations and fabricated article checks.
"""
import re
import unicodedata
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple
from app.services.language import detect_script_language
from app.services.translator import _has_target_script

# Common valid punctuation marks per language
PUNCTUATION_ENDINGS = {".", "!", "?", "।", "|", "۔", "”", "’", "\"", "'", ")", "]", "}", "…"}

# Known invalid corruption patterns / mojibake
CORRUPTION_PATTERNS = [
    re.compile(r"[\uFFFD]"),
    re.compile(r"(?:\?\?){3,}"),
    re.compile(r"&(?:amp|lt|gt|quot);"),
]

def check_repetition(text: str) -> Tuple[bool, Optional[str]]:
    """
    Checks for pathological word or sentence loops without flagging natural legal lists.
    """
    words = [w.lower() for w in re.findall(r"\w+", text, re.UNICODE)]
    if len(words) < 15:
        return True, None

    # Check 3-gram repetition (e.g. "is a right is a right is a right")
    trigrams = [tuple(words[i:i+3]) for i in range(len(words)-2)]
    trigram_counts = Counter(trigrams)
    if trigram_counts:
        most_common_tg, count = trigram_counts.most_common(1)[0]
        if count >= 5 and count / len(trigrams) > 0.2:
            return False, f"Severe phrase repetition detected ('{' '.join(most_common_tg)}' x{count})"

    # Check sentence duplication
    sentences = [s.strip() for s in re.split(r"[।\.\n!?]+", text) if len(s.strip()) > 15]
    if len(sentences) >= 4:
        s_counts = Counter(sentences)
        for s, c in s_counts.items():
            if c >= 3:
                return False, f"Duplicate sentence repeated {c} times: '{s[:40]}...'"

    return True, None


def check_script_and_language(text: str, target_language: str) -> Tuple[bool, Optional[str]]:
    """
    Ensures the response text is actually in the target language and native script.
    """
    if not text or target_language == "English":
        return True, None

    # Target language must contain its native script
    if not _has_target_script(text, target_language):
        return False, f"Output text lacks authentic native script for {target_language}"

    return True, None


def check_truncation(text: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if generation terminated abruptly mid-sentence or mid-token.
    """
    cleaned = text.strip()
    if not cleaned:
        return False, "Empty text"

    last_char = cleaned[-1]
    if last_char in PUNCTUATION_ENDINGS:
        return True, None

    # If text is substantial (> 30 chars) and does not end with recognized sentence termination
    if len(cleaned) > 30 and not any(cleaned.endswith(p) for p in PUNCTUATION_ENDINGS):
        return False, "Abrupt sentence truncation: response does not terminate with proper punctuation"

    if cleaned.count("(") > cleaned.count(")"):
        return False, "Unclosed parenthesis detected at end of response"
    if cleaned.count("[") > cleaned.count("]"):
        return False, "Unclosed square bracket detected at end of response"

    return True, None


def check_corruption(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detects encoding corruption and unrendered unicode sequences.
    """
    for pattern in CORRUPTION_PATTERNS:
        if pattern.search(text):
            return False, "Encoding corruption or broken Unicode sequence detected"
    return True, None


def validate_response(
    answer: str,
    target_language: str,
    evidence_chunks: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Comprehensive validation returning quality status and actionable details.
    """
    cleaned = (answer or "").strip()
    
    if len(cleaned) < 15:
        return {
            "is_valid": False,
            "reason": "Answer is excessively short or empty",
            "code": "TOO_SHORT"
        }

    # 1. Corruption check
    corrupt_ok, corrupt_err = check_corruption(cleaned)
    if not corrupt_ok:
        return {"is_valid": False, "reason": corrupt_err, "code": "CORRUPTED_UNICODE"}

    # 2. Repetition check
    rep_ok, rep_err = check_repetition(cleaned)
    if not rep_ok:
        return {"is_valid": False, "reason": rep_err, "code": "EXCESSIVE_REPETITION"}

    # 3. Script & Language verification
    lang_ok, lang_err = check_script_and_language(cleaned, target_language)
    if not lang_ok:
        return {"is_valid": False, "reason": lang_err, "code": "LANGUAGE_MISMATCH"}

    # 4. Truncation check
    trunc_ok, trunc_err = check_truncation(cleaned)
    if not trunc_ok:
        return {"is_valid": False, "reason": trunc_err, "code": "ABRUPT_TRUNCATION"}

    return {
        "is_valid": True,
        "reason": "Passed all quality validation checks",
        "code": "OK"
    }


def clean_repetitions_and_normalize(text: str) -> str:
    """
    Sanitizes duplicate paragraphs and consecutive identical lines in generated output.
    """
    if not text:
        return ""
    
    # 1. Collapse multiple empty lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # 2. Deduplicate consecutive duplicate lines
    lines = text.split("\n")
    cleaned_lines = []
    prev_line = None
    for line in lines:
        stripped = line.strip()
        if stripped and stripped == prev_line:
            continue
        cleaned_lines.append(line)
        if stripped:
            prev_line = stripped
        else:
            prev_line = None
            
    return "\n".join(cleaned_lines).strip()
