"""
Document versioning, legal change detection, and diff computation.
Tracks document versions, publication/amendment dates, and section-by-section diffs.
"""
import difflib
import hashlib
from datetime import datetime, timezone
import logging
from typing import List, Dict, Any, Optional
from app.database.mongodb import get_db

logger = logging.getLogger("doj_rag.versioning")


def document_versions_col():
    return get_db().document_versions


def compute_content_hash(text: str) -> str:
    """Computes SHA-256 hash of document or section text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def register_document_version(
    document_id: str,
    document_name: str,
    version: str,
    raw_text: str,
    publication_date: Optional[str] = None,
    effective_date: Optional[str] = None,
    amendment_date: Optional[str] = None,
    source_url: Optional[str] = None,
    status: str = "CURRENT"
) -> Dict[str, Any]:
    """
    Registers a new document version into document_versions collection.
    If a previous version exists, marks it SUPERSEDED.
    """
    col = document_versions_col()
    content_hash = compute_content_hash(raw_text)
    
    # Check if this exact version or hash already exists
    existing = col.find_one({"document_id": document_id, "content_hash": content_hash})
    if existing:
        return existing
        
    # Find previous version
    prev = col.find_one({"document_id": document_id, "status": "CURRENT"})
    prev_version = prev.get("version") if prev else None
    
    if prev:
        col.update_one(
            {"_id": prev["_id"]},
            {"$set": {"status": "SUPERSEDED", "superseded_at": datetime.now(timezone.utc)}}
        )
        
    doc_ver = {
        "document_id": document_id,
        "document_name": document_name,
        "version": version,
        "status": status,
        "publication_date": publication_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "effective_date": effective_date,
        "amendment_date": amendment_date,
        "source_url": source_url,
        "content_hash": content_hash,
        "previous_version": prev_version,
        "text": raw_text,
        "created_at": datetime.now(timezone.utc)
    }
    col.insert_one(doc_ver)
    logger.info(f"Registered version {version} for {document_id}")
    return doc_ver


def get_document_versions(document_id: str) -> List[Dict[str, Any]]:
    col = document_versions_col()
    versions = list(col.find({"document_id": document_id}, {"text": 0}).sort("created_at", 1))
    for v in versions:
        v["_id"] = str(v["_id"])
    return versions


def compare_versions(
    document_id: str,
    version_a: str,
    version_b: str,
    section: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes What Changed between Version A and Version B.
    Returns added lines, modified clauses, removed provisions, and unified diff.
    """
    col = document_versions_col()
    doc_a = col.find_one({"document_id": document_id, "version": version_a})
    doc_b = col.find_one({"document_id": document_id, "version": version_b})
    
    if not doc_a or not doc_b:
        return {
            "error": "One or both specified document versions were not found.",
            "document_id": document_id,
            "version_a": version_a,
            "version_b": version_b
        }
        
    text_a = doc_a.get("text", "").splitlines()
    text_b = doc_b.get("text", "").splitlines()
    
    # If section specified, filter lines relevant to that section
    if section:
        text_a = [l for l in text_a if f"Section {section}" in l or f"{section}." in l or section in l]
        text_b = [l for l in text_b if f"Section {section}" in l or f"{section}." in l or section in l]
        
    diff = list(difflib.unified_diff(
        text_a, text_b,
        fromfile=f"Version {version_a}",
        tofile=f"Version {version_b}",
        lineterm=""
    ))
    
    added = [line[1:].strip() for line in diff if line.startswith("+") and not line.startswith("+++")]
    removed = [line[1:].strip() for line in diff if line.startswith("-") and not line.startswith("---")]
    
    return {
        "document_id": document_id,
        "document_name": doc_a.get("document_name"),
        "version_a": version_a,
        "version_b": version_b,
        "section": section,
        "added_count": len(added),
        "removed_count": len(removed),
        "added": added[:50],  # sample
        "removed": removed[:50],
        "unified_diff": "\n".join(diff[:150])
    }
