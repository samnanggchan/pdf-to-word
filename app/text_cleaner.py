"""
Text cleaning and post-processing pipeline.

Removes artefacts common in PDF→text conversion:
  • Repeated headers / footers / page numbers
  • Broken line wraps inside paragraphs
  • Duplicate whitespace
  • Stray control characters

Preserves meaningful structure (headings, list markers, blank paragraph breaks).
"""

from __future__ import annotations

import re
from collections import Counter

from app.khmer_utils import normalize_khmer

# ── Regex patterns ───────────────────────────────────────────────────────

# Page-number-like lines: a line that is just digits (optionally with dashes)
_PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")

# Two or more consecutive spaces
_MULTI_SPACE_RE = re.compile(r"[^\S\n]{2,}")

# Lines that are only whitespace
_BLANK_LINE_RE = re.compile(r"^\s+$", re.MULTILINE)

# Common Khmer / English list markers at the start of a line
_LIST_MARKER_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,3}[.)\u00B7]"    # 1. or 1) or 1·
    r"|[-•●◦▪▸►–—]"         # bullet chars
    r"|[A-Za-z][.)]"         # a. or a)
    r"|[\u17E0-\u17E9]+[.)]" # Khmer digit list marker
    r")\s"
)

# Heuristic: a "short" line that doesn't end with sentence-ending punctuation
# is probably a broken wrap.
_SENTENCE_ENDERS = re.compile(r"[.!?\u17D4\u17D5។៕]\s*$")

# ── Header / Footer detection ───────────────────────────────────────────


def _detect_repeated_lines(pages_text: list[str], threshold: int = 2) -> set[str]:
    """
    Find lines that appear verbatim on at least *threshold* pages,
    positioned in the first or last 3 lines of a page — these are likely
    headers or footers.
    """
    candidates: Counter[str] = Counter()

    for text in pages_text:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        edge_lines = set()
        for line in lines[:3]:
            edge_lines.add(line)
        for line in lines[-3:]:
            edge_lines.add(line)
        for line in edge_lines:
            candidates[line] += 1

    return {line for line, count in candidates.items() if count >= threshold}


# ── Public API ───────────────────────────────────────────────────────────


def clean_pages(pages_text: list[str]) -> list[str]:
    """
    Clean a list of per-page text strings.

    Returns a new list with the same length, each entry cleaned.
    """
    repeated = _detect_repeated_lines(pages_text)
    return [_clean_single(text, repeated) for text in pages_text]


def _clean_single(text: str, repeated_lines: set[str]) -> str:
    """Clean a single page's text."""

    lines = text.splitlines()
    cleaned: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Remove blank lines (we'll reinsert paragraph breaks later)
        if not stripped:
            cleaned.append("")
            continue

        # Remove page numbers
        if _PAGE_NUM_RE.match(stripped):
            continue

        # Remove repeated headers/footers
        if stripped in repeated_lines:
            continue

        # Collapse multiple spaces
        stripped = _MULTI_SPACE_RE.sub(" ", stripped)

        cleaned.append(stripped)

    # Rejoin broken line wraps.
    merged = _merge_broken_lines(cleaned)

    # Final normalize
    merged = normalize_khmer(merged)
    return merged


def _merge_broken_lines(lines: list[str]) -> str:
    """
    Merge lines that were broken mid-paragraph by the PDF renderer.

    Rules:
      • An empty line means a real paragraph break → keep it.
      • A line starting with a list marker → keep it on its own line.
      • A line that follows a non-sentence-ending line and does NOT start
        with a capital/Khmer-letter → join to previous.
    """
    out: list[str] = []
    buf = ""

    for line in lines:
        if not line:
            # Paragraph break
            if buf:
                out.append(buf)
                buf = ""
            out.append("")
            continue

        if _LIST_MARKER_RE.match(line):
            if buf:
                out.append(buf)
                buf = ""
            buf = line
            continue

        if buf:
            # Decide: join or break?
            if _SENTENCE_ENDERS.search(buf):
                # Previous line ended a sentence → start new paragraph.
                out.append(buf)
                buf = line
            else:
                # Continuation of the same paragraph.
                buf = buf + " " + line
        else:
            buf = line

    if buf:
        out.append(buf)

    return "\n".join(out)
