"""
DOCX builder – assembles cleaned text and images into a Word document
with proper Khmer font & complex-script settings.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from app.config import KHMER_FONT, KHMER_FONT_SIZE_PT
from app.khmer_utils import has_khmer
from app.pdf_extractor import ExtractedImage, PageContent

logger = logging.getLogger(__name__)


# ── Font helpers ─────────────────────────────────────────────────────────

def _set_run_khmer_font(run, font_name: str = KHMER_FONT, size_pt: int = KHMER_FONT_SIZE_PT):
    """
    Set the Khmer font on a python-docx Run.

    Applies the font to all four slots (ascii, hAnsi, cs, eastAsia) and
    sets the complex-script font size (w:szCs) so Khmer renders at the
    correct size in Word.
    """
    rPr = run._r.get_or_add_rPr()

    # w:rFonts
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rFonts.set(qn("w:cs"), font_name)
    rFonts.set(qn("w:eastAsia"), font_name)

    # w:sz  (font size in half-points)
    half_pt = str(size_pt * 2)
    sz = rPr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rPr.append(sz)
    sz.set(qn("w:val"), half_pt)

    # w:szCs  (complex-script font size in half-points)
    szCs = rPr.find(qn("w:szCs"))
    if szCs is None:
        szCs = OxmlElement("w:szCs")
        rPr.append(szCs)
    szCs.set(qn("w:val"), half_pt)

    # Mark the run as complex-script so Word uses the CS font for shaping
    cs_elem = rPr.find(qn("w:cs"))
    # w:cs (the element, not the attribute) is a toggle property
    if cs_elem is None:
        cs_toggle = OxmlElement("w:cs")
        cs_toggle.set(qn("w:val"), "1")
        rPr.append(cs_toggle)


def _set_default_khmer_style(doc: Document):
    """Set the default document font to the Khmer font."""
    style = doc.styles["Normal"]
    font = style.font
    font.name = KHMER_FONT
    font.size = Pt(KHMER_FONT_SIZE_PT)

    # Also set complex-script font in the underlying XML
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:cs"), KHMER_FONT)

    szCs = rPr.find(qn("w:szCs"))
    if szCs is None:
        szCs = OxmlElement("w:szCs")
        rPr.append(szCs)
    szCs.set(qn("w:val"), str(KHMER_FONT_SIZE_PT * 2))


# ── Heading detection heuristic ──────────────────────────────────────────

def _looks_like_heading(line: str) -> bool:
    """
    Heuristic: a short line (< 120 chars) that doesn't end with normal
    sentence punctuation is probably a heading.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 120:
        return False
    if stripped[-1] in ".!?,;:\u17D4\u17D5។៕":
        return False
    # Entirely uppercase Latin or all-Khmer with no punctuation → heading
    if stripped.isupper() and len(stripped) > 3:
        return True
    return False


# ── Image insertion ──────────────────────────────────────────────────────

def _add_image_to_doc(doc: Document, img: ExtractedImage):
    """Insert an extracted image into the document."""
    try:
        stream = io.BytesIO(img.data)
        # Limit width to 6 inches to keep the layout readable
        max_width = Inches(6)
        width = min(max_width, Inches(img.width / 96))  # approx 96 dpi
        doc.add_picture(stream, width=width)
        # Center the image
        last_para = doc.paragraphs[-1]
        last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        logger.warning("Could not insert an image into the DOCX.")


# ── Public API ───────────────────────────────────────────────────────────

def build_docx(pages: list[PageContent], output_path: str | Path):
    """
    Assemble a DOCX file from extracted + cleaned page content.

    The output uses proper Khmer font settings on every run that contains
    Khmer characters.
    """
    doc = Document()
    _set_default_khmer_style(doc)

    for page in pages:
        lines = page.text.splitlines()

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # Empty line → paragraph break
                doc.add_paragraph("")
                continue

            if _looks_like_heading(stripped):
                para = doc.add_heading(stripped, level=2)
            else:
                para = doc.add_paragraph()
                run = para.add_run(stripped)
                if has_khmer(stripped):
                    _set_run_khmer_font(run)

        # Add images after each page's text
        for img in page.images:
            _add_image_to_doc(doc, img)

    doc.save(str(output_path))
    logger.info("DOCX saved to %s", output_path)
