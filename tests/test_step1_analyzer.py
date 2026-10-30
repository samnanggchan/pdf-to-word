"""
Tests for STEP 1: PDF Document & Page Analyzer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analyzer import analyze_pdf, clean_font_family_name, is_legacy_font_name
from tests.conftest import create_khmer_text_pdf, create_scanned_khmer_pdf


def test_clean_font_family_name():
    assert clean_font_family_name("ABCDEF+KhmerOSBattambang") == "KhmerOSBattambang"
    assert clean_font_family_name("XYZABC+NotoSansKhmer-Bold") == "NotoSansKhmer-Bold"
    assert clean_font_family_name("Arial") == "Arial"
    assert clean_font_family_name(None) == "Unknown"


def test_is_legacy_font_name():
    assert is_legacy_font_name("Limon S1") is True
    assert is_legacy_font_name("ABC-PhnomPenh") is True
    assert is_legacy_font_name("Khmer OS Battambang") is False
    assert is_legacy_font_name("Noto Sans Khmer") is False


def test_analyze_khmer_text_pdf(tmp_path: Path):
    pdf_path = create_khmer_text_pdf(tmp_path / "text.pdf")
    analysis = analyze_pdf(pdf_path)

    assert analysis.total_pages == 1
    assert len(analysis.pages) == 1
    page = analysis.pages[0]
    assert page.width > 500
    assert page.height > 700
    assert page.rotation == 0
    assert page.has_text_layer is True
    assert page.khmer_char_count > 0
    assert page.needs_ocr is False
    assert "left" in page.margins
    assert "top" in page.margins


def test_analyze_scanned_pdf(tmp_path: Path):
    pdf_path = create_scanned_khmer_pdf(tmp_path / "scanned.pdf")
    analysis = analyze_pdf(pdf_path)

    assert analysis.total_pages == 1
    page = analysis.pages[0]
    assert page.has_text_layer is False
    assert page.image_count >= 1
    assert page.needs_ocr is True
    assert analysis.has_scanned_pages is True


def test_analyze_sample_fixture():
    fixture_path = Path("tests/fixtures/sample_khmer.pdf")
    if fixture_path.exists():
        analysis = analyze_pdf(fixture_path)
        assert analysis.total_pages >= 1
        page = analysis.pages[0]
        assert page.has_text_layer is True
        assert page.khmer_char_count > 0
        assert len(analysis.all_fonts) >= 1

