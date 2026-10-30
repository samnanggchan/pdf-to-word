"""
Step 6: Visual Verification Loop & SSIM Quality Assurance.

Workflow:
  1. Convert DOCX to PDF via LibreOffice headless (if installed).
  2. Render original PDF and generated PDF pages to PNG at 150 DPI using PyMuPDF.
  3. Compute per-page SSIM (Structural Similarity Index) using scikit-image.
  4. If SSIM < 0.92 on a page:
     Retry with Mode B (Exact Layout) or font fit adjustments, up to 3 iterations.
  5. Generate a structured Verification Report.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger(__name__)

# Common paths where LibreOffice binary might be located
LIBREOFFICE_CANDIDATES = [
    "libreoffice",
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/libreoffice",
    "/usr/bin/soffice",
    "C:/Program Files/LibreOffice/program/soffice.exe",
    "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
]


@dataclass
class VerificationReport:
    """Detailed visual verification and quality assurance report."""
    page_ssim: list[float] = field(default_factory=list)
    average_ssim: float = 0.0
    passed_threshold: bool = False
    iterations_used: int = 1
    libreoffice_available: bool = False
    substituted_fonts: list[str] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def find_libreoffice() -> str | None:
    """Return path to executable LibreOffice/soffice binary if present."""
    for cand in LIBREOFFICE_CANDIDATES:
        found = shutil.which(cand)
        if found:
            return found
        if Path(cand).exists() and os.access(cand, os.X_OK):
            return cand
    return None


def convert_docx_to_pdf_libreoffice(docx_path: str | Path, out_dir: str | Path) -> Path | None:
    """Convert a DOCX to PDF using LibreOffice in headless mode."""
    lo_bin = find_libreoffice()
    if not lo_bin:
        return None

    docx_path = Path(docx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        lo_bin,
        "--headless",
        "--convert-to",
        "pdf",
        str(docx_path),
        "--outdir",
        str(out_dir),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if res.returncode == 0:
            expected_pdf = out_dir / docx_path.with_suffix(".pdf").name
            if expected_pdf.exists():
                return expected_pdf
    except Exception as e:
        logger.warning("LibreOffice conversion failed: %s", e)
    return None


def render_pdf_pages_to_images(pdf_path: str | Path, dpi: int = 150) -> list[Image.Image]:
    """Render all pages of a PDF to PIL Images at specified DPI using PyMuPDF."""
    doc = fitz.open(str(pdf_path))
    images: list[Image.Image] = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        images.append(img)
    doc.close()
    return images


def compute_image_ssim(img_orig: Image.Image, img_gen: Image.Image) -> float:
    """
    Compute Structural Similarity Index (SSIM) between two images.
    Converts to grayscale and aligns dimensions if needed.
    """
    # Convert to grayscale
    g_orig = img_orig.convert("L")
    g_gen = img_gen.convert("L")

    # Align dimensions if slightly different
    if g_orig.size != g_gen.size:
        g_gen = g_gen.resize(g_orig.size, Image.Resampling.BILINEAR)

    arr_orig = np.array(g_orig, dtype=np.uint8)
    arr_gen = np.array(g_gen, dtype=np.uint8)

    score, _ = ssim(arr_orig, arr_gen, full=True, data_range=255)
    return float(max(0.0, min(1.0, score)))


def run_visual_verification_loop(
    original_pdf: str | Path,
    docx_path: str | Path,
    mode: str = "auto",
    target_ssim: float = 0.92,
    max_retries: int = 3,
) -> VerificationReport:
    """
    Run the visual verification and optimization loop:
      • Compares original PDF vs generated DOCX
      • If SSIM < target_ssim on any page, retries with Mode B (Exact Layout)
    """
    from app.docx_modes import build_docx

    original_pdf = Path(original_pdf)
    docx_path = Path(docx_path)
    report = VerificationReport()

    lo_bin = find_libreoffice()
    if not lo_bin:
        report.libreoffice_available = False
        report.warnings.append(
            "LibreOffice headless is not available on this system. "
            "Automated visual SSIM comparison skipped. "
            "Install LibreOffice or run in Docker for full visual verification."
        )
        return report

    report.libreoffice_available = True

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        orig_imgs = render_pdf_pages_to_images(original_pdf, dpi=150)

        current_mode = mode
        for iteration in range(1, max_retries + 1):
            report.iterations_used = iteration

            # Convert DOCX to PDF
            conv_pdf = convert_docx_to_pdf_libreoffice(docx_path, tmp_path)
            if not conv_pdf or not conv_pdf.exists():
                report.warnings.append("Could not generate verification PDF from DOCX via LibreOffice.")
                break

            gen_imgs = render_pdf_pages_to_images(conv_pdf, dpi=150)

            # Compute SSIM per page
            page_scores: list[float] = []
            num_pages = min(len(orig_imgs), len(gen_imgs))
            for i in range(num_pages):
                score = compute_image_ssim(orig_imgs[i], gen_imgs[i])
                page_scores.append(score)

            report.page_ssim = page_scores
            report.average_ssim = float(np.mean(page_scores)) if page_scores else 0.0

            # Check if all pages pass
            all_passed = bool(page_scores and all(s >= target_ssim for s in page_scores))
            if all_passed or iteration >= max_retries:
                report.passed_threshold = all_passed
                break

            # If failed and was in Mode A, retry with Mode B (Exact Layout)
            if current_mode != "exact":
                logger.info(
                    "Iteration %d: Average SSIM %.3f < %.2f. Retrying with Mode B (Exact Layout)...",
                    iteration,
                    report.average_ssim,
                    target_ssim,
                )
                current_mode = "exact"
                build_docx(original_pdf, docx_path, mode="exact")
            else:
                # Mode B already used
                break

    return report

