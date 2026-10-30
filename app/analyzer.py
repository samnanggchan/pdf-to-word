"""
Step 1: PDF Document & Page Analyzer.

Analyzes PDF structure per page:
  • Geometry: dimensions, rotation, content margins
  • Content layers: text-layer presence, image count, vector drawings, tables, columns
  • Typography: every font (embedded status, font type, Khmer Unicode vs legacy Limon/ABC / garbled)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Regex for Khmer Unicode codepoints: U+1780-U+17FF and U+19E0-U+19FF
KHMER_UNICODE_RE = re.compile(r"[\u1780-\u17FF\u19E0-\u19FF]")
SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

# Known legacy non-Unicode Khmer font families / prefixes
LEGACY_FONT_HINTS = [
    "limon", "abc-", "abc ", "khek", "zgm", "tact", "kmer",
    "fk_", "cs-", "kh_", "baidok", "kampot", "moul", "taprom",
]


@dataclass
class FontInfo:
    """Detailed font metadata discovered in a PDF."""
    name: str
    clean_name: str
    embedded: bool = False
    font_type: str = "Unknown"  # TrueType, Type1, Type0 / CID, etc.
    xref: int = 0
    is_khmer_name: bool = False
    is_legacy: bool = False
    is_garbled: bool = False


@dataclass
class PageAnalysis:
    """Comprehensive analysis of a single PDF page."""
    page_number: int  # 1-indexed
    width: float  # in points (1 pt = 1/72 in)
    height: float  # in points
    rotation: int  # 0, 90, 180, 270
    margins: dict[str, float] = field(default_factory=lambda: {"top": 72.0, "bottom": 72.0, "left": 72.0, "right": 72.0})
    has_text_layer: bool = False
    char_count: int = 0
    khmer_char_count: int = 0
    image_count: int = 0
    drawing_count: int = 0
    table_count: int = 0
    column_count: int = 1
    fonts: list[FontInfo] = field(default_factory=list)
    needs_ocr: bool = False
    has_legacy_fonts: bool = False


@dataclass
class DocumentAnalysis:
    """Document-wide summary of the PDF analysis."""
    total_pages: int
    pages: list[PageAnalysis] = field(default_factory=list)
    all_fonts: list[FontInfo] = field(default_factory=list)
    has_scanned_pages: bool = False
    has_legacy_fonts: bool = False
    has_tables: bool = False
    has_vector_graphics: bool = False
    suggested_mode: str = "layout"  # 'layout' (pdf2docx), 'exact' (fixed coordinates), or 'ocr'


def clean_font_family_name(raw: str | None) -> str:
    """Strip subset prefix (e.g. 'ABCDEF+KhmerOSBattambang-Bold' -> 'KhmerOSBattambang-Bold')."""
    if not raw:
        return "Unknown"
    name = SUBSET_PREFIX_RE.sub("", raw.strip())
    return name


def is_legacy_font_name(font_name: str) -> bool:
    """Check if font name matches known legacy non-Unicode Khmer fonts."""
    if not font_name:
        return False
    lower = clean_font_family_name(font_name).lower()
    return any(hint in lower for hint in LEGACY_FONT_HINTS)


def detect_columns(blocks: list[dict[str, Any]], page_width: float) -> int:
    """
    Estimate number of text columns on the page by analyzing
    horizontal positions and gaps between text blocks.
    """
    text_blocks = [b for b in blocks if b.get("type") == 0 and b.get("text", "").strip()]
    if len(text_blocks) < 3:
        return 1

    # Collect midpoints of x spans
    x_ranges = [(b["bbox"][0], b["bbox"][2]) for b in text_blocks]
    lefts = [r[0] for r in x_ranges]

    # Cluster left margins: if we see two distinct clusters separated by at least 15% page width
    lefts.sort()
    gaps: list[float] = []
    for i in range(len(lefts) - 1):
        diff = lefts[i + 1] - lefts[i]
        if diff > page_width * 0.15:
            gaps.append(diff)

    if len(gaps) >= 2:
        return 3
    elif len(gaps) == 1:
        return 2
    return 1


def analyze_page(doc: fitz.Document, page_index: int) -> PageAnalysis:
    """Analyze a single page of a PyMuPDF document (0-indexed)."""
    page = doc[page_index]
    rect = page.rect
    width, height = float(rect.width), float(rect.height)
    rotation = int(page.rotation)

    # 1. Text extraction & characters
    text = page.get_text("text")
    stripped_text = text.strip()
    char_count = len(stripped_text)
    khmer_char_count = len(KHMER_UNICODE_RE.findall(stripped_text))

    # Text-layer usability heuristic
    printable_chars = sum(1 for ch in stripped_text if ch.isprintable() and not ch.isspace())
    printable_ratio = printable_chars / max(char_count, 1)
    has_text_layer = char_count >= 15 and printable_ratio >= 0.35

    # 2. Images & Drawings
    images = page.get_images(full=True)
    image_count = len(images)
    drawings = page.get_drawings()
    drawing_count = len(drawings)

    # 3. Tables (using PyMuPDF find_tables if available)
    table_count = 0
    try:
        tables = page.find_tables()
        table_count = len(tables.tables) if tables else 0
    except Exception:
        table_count = 0

    # 4. Margins: Calculate bounding box of all content
    content_rects: list[fitz.Rect] = []
    text_blocks = page.get_text("blocks")
    for b in text_blocks:
        if b[4].strip():  # text not empty
            content_rects.append(fitz.Rect(b[:4]))
    for img_info in images:
        try:
            for r in page.get_image_rects(img_info[0]):
                content_rects.append(r)
        except Exception:
            pass
    for d in drawings:
        content_rects.append(d["rect"])

    if content_rects:
        union_rect = content_rects[0]
        for r in content_rects[1:]:
            union_rect |= r
        margins = {
            "left": max(0.0, float(union_rect.x0)),
            "top": max(0.0, float(union_rect.y0)),
            "right": max(0.0, width - float(union_rect.x1)),
            "bottom": max(0.0, height - float(union_rect.y1)),
        }
    else:
        margins = {"left": 72.0, "top": 72.0, "right": 72.0, "bottom": 72.0}

    # 5. Columns
    blocks_dict = page.get_text("dict").get("blocks", [])
    column_count = detect_columns(blocks_dict, width)

    # 6. Fonts
    fonts: list[FontInfo] = []
    seen_xrefs = set()
    page_has_legacy = False

    for f in page.get_fonts(full=True):
        xref = f[0]
        ext = f[1]
        font_type = f[2]
        font_name = f[3]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        clean_name = clean_font_family_name(font_name)
        is_legacy = is_legacy_font_name(font_name)
        if is_legacy:
            page_has_legacy = True

        # Check if font is embedded
        embedded = False
        try:
            if xref > 0:
                font_buffer = doc.extract_font(xref)
                embedded = bool(font_buffer and font_buffer[3])  # buffer bytes
        except Exception:
            embedded = False

        is_khmer_name = (
            "khmer" in clean_name.lower()
            or "battambang" in clean_name.lower()
            or "muol" in clean_name.lower()
            or "moul" in clean_name.lower()
            or "siemreap" in clean_name.lower()
            or "bokor" in clean_name.lower()
            or "kantumruy" in clean_name.lower()
            or is_legacy
        )

        # Check if text is garbled: high ratio of replacement or PUA codepoints
        pua_or_replacement = sum(1 for ch in stripped_text if ch == "\uFFFD" or unicodedata.category(ch) == "Co")
        is_garbled = (pua_or_replacement / max(char_count, 1)) > 0.15

        fonts.append(
            FontInfo(
                name=font_name,
                clean_name=clean_name,
                embedded=embedded,
                font_type=font_type or ext or "TrueType",
                xref=xref,
                is_khmer_name=is_khmer_name,
                is_legacy=is_legacy,
                is_garbled=is_garbled,
            )
        )

    # Needs OCR if text layer is absent OR page is garbled and has images
    needs_ocr = (not has_text_layer) or (char_count < 10 and image_count > 0)

    return PageAnalysis(
        page_number=page_index + 1,
        width=width,
        height=height,
        rotation=rotation,
        margins=margins,
        has_text_layer=has_text_layer,
        char_count=char_count,
        khmer_char_count=khmer_char_count,
        image_count=image_count,
        drawing_count=drawing_count,
        table_count=table_count,
        column_count=column_count,
        fonts=fonts,
        needs_ocr=needs_ocr,
        has_legacy_fonts=page_has_legacy,
    )


def analyze_pdf(pdf_path: str | Path) -> DocumentAnalysis:
    """Analyze an entire PDF document and return comprehensive metadata."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages: list[PageAnalysis] = []
    font_map: dict[str, FontInfo] = {}

    for i in range(len(doc)):
        pa = analyze_page(doc, i)
        pages.append(pa)
        for f in pa.fonts:
            if f.clean_name not in font_map:
                font_map[f.clean_name] = f

    total_pages = len(pages)
    doc.close()

    has_scanned = any(p.needs_ocr for p in pages)
    has_legacy = any(p.has_legacy_fonts for p in pages)
    has_tables = any(p.table_count > 0 for p in pages)
    has_drawings = any(p.drawing_count > 0 for p in pages)

    # Suggested mode logic:
    # If mostly scanned -> ocr
    # If complex vector graphics / tables / columns without clean paragraphs -> exact layout
    # Otherwise -> layout (editable)
    if all(p.needs_ocr for p in pages):
        suggested_mode = "ocr"
    elif any(p.column_count > 1 or p.drawing_count > 25 for p in pages):
        suggested_mode = "exact"
    else:
        suggested_mode = "layout"

    return DocumentAnalysis(
        total_pages=total_pages,
        pages=pages,
        all_fonts=list(font_map.values()),
        has_scanned_pages=has_scanned,
        has_legacy_fonts=has_legacy,
        has_tables=has_tables,
        has_vector_graphics=has_drawings,
        suggested_mode=suggested_mode,
    )

