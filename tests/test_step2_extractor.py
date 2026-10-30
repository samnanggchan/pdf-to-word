"""
Tests for STEP 2: PDF Content Extractor with Exact Geometric Positions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.extractor import (
    extract_page_content,
    extract_pdf_document,
    rgb_tuple_to_hex,
    srgb_to_hex,
)
from tests.conftest import create_khmer_text_pdf, create_scanned_khmer_pdf


def test_color_conversions():
    # sRGB integer 0xFF0000 -> #FF0000
    assert srgb_to_hex(0xFF0000) == "#FF0000"
    assert srgb_to_hex(0x00FF00) == "#00FF00"
    assert srgb_to_hex(0x0000FF) == "#0000FF"
    assert srgb_to_hex(0x000000) == "#000000"

    # RGB tuple (1.0, 0.0, 0.0) -> #FF0000
    assert rgb_tuple_to_hex((1.0, 0.0, 0.0)) == "#FF0000"
    assert rgb_tuple_to_hex((0.5,)) == "#808080"
    assert rgb_tuple_to_hex(None) is None


def test_extract_khmer_text_pdf(tmp_path: Path):
    pdf_path = create_khmer_text_pdf(tmp_path / "text.pdf")
    pages = extract_pdf_document(pdf_path)

    assert len(pages) == 1
    page = pages[0]
    assert page.page_number == 1
    assert page.width > 500
    assert page.height > 700
    assert len(page.text_blocks) >= 1

    # Check text block, line, span hierarchy
    block = page.text_blocks[0]
    assert len(block.lines) >= 1
    line = block.lines[0]
    assert len(line.spans) >= 1

    span = line.spans[0]
    assert span.text
    assert span.size > 0
    assert span.bbox[2] > span.bbox[0]  # width > 0
    assert span.bbox[3] > span.bbox[1]  # height > 0
    assert span.color.startswith("#")
    assert span.is_khmer is True


def test_extract_scanned_pdf(tmp_path: Path):
    pdf_path = create_scanned_khmer_pdf(tmp_path / "scanned.pdf")
    pages = extract_pdf_document(pdf_path)

    assert len(pages) == 1
    page = pages[0]
    assert len(page.images) >= 1
    img = page.images[0]
    assert img.width > 0
    assert img.height > 0
    assert len(img.data) > 0
    assert img.bbox[2] > img.bbox[0]

