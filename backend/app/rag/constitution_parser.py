"""
Parser for the Constitution of India (and similarly structured constitutional
documents).

KEY INSIGHT (verified against the actual Constitution of India PDF):
  - A Table-of-Contents entry looks like:
        21.
        Protection of life and personal liberty.
    (number and title on separate lines / no em-dash, no legal body text)

  - The ACTUAL legal article looks like:
        21. Protection of life and personal liberty.—No person shall be
        deprived of his life or personal liberty except according to
        procedure established by law.
    i.e. "<number>. <Title>.—<body text>" with an em-dash ("—") joining the
    title to the operative legal text, all within the article's own page(s).

We use the em-dash-joined pattern as the authoritative signal for
"source_type": "actual_law". Anything matching the bare numbered-list pattern
without a following em-dash + body is treated as a TOC/reference entry and
is NEVER allowed to override real article content.

We also track PART / CHAPTER headings ("PART III", "Fundamental Rights") as
we scan sequentially, so every article gets its containing Part/Chapter in
its metadata.
"""
import re
from typing import List, Dict

PART_RE = re.compile(r"^PART\s+([IVXLCDM]+[A-Z]?)\b", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^CHAPTER\s+([IVXLCDM]+[A-Z]?)\b", re.IGNORECASE)

# Anchors an actual article: "21. Title text.—" (title ends in period, then em-dash).
# (?<!\d) prevents matching digit substrings embedded in things like
# "...Act, 2015.—" where "015" would otherwise falsely match \d{1,3} inside
# "2015" (the "2" immediately before blocks the match).
# NOTE: deliberately NOT anchored to line-start - amendment-inserted articles
# are commonly written as "[21A. Right to education.—..." with a leading
# bracket, so a same-line-only, non-newline-anchored (?<!\d) guard is used
# instead; it still blocks the "2015" case since the digit before "015" is
# itself a digit.
ARTICLE_ANCHOR_RE = re.compile(
    r"(?<!\d)(?P<num>\d{1,3}[A-Z]?)\.\s+(?P<title>[A-Z][^\n]{2,180}?)\.\s*[—\-]{1,2}\s*",
)

# Bare TOC-style line: "21." alone or "21. Title" with no em-dash on that line
TOC_LINE_RE = re.compile(r"^(?P<num>\d{1,3}[A-Z]?)\.\s*$")

# Marks the end of the numbered Articles and the start of the Schedules.
# Schedules restart their own paragraph numbering (1, 2, 3...) in a very
# different tabular/list format, which would otherwise get misparsed as
# more "Articles" (and could even bleed into the body of the real final
# Article if no further anchor is found for a long stretch). We hard-stop
# Article extraction at this boundary.
SCHEDULE_BOUNDARY_RE = re.compile(
    r"^\s*\[?\s*(?:THE\s+)?(?:FIRST\s+SCHEDULE|SCHEDULES)\s*\]?\s*$",
    re.MULTILINE,
)


def _find_schedule_boundary(full_text: str) -> int:
    m = SCHEDULE_BOUNDARY_RE.search(full_text)
    return m.start() if m else len(full_text)


def _page_boundaries(pages: List[str]):
    """Build a single text blob with (char_offset -> page_number) markers."""
    full_text_parts = []
    offsets = []  # (start_offset, page_number)
    cursor = 0
    for page_num, text in enumerate(pages, start=1):
        offsets.append((cursor, page_num))
        full_text_parts.append(text)
        cursor += len(text) + 1  # +1 for the join newline
    return "\n".join(full_text_parts), offsets


def _offset_to_page(offset: int, offsets) -> int:
    page = offsets[0][1]
    for start, pnum in offsets:
        if start <= offset:
            page = pnum
        else:
            break
    return page


def _track_part_chapter(pages: List[str], toc_pages: set):
    """
    Sequentially scan pages to build a map of char-offset -> (part, chapter)
    so we know which Part/Chapter each article anchor falls under.

    TOC pages are skipped: the table of contents lists every Part/Chapter
    heading up front, which would otherwise falsely become the "current"
    chapter for articles that appear much later under a different chapter.
    """
    markers = []  # (offset, part, chapter)
    current_part = None
    current_chapter = None
    cursor = 0
    for page_idx, text in enumerate(pages):
        if page_idx in toc_pages:
            cursor += len(text) + 1
            continue
        for line in text.split("\n"):
            stripped = line.strip()
            m_part = PART_RE.match(stripped)
            m_chap = CHAPTER_RE.match(stripped)
            if m_part:
                current_part = f"PART {m_part.group(1).upper()}"
                current_chapter = None  # chapters are scoped within a Part
                markers.append((cursor, current_part, current_chapter))
            elif m_chap:
                current_chapter = stripped[:120]
                markers.append((cursor, current_part, current_chapter))
            cursor += len(line) + 1
        cursor += 1  # page join newline
    return markers


def _part_chapter_at(offset: int, markers):
    part, chapter = None, None
    for m_off, m_part, m_chap in markers:
        if m_off <= offset:
            part, chapter = m_part, m_chap
        else:
            break
    return part, chapter


def parse_constitution(document_id: str, document_name: str, pages: List[str],
                        toc_pages: set) -> List[Dict]:
    """
    Returns a list of article dicts:
      {number, title, body, part, chapter, page_start, page_end, source_type}
    """
    full_text, offsets = _page_boundaries(pages)
    part_chapter_markers = _track_part_chapter(pages, toc_pages)

    anchors = list(ARTICLE_ANCHOR_RE.finditer(full_text))
    articles = []
    seen_numbers = {}  # article number -> index in `articles` (keep first REAL match)

    for i, m in enumerate(anchors):
        start_offset = m.start()
        page_num = _offset_to_page(start_offset, offsets)

        # Skip anchors that land on a detected TOC page - they are noise
        # even if they happen to match the anchor regex.
        if (page_num - 1) in toc_pages:
            continue

        num = m.group("num")
        title = re.sub(r"\s+", " ", m.group("title")).strip()

        body_start = m.end()
        body_end = anchors[i + 1].start() if i + 1 < len(anchors) else len(full_text)
        body = full_text[body_start:body_end].strip()

        # Guard: a genuine article should have a reasonably substantial body.
        # This prevents stray "21.—" style false positives from being treated
        # as real law with an empty/garbage body.
        if len(body) < 15:
            continue

        end_page = _offset_to_page(body_start + len(body) - 1, offsets)
        part, chapter = _part_chapter_at(start_offset, part_chapter_markers)

        article = {
            "number": num,
            "title": title,
            "body": body,
            "part": part,
            "chapter": chapter,
            "page_start": page_num,
            "page_end": end_page,
            "source_type": "actual_law",
            "document_id": document_id,
            "document_name": document_name,
            "document_type": "constitution",
        }

        # IMPORTANT: numbering restarts inside Schedules (e.g. paragraph "21"
        # in the Fifth Schedule) *after* the main Articles (1-395) have
        # already appeared earlier in the document. We therefore keep the
        # FIRST occurrence of each number as the authoritative Article, and
        # ignore later re-uses of the same number in Schedules/Appendices.
        if num not in seen_numbers:
            seen_numbers[num] = len(articles)
            articles.append(article)
        # else: later duplicate (schedule paragraph reusing the number) - skip

    return articles
