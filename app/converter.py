"""
End-to-End Orchestrator Pipeline for Khmer PDF to Word Conversion.

Integrates:
  • Step 1: PDF Analysis (app.analyzer)
  • Step 2: Content Extraction (app.extractor)
  • Step 3: Dynamic Font Resolution (app.font_resolver)
  • Step 4: Output Modes (app.docx_modes: Mode A Editable & Mode B Exact Layout)
  • Step 5: Khmer Text Correctness (app.khmer_utils)
  • Step 6: Visual Verification Loop (app.verifier)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from app.analyzer import DocumentAnalysis, analyze_pdf
from app.config import MAX_FILE_SIZE_BYTES
from app.docx_modes import build_docx
from app.extractor import ExtractedPage, extract_pdf_document
from app.khmer_utils import normalize_khmer, ocr_page_in_memory
from app.verifier import VerificationReport, run_visual_verification_loop

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """Metadata and extracted text for previewing a page."""
    page_number: int
    text: str
    width: float
    height: float
    has_text_layer: bool
    used_ocr: bool = False
    image_count: int = 0
    table_count: int = 0


@dataclass
class ConversionResult:
    """Comprehensive result of a PDF to DOCX conversion."""
    docx_path: Path
    total_pages: int
    pages: list[PageResult] = field(default_factory=list)
    used_ocr: bool = False
    word_count: int = 0
    char_count: int = 0
    raw_text: str = ""
    applied_fonts: list[str] = field(default_factory=list)
    suggested_mode: str = "layout"
    verification_report: VerificationReport | None = None


def convert_pdf(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    mode: str = "auto",  # 'auto', 'editable', 'exact'
    run_verification: bool = False,
) -> ConversionResult:
    """
    High-level conversion pipeline.
    Takes a PDF and outputs a DOCX matching original layout and Khmer typography.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # File size validation
    file_size = pdf_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size {file_size / (1024 * 1024):.1f} MB exceeds maximum limit "
            f"of {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB"
        )

    if output_path is None:
        output_path = pdf_path.with_suffix(".docx")
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting conversion [%s]: %s -> %s", mode, pdf_path.name, output_path.name)

    # 1. Analyze PDF (Step 1)
    analysis = analyze_pdf(pdf_path)

    # 2. Extract with positions (Step 2)
    extracted = extract_pdf_document(pdf_path)

    # 3. Handle OCR fallback for scanned pages if needed
    used_ocr = False
    page_results: list[PageResult] = []

    doc_fitz = fitz.open(str(pdf_path))
    try:
        for idx, pa in enumerate(analysis.pages):
            page_text = ""
            page_used_ocr = False

            if pa.needs_ocr:
                try:
                    page_text = ocr_page_in_memory(doc_fitz[idx], dpi=300)
                    page_used_ocr = True
                    used_ocr = True
                except Exception as e:
                    logger.warning("OCR failed on page %s: %s", pa.page_number, e)
                    page_text = ""
            else:
                ep = extracted[idx]
                page_text = ep.text

            page_text = normalize_khmer(page_text)

            page_results.append(
                PageResult(
                    page_number=pa.page_number,
                    text=page_text,
                    width=pa.width,
                    height=pa.height,
                    has_text_layer=pa.has_text_layer,
                    used_ocr=page_used_ocr,
                    image_count=pa.image_count,
                    table_count=pa.table_count,
                )
            )
    finally:
        doc_fitz.close()

    # 4. Generate DOCX with Mode A / Mode B / Hybrid (Steps 3 & 4)
    out_file = build_docx(pdf_path, output_path, mode=mode)

    # 5. Visual verification loop if requested (Step 6)
    verif_report = None
    if run_verification:
        verif_report = run_visual_verification_loop(
            original_pdf=pdf_path,
            docx_path=out_file,
            mode=mode,
        )

    # 6. Metadata summary
    all_text = "\n\n".join(p.text for p in page_results if p.text.strip())
    total_words = sum(len(p.text.split()) for p in page_results)
    total_chars = len(all_text)
    applied_fonts = [f.clean_name for f in analysis.all_fonts if f.clean_name]

    return ConversionResult(
        docx_path=out_file,
        total_pages=analysis.total_pages,
        pages=page_results,
        used_ocr=used_ocr,
        word_count=total_words,
        char_count=total_chars,
        raw_text=all_text,
        applied_fonts=applied_fonts or ["Khmer OS Battambang"],
        suggested_mode=analysis.suggested_mode,
        verification_report=verif_report,
    )


def convert_pdf_to_docx(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    mode: str = "auto",
) -> Path:
    """Convenience function returning Path to generated DOCX."""
    return convert_pdf(pdf_path, output_path, mode=mode).docx_path
