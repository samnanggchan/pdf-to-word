"""
Test 2 – Scanned Khmer PDF (no text layer, OCR required).

Verifies:
  • The converter detects the absence of a text layer.
  • OCR is invoked (or at least attempted).
  • The output DOCX exists and is non-empty.
  • If Tesseract + khm data is available, the output contains Khmer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from docx import Document

from app.converter import convert_pdf_to_docx
from app.khmer_utils import has_khmer
from app.pdf_extractor import extract_pdf
from tests.conftest import create_scanned_khmer_pdf

# Check whether Tesseract is actually installed on this machine
_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


@pytest.fixture()
def scanned_khmer_pdf(tmp_path: Path) -> Path:
    return create_scanned_khmer_pdf(tmp_path / "scanned_khmer.pdf")


class TestScannedKhmerPdf:
    """Tests for a scanned (image-only) Khmer PDF."""

    def test_no_text_layer_detected(self, scanned_khmer_pdf: Path):
        """
        The extractor should recognise that the scanned PDF has no
        meaningful text layer and should flag pages as needing OCR.
        """
        pages = extract_pdf(scanned_khmer_pdf)
        assert len(pages) >= 1
        # At least one page should have used OCR (or attempted to)
        # Note: if Tesseract isn't installed the text will be empty,
        # but used_ocr should still be True because the code path was
        # triggered.
        assert any(p.used_ocr for p in pages), (
            "Expected the scanned PDF to trigger the OCR fallback path."
        )

    def test_conversion_succeeds(self, scanned_khmer_pdf: Path):
        """The converter should not crash even for scanned PDFs."""
        docx_path = scanned_khmer_pdf.with_suffix(".docx")
        result = convert_pdf_to_docx(scanned_khmer_pdf, docx_path)
        assert result.exists()
        assert result.stat().st_size > 0

    @pytest.mark.skipif(
        not _TESSERACT_AVAILABLE,
        reason="Tesseract is not installed on this machine.",
    )
    def test_ocr_produces_khmer_text(self, scanned_khmer_pdf: Path):
        """
        When Tesseract *is* available (e.g., in Docker), the OCR output
        should contain at least some Khmer characters.
        """
        docx_path = scanned_khmer_pdf.with_suffix(".docx")
        convert_pdf_to_docx(scanned_khmer_pdf, docx_path)
        doc = Document(str(docx_path))
        full_text = "\n".join(p.text for p in doc.paragraphs)

        # This assertion may still fail if the khm traineddata is missing,
        # but on a correctly configured Docker image it should pass.
        assert has_khmer(full_text), (
            "Expected Khmer text from OCR but found none. "
            "Is tesseract-ocr-khm installed?"
        )

    def test_output_has_images_or_text(self, scanned_khmer_pdf: Path):
        """
        The output should have either extracted text or the original
        image preserved.
        """
        pages = extract_pdf(scanned_khmer_pdf)
        has_content = any(p.text.strip() or p.images for p in pages)
        assert has_content, "Expected some content (text or images) from the scanned PDF."
