"""
PDF text extraction layer.

Uses PyMuPDF (fitz) for text-layer extraction and Tesseract OCR as a
fallback for scanned / image-only pages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image
from pdf2image import convert_from_path

from app.config import OCR_DPI, TESSERACT_LANG, TEXT_LAYER_MIN_CHARS, TEXT_LAYER_MIN_RATIO
from app.khmer_utils import contains_garbled_text, is_legacy_font, legacy_to_unicode, normalize_khmer

logger = logging.getLogger(__name__)

# Lazy-import pytesseract so the module loads even when Tesseract isn't installed.
_pytesseract = None


def _get_pytesseract():
    global _pytesseract
    if _pytesseract is None:
        import pytesseract as _pt
        _pytesseract = _pt
    return _pytesseract


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class ExtractedImage:
    """An image pulled from a PDF page."""
    data: bytes
    ext: str  # e.g. "png", "jpeg"
    width: int
    height: int
    bbox: tuple[float, float, float, float] | None = None  # (x0,y0,x1,y1)


@dataclass
class PageContent:
    """Content extracted from a single PDF page."""
    page_number: int
    text: str = ""
    images: list[ExtractedImage] = field(default_factory=list)
    used_ocr: bool = False


# ── Core extraction ──────────────────────────────────────────────────────

def _page_has_text_layer(page: fitz.Page) -> bool:
    """Check whether a PyMuPDF page has a meaningful text layer."""
    text = page.get_text("text")
    if len(text.strip()) < TEXT_LAYER_MIN_CHARS:
        return False
    # Check ratio of "printable / meaningful" characters
    printable = sum(1 for ch in text if ch.isprintable() and ch.strip())
    ratio = printable / max(len(text), 1)
    return ratio >= TEXT_LAYER_MIN_RATIO


def _extract_text_with_fonts(page: fitz.Page) -> str:
    """
    Extract text from a PyMuPDF page, converting legacy-font spans to
    Unicode on the fly.
    """
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    parts: list[str] = []

    for block in blocks:
        if block["type"] != 0:  # skip image blocks
            continue
        for line in block["lines"]:
            line_parts: list[str] = []
            for span in line["spans"]:
                txt = span["text"]
                font_name = span.get("font", "")
                if is_legacy_font(font_name):
                    txt = legacy_to_unicode(txt, font_name)
                line_parts.append(txt)
            parts.append("".join(line_parts))

    return "\n".join(parts)


def _extract_images_from_page(page: fitz.Page) -> list[ExtractedImage]:
    """Extract embedded images from a PyMuPDF page."""
    images: list[ExtractedImage] = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            base_image = page.parent.extract_image(xref)
            if base_image:
                images.append(
                    ExtractedImage(
                        data=base_image["image"],
                        ext=base_image["ext"],
                        width=base_image["width"],
                        height=base_image["height"],
                    )
                )
        except Exception:
            logger.warning("Failed to extract image xref=%s from page %s", xref, page.number)
    return images


def _ocr_page(pdf_path: str | Path, page_number: int) -> str:
    """Run Tesseract OCR on a single PDF page (0-indexed)."""
    pytesseract = _get_pytesseract()
    pil_images = convert_from_path(
        str(pdf_path),
        dpi=OCR_DPI,
        first_page=page_number + 1,
        last_page=page_number + 1,
    )
    if not pil_images:
        return ""
    text = pytesseract.image_to_string(
        pil_images[0],
        lang=TESSERACT_LANG,
        config="--psm 6",
    )
    return text


# ── Public API ───────────────────────────────────────────────────────────

def extract_pdf(pdf_path: str | Path) -> list[PageContent]:
    """
    Extract content from every page of *pdf_path*.

    Strategy per page:
      1. Try PyMuPDF text extraction (with legacy-font conversion).
      2. If the text layer is absent or garbled, fall back to OCR.
      3. Normalize the resulting Khmer text.
      4. Collect embedded images.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    pages: list[PageContent] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pc = PageContent(page_number=page_idx + 1)

        # 1. Attempt direct text extraction
        has_text = _page_has_text_layer(page)
        text = ""
        used_ocr = False

        if has_text:
            text = _extract_text_with_fonts(page)
            if contains_garbled_text(text):
                logger.info(
                    "Page %d: text layer looks garbled – falling back to OCR.",
                    page_idx + 1,
                )
                has_text = False

        # 2. OCR fallback
        if not has_text:
            used_ocr = True
            try:
                text = _ocr_page(pdf_path, page_idx)
            except Exception:
                logger.exception("OCR failed on page %d", page_idx + 1)
                text = ""

        # 3. Normalize
        pc.text = normalize_khmer(text)
        pc.used_ocr = used_ocr

        # 4. Images
        pc.images = _extract_images_from_page(page)

        pages.append(pc)

    doc.close()
    return pages
