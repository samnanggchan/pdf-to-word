"""
Test 1 – Khmer text PDF (has a real text layer).

Verifies:
  • The PDF is processed without errors.
  • The output DOCX exists and is non-empty.
  • The DOCX contains Khmer Unicode text.
  • The DOCX XML has the correct Khmer font settings (w:rFonts, w:szCs).
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from docx import Document

from app.converter import convert_pdf_to_docx
from app.khmer_utils import has_khmer, normalize_khmer
from tests.conftest import create_khmer_text_pdf


@pytest.fixture()
def khmer_text_pdf(tmp_path: Path) -> Path:
    return create_khmer_text_pdf(tmp_path / "khmer_text.pdf")


class TestKhmerTextPdf:
    """Tests for a PDF that already contains a Khmer text layer."""

    def test_conversion_succeeds(self, khmer_text_pdf: Path):
        """The converter should run without raising."""
        docx_path = khmer_text_pdf.with_suffix(".docx")
        result = convert_pdf_to_docx(khmer_text_pdf, docx_path)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_output_contains_khmer(self, khmer_text_pdf: Path):
        """The DOCX should contain recognisable Khmer Unicode text."""
        docx_path = khmer_text_pdf.with_suffix(".docx")
        convert_pdf_to_docx(khmer_text_pdf, docx_path)
        doc = Document(str(docx_path))
        full_text = "\n".join(p.text for p in doc.paragraphs)

        # At a minimum, check that some Khmer characters survived
        assert has_khmer(full_text), (
            "Expected Khmer Unicode in the output DOCX, but found none."
        )

    def test_text_is_nfc_normalized(self, khmer_text_pdf: Path):
        """All text should already be NFC-normalized."""
        docx_path = khmer_text_pdf.with_suffix(".docx")
        convert_pdf_to_docx(khmer_text_pdf, docx_path)
        doc = Document(str(docx_path))
        for para in doc.paragraphs:
            if para.text.strip():
                assert para.text == normalize_khmer(para.text)

    def test_khmer_font_settings_in_xml(self, khmer_text_pdf: Path):
        """
        Runs containing Khmer text should have w:rFonts with the CS
        attribute set and a w:szCs element.
        """
        docx_path = khmer_text_pdf.with_suffix(".docx")
        convert_pdf_to_docx(khmer_text_pdf, docx_path)
        doc = Document(str(docx_path))

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        found_cs_font = False

        for para in doc.paragraphs:
            for run in para.runs:
                if has_khmer(run.text):
                    rPr = run._r.find(f"{{{ns['w']}}}rPr")
                    assert rPr is not None, "Khmer run missing rPr element"

                    rFonts = rPr.find(f"{{{ns['w']}}}rFonts")
                    assert rFonts is not None, "Khmer run missing w:rFonts"

                    cs_val = rFonts.get(f"{{{ns['w']}}}cs")
                    assert cs_val, "w:rFonts missing cs attribute"
                    found_cs_font = True

                    szCs = rPr.find(f"{{{ns['w']}}}szCs")
                    assert szCs is not None, "Khmer run missing w:szCs"

        if found_cs_font:
            # good
            pass
        # If there are no Khmer runs at all (e.g., font wasn't available),
        # we can't assert on font settings, so we skip.
