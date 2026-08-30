"""
Structure-aware chunking.

Each parsed unit (Article / Section / Rule / Paragraph) becomes ONE logical
parent chunk. If its body is large, it is split into smaller CHILD chunks on
sentence/clause boundaries (never mid-sentence), each inheriting the full
parent metadata plus a child index - so retrieval never returns a meaningless
fragment without knowing which Article/Section it belongs to.

We deliberately avoid naive fixed-size sliding-window chunking of the whole
document: that is what causes retrieval of table-of-contents fragments,
half-sentences, or the wrong Article.
"""
import re
import uuid
from typing import List, Dict

MAX_CHARS_PER_CHUNK = 1200   # keep chunks small enough for the embedding model
MIN_CHARS_TO_SPLIT = 1400    # only split if meaningfully larger than target

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(0-9])")


def _split_into_subchunks(body: str, max_chars: int) -> List[str]:
    if len(body) <= MIN_CHARS_TO_SPLIT:
        return [body]

    sentences = SENTENCE_SPLIT_RE.split(body)
    chunks, current = [], ""
    for sent in sentences:
        if current and len(current) + len(sent) + 1 > max_chars:
            chunks.append(current.strip())
            current = sent
        else:
            current = f"{current} {sent}".strip() if current else sent
    if current:
        chunks.append(current.strip())

    # Merge any tiny trailing fragment into the previous chunk
    if len(chunks) > 1 and len(chunks[-1]) < 120:
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()

    return chunks


def build_chunks(units: List[Dict]) -> List[Dict]:
    """
    Convert normalized parser units into final chunk records ready for
    embedding + MongoDB storage + FAISS/BM25 indexing.
    """
    chunks = []

    for unit in units:
        body = unit["body"]
        sub_bodies = _split_into_subchunks(body, MAX_CHARS_PER_CHUNK)
        total_children = len(sub_bodies)

        for idx, sub_body in enumerate(sub_bodies):
            chunk_id = str(uuid.uuid4())

            # The searchable text includes the title/label so semantic +
            # keyword search both benefit from it, without polluting the
            # "body" field used for the final displayed answer.
            label_bits = []
            if unit["unit_type"] == "article":
                label_bits.append(f"Article {unit['number']}")
            elif unit["unit_type"] == "section":
                label_bits.append(f"Section {unit['number']}")
            elif unit["unit_type"] == "rule":
                label_bits.append(f"Rule {unit['number']}")
            elif unit["unit_type"] == "paragraph" and unit["extra"].get("case_name"):
                label_bits.append(f"Para {unit['number']} of {unit['extra']['case_name']}")

            if unit.get("title"):
                label_bits.append(unit["title"])

            label = " - ".join(label_bits) if label_bits else unit["document_name"]
            searchable_text = f"{label}. {sub_body}" if label else sub_body

            chunks.append({
                "chunk_id": chunk_id,
                "document_id": unit["document_id"],
                "document_name": unit["document_name"],
                "document_type": unit["document_type"],
                "unit_type": unit["unit_type"],
                "part": unit.get("part"),
                "chapter": unit.get("chapter"),
                "article": unit["number"] if unit["unit_type"] == "article" else None,
                "section": unit["number"] if unit["unit_type"] == "section" else None,
                "rule": unit["number"] if unit["unit_type"] == "rule" else None,
                "title": unit.get("title"),
                "text": sub_body,
                "searchable_text": searchable_text,
                "page_start": unit.get("page_start"),
                "page_end": unit.get("page_end"),
                "source_type": unit["source_type"],
                "child_index": idx,
                "total_children": total_children,
                "extra": unit.get("extra", {}),
            })

    return chunks
