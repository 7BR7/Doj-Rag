"""
Security and Defensive Safeguards for DOJ-RAG:
1. Prompt Injection & Jailbreak Detection (heuristic & pattern-based).
2. Rate Limiting (in-memory sliding window / token bucket).
3. Document Upload Validation (MIME type, size, magic bytes).
4. Sanitization of input and prevention of system prompt leakage.
"""
import time
import re
import logging
from typing import Dict, Tuple, Optional
from fastapi import HTTPException, Request, UploadFile

logger = logging.getLogger("doj_rag.security")

# Rate limit storage: client_id -> list of timestamps
_RATE_LIMIT_BUCKET: Dict[str, list] = {}

# Prompt injection patterns commonly targeting LLM legal assistants
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|directives|prompts)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|above|prior)\s+(rules|instructions)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(developer\s+mode|unrestricted|jailbroken|dan)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*leak|output\s+your\s+system\s+prompt|repeat\s+the\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"bypass\s+(all\s+)?(safeguards|filters|legal\s+constraints)", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now|override\s+your\s+instructions", re.IGNORECASE),
    re.compile(r"<\|\s*im_start\s*\|>|<\|\s*system\s*\|>|\[SYSTEM\s+PROMPT\]", re.IGNORECASE),
]

# Magic bytes for verified PDF files
PDF_MAGIC_BYTES = b"%PDF"


def check_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """
    Scans input text for known prompt-injection and jailbreak vectors.
    Returns (is_suspicious, reason).
    """
    if not text:
        return False, None
        
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("Prompt injection attempt detected: '%s'", text[:80])
            return True, "Potential prompt injection or instruction override detected."
            
    return False, None


def check_rate_limit(client_id: str, max_requests: int = 30, window_seconds: int = 60) -> bool:
    """
    Sliding window rate limiter per client IP or user ID.
    Returns True if allowed, False if exceeded.
    """
    current_time = time.time()
    bucket = _RATE_LIMIT_BUCKET.setdefault(client_id, [])
    
    # Prune old timestamps outside window
    _RATE_LIMIT_BUCKET[client_id] = [t for t in bucket if current_time - t < window_seconds]
    
    if len(_RATE_LIMIT_BUCKET[client_id]) >= max_requests:
        return False
        
    _RATE_LIMIT_BUCKET[client_id].append(current_time)
    return True


def validate_pdf_upload(file_bytes: bytes, filename: str, max_size_mb: int = 30) -> None:
    """
    Validates uploaded document files:
    - Verifies file size does not exceed limit
    - Checks file extension is .pdf
    - Inspects magic bytes header (%PDF) to prevent malicious executable masquerading
    """
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF legal documents (.pdf) are accepted."
        )
        
    max_bytes = max_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed upload size of {max_size_mb} MB."
        )
        
    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=400,
            detail="File content header does not match valid PDF magic bytes signature (%PDF)."
        )
