"""
PDF text cleaning utilities.

Removes headers/footers/page numbers/duplicate boilerplate that repeat across
pages of Indian legal PDFs (Constitution, Bare Acts, Rules), WITHOUT touching
valid legal text. This runs before structure detection/chunking.
"""
import re
from collections import Counter
from typing import List, Dict

PAGE_NUM_ONLY_RE = re.compile(r"^\s*\d{1,4}\s*$")
ROMAN_NUM_ONLY_RE = re.compile(r"^\s*[ivxlcdm]{1,6}\s*$", re.IGNORECASE)

# Running section headers/footers common in Indian legal PDFs, e.g.
# "(Part III.—Fundamental Rights)" or "[Chapter II.—General Explanations]"
# repeated on every page of that section. These repeat only WITHIN a
# section (a handful of pages), not across the whole document, so the
# global repeated-line ratio below won't catch them - this pattern-based
# check does.
RUNNING_SECTION_HEADER_RE = re.compile(
    r"^[\(\[]?\s*(PART|CHAPTER)\s+[IVXLCDM]+[A-Z]?\s*[.\-—]+\s*[^()\[\]]{0,80}[\)\]]?\s*$",
    re.IGNORECASE,
)


def find_repeated_lines(pages: List[str], min_repeat_ratio: float = 0.4,
                         min_local_repeat: int = 6) -> set:
    """
    Identify boilerplate lines to strip before chunking:
      1. Lines repeating across a large fraction of the WHOLE document
         (document title, "GOVERNMENT OF INDIA", etc.)
      2. Lines matching the running "(Part X.—Title)" / "(Chapter X.—Title)"
         header/footer pattern that repeat at least `min_local_repeat` times
         anywhere in the document (these only repeat within one section, not
         document-wide, so they need a lower absolute threshold rather than
         a document-wide ratio).
    """
    line_counter = Counter()
    total_pages = max(len(pages), 1)

    for page_text in pages:
        lines = {ln.strip() for ln in page_text.split("\n") if ln.strip()}
        for ln in lines:
            if len(ln) < 3:
                continue
            line_counter[ln] += 1

    global_threshold = max(2, int(total_pages * min_repeat_ratio))
    boilerplate = {ln for ln, count in line_counter.items() if count >= global_threshold}

    for ln, count in line_counter.items():
        if count >= min_local_repeat and RUNNING_SECTION_HEADER_RE.match(ln):
            boilerplate.add(ln)

    return boilerplate


def is_page_number_line(line: str) -> bool:
    return bool(PAGE_NUM_ONLY_RE.match(line) or ROMAN_NUM_ONLY_RE.match(line))


def clean_page_text(text: str, boilerplate_lines: set) -> str:
    """
    Remove boilerplate/page-number lines from one page of text.
    Preserves all remaining content (including numbered legal clauses).
    """
    cleaned_lines = []
    prev_blank = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()

        if not line:
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
            continue
        prev_blank = False

        if line in boilerplate_lines:
            continue
        if is_page_number_line(line):
            continue
        # OCR noise: lines that are almost entirely non-alphanumeric junk
        alnum_ratio = sum(c.isalnum() for c in line) / max(len(line), 1)
        if alnum_ratio < 0.15 and len(line) < 40:
            continue

        cleaned_lines.append(raw_line.rstrip())

    return "\n".join(cleaned_lines).strip()


def clean_document_pages(pages: List[str]) -> List[str]:
    """Clean an entire document's pages, removing cross-page boilerplate."""
    boilerplate = find_repeated_lines(pages)
    return [clean_page_text(p, boilerplate) for p in pages]


def dedupe_consecutive_blocks(text: str) -> str:
    """Collapse accidental duplicate paragraphs (common in OCR'd scans)."""
    paragraphs = [p for p in text.split("\n\n")]
    out = []
    last = None
    for p in paragraphs:
        norm = re.sub(r"\s+", " ", p).strip()
        if norm and norm == last:
            continue
        out.append(p)
        last = norm
    return "\n\n".join(out)
