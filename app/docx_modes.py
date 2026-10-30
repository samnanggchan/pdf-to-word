"""
Step 4: Two Output Modes: Mode A (Editable) & Mode B (Exact Layout).

MODE A "Editable":
  • Uses pdf2docx for flowing paragraphs, tables, lists, and layout.
  • Post-processes with FontResolver, applying Khmer complex-script OpenXML (w:rFonts, w:szCs, w:bCs, w:lang).
  • Sets exact page sizes and margins matching the original PDF.

MODE B "Exact Layout":
  • Places lines as absolutely positioned frames (w:framePr) at exact (x, y) coordinates from PDF bboxes.
  • Zero internal padding (w:hSpace=0, w:vSpace=0, wrap=none), anchored to page origin.
  • Places images and vector boxes at their exact coordinates.
  • One section per page with matching page size and orientation.

Hybrid / Auto Mode:
  • Uses Mode A for simple flowing documents, falls back to Mode B for complex/multi-column pages.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from pdf2docx import Converter

from app.analyzer import DocumentAnalysis, PageAnalysis, analyze_pdf
from app.extractor import ExtractedPage, extract_pdf_document
from app.font_resolver import (
    FontResolver,
    apply_khmer_run_properties,
    obfuscate_font_data,
)

logger = logging.getLogger(__name__)


def _set_section_geometry(section: Any, width_pt: float, height_pt: float, margins: dict[str, float] | None = None):
    """Set section page dimensions and margins in points."""
    section.page_width = Pt(width_pt)
    section.page_height = Pt(height_pt)
    if width_pt > height_pt:
        section.orientation = WD_ORIENT.LANDSCAPE
    else:
        section.orientation = WD_ORIENT.PORTRAIT

    if margins:
        section.top_margin = Pt(margins.get("top", 72.0))
        section.bottom_margin = Pt(margins.get("bottom", 72.0))
        section.left_margin = Pt(margins.get("left", 72.0))
        section.right_margin = Pt(margins.get("right", 72.0))
    else:
        section.top_margin = Pt(0)
        section.bottom_margin = Pt(0)
        section.left_margin = Pt(0)
        section.right_margin = Pt(0)


def _add_frame_pr(pPr: Any, x_pt: float, y_pt: float, w_pt: float, h_pt: float):
    """
    Attach OpenXML w:framePr to a paragraph for absolute page positioning.
    Coordinates are in twips (1 pt = 20 twips).
    """
    framePr = OxmlElement("w:framePr")
    # Coordinates in twips
    x_twips = str(int(round(x_pt * 20)))
    y_twips = str(int(round(y_pt * 20)))
    w_twips = str(max(20, int(round(w_pt * 20))))
    h_twips = str(max(20, int(round(h_pt * 20))))

    framePr.set(qn("w:w"), w_twips)
    framePr.set(qn("w:h"), h_twips)
    framePr.set(qn("w:hRule"), "exact")
    framePr.set(qn("w:hAnchor"), "page")
    framePr.set(qn("w:vAnchor"), "page")
    framePr.set(qn("w:x"), x_twips)
    framePr.set(qn("w:y"), y_twips)
    framePr.set(qn("w:wrap"), "none")
    framePr.set(qn("w:hSpace"), "0")
    framePr.set(qn("w:vSpace"), "0")
    pPr.append(framePr)


def _embed_fonts_in_docx(docx_path: str | Path, embedded_fonts: dict[str, Any]):
    """
    Inject extracted embedded fonts into DOCX archive as obfuscated .odttf
    and update word/fontTable.xml.
    """
    if not embedded_fonts:
        return

    docx_path = Path(docx_path)
    tmp_out = docx_path.with_suffix(".tmp.docx")

    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(tmp_out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            zout.writestr(item, content)

        # Inject obfuscated fonts
        for font_name, resolved in embedded_fonts.items():
            if resolved.embedded_data and resolved.obfuscated_filename and resolved.embedded_font_key:
                obf_bytes = obfuscate_font_data(resolved.embedded_data, resolved.embedded_font_key)
                zout.writestr(f"word/fonts/{resolved.obfuscated_filename}", obf_bytes)

    tmp_out.replace(docx_path)


# ── MODE A: Editable (pdf2docx + Font Post-Processing) ────────────────────

def build_mode_a_editable(
    pdf_path: str | Path,
    output_path: str | Path,
    doc_analysis: DocumentAnalysis,
    font_resolver: FontResolver,
) -> Path:
    """
    Build an editable DOCX preserving paragraphs, tables, and lists via pdf2docx,
    then apply dynamic font resolution and complex-script formatting to all runs.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Run pdf2docx layout converter
    cv = Converter(str(pdf_path))
    try:
        cv.convert(str(output_path), start=0, end=None)
    finally:
        cv.close()

    # 2. Open generated document and refine formatting
    doc = Document(str(output_path))

    # Match section geometry
    if doc.sections and doc_analysis.pages:
        for idx, section in enumerate(doc.sections):
            pa = doc_analysis.pages[min(idx, len(doc_analysis.pages) - 1)]
            _set_section_geometry(section, pa.width, pa.height, pa.margins)

    # Walk all paragraphs, tables, headers, footers
    def process_paragraph(p):
        for run in p.runs:
            txt = run.text
            if not txt:
                continue
            raw_font = run.font.name or "Khmer OS Battambang"
            resolved = font_resolver.resolve_font(raw_font)
            is_bold = bool(run.bold)
            is_italic = bool(run.italic)
            pt_size = run.font.size.pt if run.font.size else 11.0

            apply_khmer_run_properties(
                run=run,
                font_name=resolved.resolved_name,
                font_size_pt=pt_size,
                is_bold=is_bold,
                is_italic=is_italic,
            )

    for p in doc.paragraphs:
        process_paragraph(p)

    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    process_paragraph(p)

    for s in doc.sections:
        for part in (s.header, s.footer):
            if part:
                for p in part.paragraphs:
                    process_paragraph(p)

    doc.save(str(output_path))

    # 3. Embed extracted fonts if any
    _embed_fonts_in_docx(output_path, font_resolver._embedded_fonts)

    return output_path


# ── MODE B: Exact Layout (DrawingML / Absolute Frame Positioning) ─────────

def build_mode_b_exact(
    pdf_path: str | Path,
    output_path: str | Path,
    doc_analysis: DocumentAnalysis,
    extracted_pages: list[ExtractedPage],
    font_resolver: FontResolver,
) -> Path:
    """
    Build a visually exact DOCX where every text line, image, and drawing
    is placed at its precise PDF coordinates using w:framePr.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    for p_idx, ep in enumerate(extracted_pages):
        pa = doc_analysis.pages[min(p_idx, len(doc_analysis.pages) - 1)]

        if p_idx == 0:
            section = doc.sections[0]
        else:
            section = doc.add_section(WD_SECTION_START.NEW_PAGE)

        # Set exact page dimensions and zero margins for absolute frame positioning
        _set_section_geometry(section, ep.width, ep.height, margins=None)

        # 1. Place Vector Drawings (lines, boxes)
        for drw in ep.drawings:
            x0, y0, x1, y1 = drw.bbox
            w = max(1.0, x1 - x0)
            h = max(1.0, y1 - y0)
            if w < 1.0 and h < 1.0:
                continue

            dp = doc.add_paragraph()
            dpPr = dp._p.get_or_add_pPr()
            _add_frame_pr(dpPr, x0, y0, w, h)

            # Style borders or fill
            if drw.fill_color:
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:fill"), drw.fill_color.replace("#", ""))
                dpPr.append(shd)
            elif drw.stroke_color:
                pBdr = OxmlElement("w:pBdr")
                bdr = OxmlElement("w:bottom")
                bdr.set(qn("w:val"), "single")
                bdr.set(qn("w:sz"), str(max(4, int(round(drw.stroke_width * 8)))))
                bdr.set(qn("w:space"), "0")
                bdr.set(qn("w:color"), drw.stroke_color.replace("#", ""))
                pBdr.append(bdr)
                dpPr.append(pBdr)

        # 2. Place Images at exact bbox
        for img in ep.images:
            ix0, iy0, ix1, iy1 = img.bbox
            iw = max(10.0, ix1 - ix0)
            ih = max(10.0, iy1 - iy0)

            ip = doc.add_paragraph()
            ipPr = ip._p.get_or_add_pPr()
            _add_frame_pr(ipPr, ix0, iy0, iw, ih)

            try:
                stream = io.BytesIO(img.data)
                run = ip.add_run()
                run.add_picture(stream, width=Pt(iw), height=Pt(ih))
            except Exception as e:
                logger.warning("Could not add image on page %s: %s", ep.page_number, e)

        # 3. Place Text Lines at exact bbox
        for block in ep.text_blocks:
            for line in block.lines:
                lx0, ly0, lx1, ly1 = line.bbox
                lw = max(10.0, lx1 - lx0)
                lh = max(6.0, ly1 - ly0)

                lp = doc.add_paragraph()
                lpPr = lp._p.get_or_add_pPr()
                _add_frame_pr(lpPr, lx0, ly0, lw, lh)

                # Set zero paragraph spacing
                spc = OxmlElement("w:spacing")
                spc.set(qn("w:before"), "0")
                spc.set(qn("w:after"), "0")
                spc.set(qn("w:line"), "240")
                spc.set(qn("w:lineRule"), "auto")
                lpPr.append(spc)

                # Add spans
                for s in line.spans:
                    if not s.text:
                        continue
                    run = lp.add_run(s.text)
                    resolved = font_resolver.resolve_font(s.font)

                    # Fit text: check width and adjust spacing / font size
                    fit_res = font_resolver.fit_text(
                        text=s.text,
                        font_name=resolved.resolved_name,
                        font_size_pt=s.size,
                        target_width_pt=s.width if s.width > 0 else lw,
                    )

                    apply_khmer_run_properties(
                        run=run,
                        font_name=resolved.resolved_name,
                        font_size_pt=fit_res.adjusted_size,
                        is_bold=s.is_bold,
                        is_italic=s.is_italic,
                        color_hex=s.color,
                        spacing_twips=fit_res.spacing_twips,
                    )

    doc.save(str(output_path))
    _embed_fonts_in_docx(output_path, font_resolver._embedded_fonts)
    return output_path


# ── HYBRID / DISPATCHER ──────────────────────────────────────────────────

def build_docx(
    pdf_path: str | Path,
    output_path: str | Path,
    mode: str = "auto",  # 'auto', 'editable' (mode A), 'exact' (mode B)
) -> Path:
    """
    Main conversion entrypoint supporting Mode A, Mode B, and Auto hybrid selection.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    # 1. Analyze PDF
    doc_analysis = analyze_pdf(pdf_path)

    # 2. Extract with positions
    extracted_pages = extract_pdf_document(pdf_path)

    # 3. Setup font resolver with PyMuPDF doc for embedded font extraction
    fitz_doc = fitz.open(str(pdf_path))
    font_resolver = FontResolver(doc=fitz_doc)

    try:
        selected_mode = mode.lower()
        if selected_mode == "auto":
            selected_mode = doc_analysis.suggested_mode

        if selected_mode in ("exact", "ocr") or doc_analysis.suggested_mode == "exact":
            logger.info("Using Mode B (Exact Layout) for %s", pdf_path.name)
            return build_mode_b_exact(pdf_path, output_path, doc_analysis, extracted_pages, font_resolver)
        else:
            logger.info("Using Mode A (Editable) for %s", pdf_path.name)
            return build_mode_a_editable(pdf_path, output_path, doc_analysis, font_resolver)
    finally:
        fitz_doc.close()

