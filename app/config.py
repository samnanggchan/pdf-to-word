"""
Application configuration and constants.
"""

import os
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# ── Upload limits ───────────────────────────────────────────────────────
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# ── OCR settings ────────────────────────────────────────────────────────
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "khm+eng")
OCR_DPI = int(os.getenv("OCR_DPI", "300"))

# ── Khmer font settings ────────────────────────────────────────────────
# Primary Khmer font for the output DOCX.  Falls back in order.
KHMER_FONT_CANDIDATES = [
    "Khmer OS Battambang",
    "Noto Sans Khmer",
    "Khmer OS",
]
KHMER_FONT = os.getenv("KHMER_FONT", KHMER_FONT_CANDIDATES[0])
KHMER_FONT_SIZE_PT = int(os.getenv("KHMER_FONT_SIZE_PT", "12"))

# ── Text-layer detection thresholds ─────────────────────────────────────
# Minimum ratio of "real" text characters vs total extracted chars to
# consider a page as having a usable text layer.
TEXT_LAYER_MIN_RATIO = float(os.getenv("TEXT_LAYER_MIN_RATIO", "0.3"))
# Minimum number of characters on a page before we bother checking ratio.
TEXT_LAYER_MIN_CHARS = int(os.getenv("TEXT_LAYER_MIN_CHARS", "20"))
