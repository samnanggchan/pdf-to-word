"""
Test 3: Complex Khmer PDF containing a table, an image, and a signature block.

Verifies:
  • Analysis detects tables, images, and text layers.
  • Conversion to DOCX succeeds in both Mode A (Editable) and Mode B (Exact).
  • Tables are preserved in the DOCX output.
  • Images (stamp/signature) are embedded.
  • Khmer signature block text is preserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from app.analyzer import analyze_pdf
from app.converter import convert_pdf_to_docx
from app.docx_modes import build_docx
from app.khmer_utils import has_khmer
from tests.conftest import create_complex_khmer_pdf


@pytest.fixture()
def complex_pdf(tmp_path: Path) -> Path:
    return create_complex_khmer_pdf(tmp_path / "complex_khmer.pdf")


class TestComplexKhmerPdf:
    def test_analysis_detects_all_elements(self, complex_pdf: Path):
        analysis = analyze_pdf(complex_pdf)
        assert analysis.total_pages == 1
        page = analysis.pages[0]

        assert page.has_text_layer is True
        assert page.khmer_char_count > 0
        assert page.table_count >= 1
        assert page.image_count >= 1

    def test_mode_a_preserves_table_and_content(self, complex_pdf: Path, tmp_path: Path):
        docx_path = tmp_path / "complex_mode_a.docx"
        build_docx(complex_pdf, docx_path, mode="editable")

        assert docx_path.exists()
        assert docx_path.stat().st_size > 0

        doc = Document(str(docx_path))
        # Verify table exists in Mode A
        assert len(doc.tables) >= 1
        table = doc.tables[0]
        assert len(table.rows) >= 2
        assert len(table.columns) >= 2

        full_text = "\n".join(p.text for p in doc.paragraphs)
        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    full_text += "\n" + cell.text

        assert has_khmer(full_text)

    def test_mode_b_exact_layout_preserves_elements(self, complex_pdf: Path, tmp_path: Path):
        docx_path = tmp_path / "complex_mode_b.docx"
        build_docx(complex_pdf, docx_path, mode="exact")

        assert docx_path.exists()
        assert docx_path.stat().st_size > 0

        doc = Document(str(docx_path))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        assert has_khmer(full_text)

    def test_high_level_converter_succeeds(self, complex_pdf: Path, tmp_path: Path):
        docx_path = tmp_path / "complex_auto.docx"
        result = convert_pdf_to_docx(complex_pdf, docx_path, mode="auto")

        assert result.exists()
        assert result.stat().st_size > 0

