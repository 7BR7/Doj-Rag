"""
Parser for Bare Acts / Legal Acts: extracts Chapters -> Sections -> Subsections.

Typical Indian Act formatting:
    CHAPTER II
    GENERAL EXPLANATIONS

    4. Punishment of offences committed within India.—...

Sections follow the same "<num>. <Title>.—<body>" convention as Constitution
Articles, so we reuse the same anchor strategy but label the field "section"
instead of "article", and track CHAPTER (no PART) headings.
"""
import re
from typing import List, Dict

CHAPTER_RE = re.compile(r"^CHAPTER\s+([IVXLCDM]+[A-Z]?)\b[\s:.\-]*(.*)$", re.IGNORECASE)
# Same not-preceded-by-a-digit guard as the constitution parser, so a stray
# "2015." (e.g. in "...Act, 2015.—Explanation...") can't have its last digits
# misread as a section number, while still allowing bracket-prefixed,
# amendment-inserted sections like "[4A. Explanation.—...".
SECTION_ANCHOR_RE = re.compile(
    r"(?<!\d)(?P<num>\d{1,4}[A-Z]?)\.\s+(?P<title>[A-Z][^\n]{2,180}?)\.\s*[—\-]{1,2}\s*",
)


def _page_boundaries(pages: List[str]):
    full_text_parts, offsets, cursor = [], [], 0
    for page_num, text in enumerate(pages, start=1):
        offsets.append((cursor, page_num))
        full_text_parts.append(text)
        cursor += len(text) + 1
    return "\n".join(full_text_parts), offsets


def _offset_to_page(offset: int, offsets) -> int:
    page = offsets[0][1]
    for start, pnum in offsets:
        if start <= offset:
            page = pnum
        else:
            break
    return page


def _track_chapters(pages: List[str], toc_pages: set):
    markers, current_chapter, cursor = [], None, 0
    for page_idx, text in enumerate(pages):
        if page_idx in toc_pages:
            cursor += len(text) + 1
            continue
        for line in text.split("\n"):
            m = CHAPTER_RE.match(line.strip())
            if m:
                title = m.group(2).strip()
                current_chapter = f"CHAPTER {m.group(1).upper()}" + (f" — {title}" if title else "")
                markers.append((cursor, current_chapter))
            cursor += len(line) + 1
        cursor += 1
    return markers


def _chapter_at(offset: int, markers):
    chapter = None
    for m_off, m_chap in markers:
        if m_off <= offset:
            chapter = m_chap
        else:
            break
    return chapter


def _extract_act_name(pages: List[str]) -> str:
    for text in pages[:3]:
        m = re.search(r"THE\s+[A-Z][A-Z \-,'&]{5,100}ACT,?\s*\d{4}", text)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()
    return "Legal Act"


def parse_act(document_id: str, document_name: str, pages: List[str],
              toc_pages: set) -> List[Dict]:
    full_text, offsets = _page_boundaries(pages)
    chapter_markers = _track_chapters(pages, toc_pages)
    act_name = _extract_act_name(pages)

    anchors = list(SECTION_ANCHOR_RE.finditer(full_text))
    sections, seen = [], {}

    for i, m in enumerate(anchors):
        start_offset = m.start()
        page_num = _offset_to_page(start_offset, offsets)
        if (page_num - 1) in toc_pages:
            continue

        num = m.group("num")
        title = re.sub(r"\s+", " ", m.group("title")).strip()
        body_start = m.end()
        body_end = anchors[i + 1].start() if i + 1 < len(anchors) else len(full_text)
        body = full_text[body_start:body_end].strip()
        if len(body) < 15:
            continue

        end_page = _offset_to_page(body_start + len(body) - 1, offsets)
        chapter = _chapter_at(start_offset, chapter_markers)

        section = {
            "number": num,
            "title": title,
            "body": body,
            "chapter": chapter,
            "act_name": act_name,
            "page_start": page_num,
            "page_end": end_page,
            "source_type": "actual_law",
            "document_id": document_id,
            "document_name": document_name,
            "document_type": "act",
        }

        # Sections are numbered sequentially and don't legitimately restart
        # mid-document the way Schedule paragraphs do in the Constitution -
        # but we still guard against duplicate anchors (e.g. cross-references
        # that happen to match) by keeping the first (chronologically
        # earliest / most complete) genuine occurrence.
        if num not in seen:
            seen[num] = len(sections)
            sections.append(section)

    return sections
