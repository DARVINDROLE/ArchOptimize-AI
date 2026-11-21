"""PDF → clean text per page.

PDF text is messy: every page repeats a header/footer, the table of contents is dot leaders,
and words are split by line-break hyphens. We remove the noise but keep page numbers, so a
citation can link to the exact page.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

MIN_PAGE_CHARS = 200  # pages shorter than this (cover, blank) are skipped
_DOT_LEADER = re.compile(r"\.{5,}")  # table-of-contents lines
_ONLY_NUMBER = re.compile(r"^\s*[ivxlcdm\d]+\s*$", re.IGNORECASE)  # page numbers
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based
    text: str


def _repeated_lines(pages: list[list[str]], share: float = 0.3) -> set[str]:
    """Lines that appear on more than `share` of pages are headers/footers."""
    counts = Counter(line for lines in pages for line in set(lines))
    limit = max(3, int(len(pages) * share))
    return {line for line, n in counts.items() if n >= limit}


def clean_pages(raw_pages: list[str]) -> list[PageText]:
    # NFKC turns typographic ligatures back into letters ("eﬃcient" -> "efficient");
    # without it, embeddings and keyword matches miss those words.
    raw_pages = [unicodedata.normalize("NFKC", page) for page in raw_pages]
    split = [[ln.strip() for ln in page.splitlines() if ln.strip()] for page in raw_pages]
    boilerplate = _repeated_lines(split)
    result: list[PageText] = []
    for number, lines in enumerate(split, start=1):
        kept = [
            ln
            for ln in lines
            if ln not in boilerplate and not _DOT_LEADER.search(ln) and not _ONLY_NUMBER.match(ln)
        ]
        text = _HYPHEN_BREAK.sub(r"\1\2", "\n".join(kept))
        text = re.sub(r"[ \t]+", " ", text).strip()
        if len(text) >= MIN_PAGE_CHARS:
            result.append(PageText(number, text))
    return result


def extract_pages(pdf_path: Path) -> list[PageText]:
    reader = PdfReader(str(pdf_path))
    return clean_pages([page.extract_text() or "" for page in reader.pages])
