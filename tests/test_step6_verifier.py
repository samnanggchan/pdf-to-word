"""
Tests for STEP 6: Visual Verification Loop & SSIM Quality Assurance.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.docx_modes import build_docx
from app.verifier import (
    compute_image_ssim,
    find_libreoffice,
    render_pdf_pages_to_images,
    run_visual_verification_loop,
)
from tests.conftest import create_khmer_text_pdf


def test_compute_image_ssim_identical():
    img1 = Image.new("RGB", (200, 200), "white")
    draw1 = ImageDraw.Draw(img1)
    draw1.text((30, 50), "សួស្តីកម្ពុជា", fill="black")

    img2 = img1.copy()
    score = compute_image_ssim(img1, img2)
    assert score == pytest.approx(1.0, abs=1e-4)


def test_compute_image_ssim_different():
    img1 = Image.new("RGB", (200, 200), "white")
    draw1 = ImageDraw.Draw(img1)
    draw1.rectangle([20, 20, 180, 180], fill="black")

    img2 = Image.new("RGB", (200, 200), "white")
    # Completely different image
    score = compute_image_ssim(img1, img2)
    assert score < 0.85


def test_render_pdf_pages_to_images(tmp_path: Path):
    pdf_path = create_khmer_text_pdf(tmp_path / "test_render.pdf")
    imgs = render_pdf_pages_to_images(pdf_path, dpi=150)
    assert len(imgs) == 1
    assert imgs[0].width > 0
    assert imgs[0].height > 0


def test_verification_loop_graceful_without_lo(tmp_path: Path):
    pdf_path = create_khmer_text_pdf(tmp_path / "test_verif.pdf")
    docx_path = tmp_path / "test_verif.docx"
    build_docx(pdf_path, docx_path, mode="editable")

    report = run_visual_verification_loop(pdf_path, docx_path, mode="editable")
    assert isinstance(report.warnings, list)
    # If LibreOffice is not installed, it notes it in report without crashing
    if not find_libreoffice():
        assert report.libreoffice_available is False
        assert len(report.warnings) >= 1

