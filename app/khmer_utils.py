"""
Step 5: Khmer Unicode Text Correctness & Legacy Font Converter.

Handles:
  • NFC normalization
  • Zero-width character handling (preserves meaningful ZWSP U+200B, strips stray ZWNJ, ZWJ, BOM, Word Joiner)
  • Orthographic cluster boundary protection (never split consonant + coeng + subconsonant + vowel across lines)
  • Legacy font conversion (Limon, ABC) with digraph and subscript support
  • Tesseract OCR fallback (300 DPI in-memory PyMuPDF pixmaps)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

# ── Khmer Unicode Codepoint Ranges ───────────────────────────────────────
# Khmer: U+1780 – U+17FF
# Khmer Symbols: U+19E0 – U+19FF
KHMER_CHAR_RE = re.compile(r"[\u1780-\u17FF\u19E0-\u19FF]")

# Complete Khmer Syllable Cluster regex
# Consonant/Ind. Vowel + (Coeng + Consonant)* + Register signs? + Vowel? + Diacritics?
KHMER_CLUSTER_RE = re.compile(
    r"[\u1780-\u17B3]"              # Base consonant / independent vowel
    r"(?:\u17D2[\u1780-\u17B3])*"   # Optional subscript consonants (ជើង)
    r"[\u17C9\u17CA]?"              # Optional register signs (ត្រីស័ព្ទ / មូសិកទន្ត)
    r"[\u17B6-\u17C5]?"              # Optional dependent vowel (ស្រៈនិស្ស័យ)
    r"[\u17C6-\u17D1\u17D3]?"       # Optional diacritics / signs (និគ្គហិត, រះមុខ, etc.)
)

# Stray invisible characters to strip: ZWNJ, ZWJ, Word Joiner, BOM
STRAY_CHARS_RE = re.compile(r"[\u200C\u200D\u2060\uFEFF]")
MULTI_ZWSP_RE = re.compile(r"\u200B{2,}")

# Legacy non-Unicode Khmer font names (Limon, ABC, etc.)
LEGACY_FONT_PREFIXES = [
    "limon", "abc-", "abc ", "khek", "fk_", "cs-", "kh_",
    "baidok", "kampot", "moul", "battambang", "taprom", "metal chrieng",
]

# Multi-character digraphs in Limon / ABC encoding
LIMON_DIGRAPHS: dict[str, str] = {
    "Ch": "\u1787",  # Ch -> ជ
    "ch": "\u1787",
    "Df": "\u178B",  # Df -> ឋ
    "df": "\u178B",
    "Nn": "\u178C",  # Nn -> ឌ
    "nn": "\u178C",
    "kh": "\u1781",  # kh -> ខ
    "Kh": "\u1781",
    "th": "\u1790",  # th -> ថ
    "Th": "\u1790",
    "ph": "\u1795",  # ph -> ផ
    "Ph": "\u1795",
}

# Single-byte code points for Limon S1 -> Khmer Unicode
LIMON_CHAR_MAP: dict[int, str] = {
    # Punctuation & signs
    0x21: "\u17D4",  # ! -> ។ (Khan)
    0x22: "\u17D5",  # " -> ៕ (Bariyosan)
    0x23: "\u17D1",  # # -> ៑ (Viriam)
    0x24: "\u17D6",  # $ -> ៖ (Camnuc-pi-kuuh)
    0x25: "\u17D7",  # % -> ៗ (Lek Too)
    0x28: "\u17D8",  # ( -> ៘ (Beyyal)
    0x29: "\u17D9",  # ) -> ៙ (Phnek Moan)
    # Digits (0-9 -> Khmer digits)
    0x30: "\u17E0",  # 0 -> ០
    0x31: "\u17E1",  # 1 -> ១
    0x32: "\u17E2",  # 2 -> ២
    0x33: "\u17E3",  # 3 -> ៣
    0x34: "\u17E4",  # 4 -> ៤
    0x35: "\u17E5",  # 5 -> ៥
    0x36: "\u17E6",  # 6 -> ៦
    0x37: "\u17E7",  # 7 -> ៧
    0x38: "\u17E8",  # 8 -> ៨
    0x39: "\u17E9",  # 9 -> ៩
    # Consonants
    0x6B: "\u1780",  # k -> ក
    0x78: "\u1781",  # x -> ខ
    0x43: "\u1782",  # C -> គ
    0x44: "\u1783",  # D -> ឃ
    0x67: "\u1784",  # g -> ង
    0x63: "\u1785",  # c -> ច
    0x4A: "\u1786",  # J -> ឆ
    0x4E: "\u1788",  # N -> ឈ
    0x47: "\u1789",  # G -> ញ
    0x64: "\u178A",  # d -> ដ
    0x70: "\u178E",  # p -> ណ
    0x74: "\u178F",  # t -> ត
    0x54: "\u1790",  # T -> ថ
    0x66: "\u1791",  # f -> ទ
    0x46: "\u1792",  # F -> ធ
    0x6E: "\u1793",  # n -> ន
    0x62: "\u1794",  # b -> ប
    0x42: "\u1795",  # B -> ផ
    0x71: "\u1796",  # q -> ព
    0x51: "\u1797",  # Q -> ភ
    0x6D: "\u1798",  # m -> ម
    0x79: "\u1799",  # y -> យ
    0x72: "\u179A",  # r -> រ
    0x6C: "\u179B",  # l -> ល
    0x76: "\u179C",  # v -> វ
    0x73: "\u179F",  # s -> ស
    0x68: "\u17A0",  # h -> ហ
    0x6F: "\u17A2",  # o -> អ
    # Dependent Vowels
    0x61: "\u17B6",  # a -> ា
    0x69: "\u17B7",  # i -> ិ
    0x49: "\u17B8",  # I -> ី
    0x77: "\u17B9",  # w -> ឹ
    0x57: "\u17BA",  # W -> ឺ
    0x75: "\u17BB",  # u -> ុ
    0x55: "\u17BC",  # U -> ូ
    0x65: "\u17C1",  # e -> េ
    0x45: "\u17C2",  # E -> ែ
    0x4F: "\u17C4",  # O -> ោ
}


def is_khmer_char(ch: str) -> bool:
    """Return True if character is in the Khmer Unicode range."""
    return bool(KHMER_CHAR_RE.match(ch))


def has_khmer(text: str) -> bool:
    """Return True if text contains at least one Khmer Unicode character."""
    return bool(KHMER_CHAR_RE.search(text))


def normalize_khmer(text: str) -> str:
    """
    Standardize Khmer Unicode text:
      1. NFC normalization
      2. Strip stray invisible characters (ZWNJ, ZWJ, Word Joiner, BOM)
      3. Preserve single ZWSP (U+200B) between words
      4. Collapse multiple consecutive ZWSPs into one
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = STRAY_CHARS_RE.sub("", text)
    text = MULTI_ZWSP_RE.sub("\u200B", text)
    return text


def is_legacy_font(font_name: str) -> bool:
    """Check if font_name is a known legacy non-Unicode Khmer font."""
    if not font_name:
        return False
    lower = font_name.lower().strip()
    return any(lower.startswith(p) for p in LEGACY_FONT_PREFIXES)


def legacy_to_unicode(text: str, font_name: str = "") -> str:
    """
    Convert legacy Limon/ABC encoded text to proper Khmer Unicode.
    Pre-processes multi-character digraphs before single-character mapping.
    """
    if not text:
        return ""

    result = text
    # 1. Substitute digraphs first
    for dg, uni in LIMON_DIGRAPHS.items():
        if dg in result:
            result = result.replace(dg, uni)

    # 2. Map single codepoints
    out: list[str] = []
    for ch in result:
        cp = ord(ch)
        out.append(LIMON_CHAR_MAP.get(cp, ch))

    return normalize_khmer("".join(out))


def split_khmer_clusters(text: str) -> list[str]:
    """
    Split Khmer text into orthographic syllable clusters.
    Ensures that consonant + coeng + subconsonant + vowel + diacritics
    remain strictly together.
    """
    clusters: list[str] = []
    last_idx = 0
    for match in KHMER_CLUSTER_RE.finditer(text):
        start, end = match.span()
        # Any non-Khmer text before this cluster
        if start > last_idx:
            clusters.append(text[last_idx:start])
        clusters.append(text[start:end])
        last_idx = end
    if last_idx < len(text):
        clusters.append(text[last_idx:])
    return [c for c in clusters if c]


def join_lines_khmer_safe(prev_line: str, next_line: str) -> str:
    """
    Safely join two wrapped lines:
      • If wrapping occurs between two Khmer characters, join directly
        (or with ZWSP) to prevent inserting unwanted spaces inside Khmer words.
      • If Latin or digits, join with standard space ' '.
    """
    if not prev_line:
        return next_line
    if not next_line:
        return prev_line

    last_ch = prev_line[-1]
    first_ch = next_line[0]

    if is_khmer_char(last_ch) and is_khmer_char(first_ch):
        # Do not insert visible space between Khmer characters
        return prev_line + "\u200B" + next_line
    return prev_line + " " + next_line


def contains_garbled_text(text: str) -> bool:
    """Return True if text has high ratio of replacement or PUA codepoints."""
    if not text or len(text) < 10:
        return False
    bad = sum(1 for ch in text if ch == "\uFFFD" or unicodedata.category(ch) == "Co")
    return (bad / len(text)) > 0.15


# ── In-Memory OCR Fallback using PyMuPDF (No Poppler required) ────────────

_pytesseract = None


def get_pytesseract():
    global _pytesseract
    if _pytesseract is None:
        import pytesseract
        _pytesseract = pytesseract
    return _pytesseract


def ocr_page_in_memory(
    page: fitz.Page,
    dpi: int = 300,
    lang: str = "khm+eng",
) -> str:
    """
    Run Tesseract OCR on a PyMuPDF page in memory at 300 DPI.
    Does not require Poppler / pdftoppm or disk I/O.
    """
    pytesseract = get_pytesseract()
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    text = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
    return normalize_khmer(text)
