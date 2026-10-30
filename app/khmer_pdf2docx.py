"""
khmer_pdf2docx.py
Convert PDF -> DOCX while keeping Khmer fonts (Muol, Battambang, Siemreap, Noto...)
and layout as close as possible to the original.

CLI:  python khmer_pdf2docx.py input.pdf output.docx [--ocr]
"""
from __future__ import annotations

import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from pdf2docx import Converter

logger = logging.getLogger(__name__)

KHMER_RE = re.compile(r"[\u1780-\u17FF\u19E0-\u19FF]")
SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")  # e.g. ABCDEF+KhmerOSBattambang
DEFAULT_FONT = "Khmer OS Battambang"
HEADING_FONT = "Khmer OS Muol Light"

# Normalized key (lowercase letters/digits only) -> real font name installed on Windows/Word
FONT_MAP = {
    "khmerosbattambang": "Khmer OS Battambang",
    "khmerosmuollight": "Khmer OS Muol Light",
    "khmerosmuol": "Khmer OS Muol",
    "khmerosmuolpali": "Khmer OS Muol Pali",
    "khmerossiemreap": "Khmer OS Siemreap",
    "khmerosbokor": "Khmer OS Bokor",
    "khmerosfasthand": "Khmer OS Fasthand",
    "khmerosfreehand": "Khmer OS Freehand",
    "khmeroscontent": "Khmer OS Content",
    "khmerosdangrek": "Khmer OS Dangrek",
    "khmerosdiecasting": "Khmer OS Metal Chrieng",
    "khmerosmetalchrieng": "Khmer OS Metal Chrieng",
    "khmerosniroth": "Khmer OS Niroth",
    "khmerossystem": "Khmer OS System",
    "khmerosteuk": "Khmer OS Taprom",
    "khmerostaprom": "Khmer OS Taprom",
    "khmerosoperational": "Khmer OS",
    "khmeros": "Khmer OS",
    "khmerui": "Khmer UI",
    "daunpenh": "DaunPenh",
    "moul": "Khmer OS Muol Light",
    "moullight": "Khmer OS Muol Light",
    "moulpali": "Khmer OS Muol Pali",
    "battambang": "Khmer OS Battambang",
    "siemreap": "Khmer OS Siemreap",
    "bokor": "Khmer OS Bokor",
    "fasthand": "Khmer OS Fasthand",
    "freehand": "Khmer OS Freehand",
    "content": "Khmer OS Content",
    "notosanskhmer": "Noto Sans Khmer",
    "notoserifkhmer": "Noto Serif Khmer",
    "kantumruy": "Kantumruy Pro",
    "kantumruypro": "Kantumruy Pro",
    "leelawadeeui": "Leelawadee UI",
    "nokora": "Nokora",
    "hanuman": "Hanuman",
    "khmersangammn": "Khmer OS Battambang",
    "khmermn": "Khmer OS Battambang",
}

# Fonts that put Khmer glyphs on Latin code points -> text will look like gibberish when extracted
LEGACY_HINTS = ("limon", "abc", "khek", "zgm", "tact", "kmer")


def clean_font_name(raw: str | None) -> str | None:
    """'ABCDEF+KhmerOSMuolLight-Bold' -> 'Khmer OS Muol Light'."""
    if not raw:
        return None
    name = SUBSET_PREFIX_RE.sub("", raw)
    name = re.split(r"[-,]", name)[0].strip()
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    for suffix in ("bold", "italic", "regular", "light", "medium", "semibold"):
        if key.endswith(suffix) and key[: -len(suffix)] in FONT_MAP:
            key = key[: -len(suffix)]
    if key in FONT_MAP:
        return FONT_MAP[key]

    # Smart heuristics for Khmer font variants
    if "muol" in key or "moul" in key:
        return "Khmer OS Muol Light"
    if "battambang" in key or "sangam" in key:
        return "Khmer OS Battambang"
    if "siemreap" in key:
        return "Khmer OS Siemreap"
    if "bokor" in key:
        return "Khmer OS Bokor"
    if "content" in key:
        return "Khmer OS Content"
    if "fasthand" in key:
        return "Khmer OS Fasthand"
    if "freehand" in key:
        return "Khmer OS Freehand"
    if "noto" in key and "khmer" in key:
        return "Noto Sans Khmer"
    if "khmer" in key:
        return name  # unknown Khmer font: keep its own name
    return None


def normalize_khmer(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u200b\u200b", "\u200b")      # duplicate ZWSP
    text = re.sub(r"[\u200c\u200d\u2060\ufeff]", "", text)  # stray invisible chars (keep ZWSP U+200B)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def detect_pdf(pdf_path: str) -> dict:
    """Check whether the PDF has a usable Khmer text layer or needs OCR / legacy-font conversion."""
    doc = fitz.open(pdf_path)
    total, khmer, legacy = 0, 0, False
    detected_fonts = set()

    for page in doc:
        txt = page.get_text()
        total += len(txt.strip())
        khmer += len(KHMER_RE.findall(txt))
        for f in page.get_fonts():
            font_name = f[3]
            clean = clean_font_name(font_name)
            if clean:
                detected_fonts.add(clean)
            if any(h in font_name.lower() for h in LEGACY_HINTS):
                legacy = True
    pages = len(doc)
    doc.close()
    return {
        "pages": pages,
        "chars": total,
        "khmer_chars": khmer,
        "has_text_layer": total > 20 * pages,
        "legacy_font_suspected": legacy and khmer == 0,
        "detected_fonts": sorted(detected_fonts),
    }


def _set_run_khmer(run, font: str):
    run.font.name = font
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), font)
    # complex-script size / bold must mirror normal size / bold, or Word shows Khmer at 10pt
    sz = rPr.find(qn("w:sz"))
    if sz is not None:
        szcs = rPr.find(qn("w:szCs"))
        if szcs is None:
            szcs = OxmlElement("w:szCs")
            rPr.append(szcs)
        szcs.set(qn("w:val"), sz.get(qn("w:val")))
    if rPr.find(qn("w:b")) is not None and rPr.find(qn("w:bCs")) is None:
        rPr.append(OxmlElement("w:bCs"))
    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:bidi"), "km-KH")



def _iter_paragraphs(doc):
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
    for s in doc.sections:
        for part in (s.header, s.footer):
            for p in part.paragraphs:
                yield p


def fix_khmer_fonts(docx_path: str, default_font: str = DEFAULT_FONT) -> dict:
    """Fix all Khmer runs in the DOCX to use proper fonts and complex script styling."""
    doc = Document(docx_path)
    applied_fonts = set()
    runs_fixed = 0

    # Optional legacy converter
    try:
        from app.khmer_utils import is_legacy_font, legacy_to_unicode
        has_legacy_utils = True
    except ImportError:
        try:
            from khmer_utils import is_legacy_font, legacy_to_unicode
            has_legacy_utils = True
        except ImportError:
            has_legacy_utils = False

    for p in _iter_paragraphs(doc):
        for run in p.runs:
            rFonts = run._r.get_or_add_rPr().find(qn("w:rFonts"))
            raw = None
            if rFonts is not None:
                raw = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi")) or rFonts.get(qn("w:eastAsia"))
            raw = raw or run.font.name

            # Check if this run has legacy font text
            if has_legacy_utils and raw and is_legacy_font(raw):
                run.text = legacy_to_unicode(run.text, raw)

            if not KHMER_RE.search(run.text):
                continue

            run.text = normalize_khmer(run.text)
            font = clean_font_name(raw) or default_font
            _set_run_khmer(run, font)
            applied_fonts.add(font)
            runs_fixed += 1

    # document-wide defaults so new text typed later is also Khmer-safe
    styles = doc.styles.element
    rpr_default = styles.find(".//" + qn("w:rPrDefault"))
    if rpr_default is not None:
        rpr = rpr_default.find(qn("w:rPr"))
        if rpr is not None:
            rf = rpr.find(qn("w:rFonts"))
            if rf is None:
                rf = OxmlElement("w:rFonts")
                rpr.insert(0, rf)
            rf.set(qn("w:cs"), default_font)
    doc.save(docx_path)

    return {
        "applied_fonts": sorted(applied_fonts) if applied_fonts else [default_font],
        "runs_fixed": runs_fixed,
    }


def ocr_to_docx(pdf_path: str, docx_path: str, font: str = DEFAULT_FONT, dpi: int = 300, lang: str = "khm+eng") -> dict:
    """Fallback for scanned PDFs. Needs tesseract + khm language data."""
    import pytesseract
    from PIL import Image

    src = fitz.open(pdf_path)
    out = Document()
    total_paras = 0

    for i, page in enumerate(src):
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        text = pytesseract.image_to_string(img, lang=lang, config="--psm 4")
        for para in re.split(r"\n\s*\n", text):
            para = normalize_khmer(" ".join(para.split("\n")).strip())
            if not para:
                continue
            p = out.add_paragraph()
            run = p.add_run(para)
            run.font.size = Pt(12)
            _set_run_khmer(run, font)
            rPr = run._r.get_or_add_rPr()
            szcs = OxmlElement("w:szCs")
            szcs.set(qn("w:val"), "24")
            rPr.append(szcs)
            total_paras += 1
        if i < len(src) - 1:
            out.add_page_break()
    src.close()
    out.save(docx_path)

    return {"applied_fonts": [font], "runs_fixed": total_paras}


def convert(pdf_path: str, docx_path: str, mode: str = "auto", default_font: str = DEFAULT_FONT) -> dict:
    """mode: 'auto' | 'text' | 'ocr'. Returns a report dict."""
    info = detect_pdf(pdf_path)
    use_ocr = mode == "ocr" or (mode == "auto" and not info["has_text_layer"])
    report = {**info, "method": "ocr" if use_ocr else "text", "warnings": [], "applied_fonts": []}

    if use_ocr:
        ocr_res = ocr_to_docx(pdf_path, docx_path, default_font)
        report["applied_fonts"] = ocr_res["applied_fonts"]
        report["warnings"].append("OCR output is plain text; layout/fonts are not preserved.")
        return report

    cv = Converter(pdf_path)
    try:
        cv.convert(docx_path, start=0, end=None)
    finally:
        cv.close()

    fix_res = fix_khmer_fonts(docx_path, default_font)
    report["applied_fonts"] = fix_res["applied_fonts"]

    if info["legacy_font_suspected"]:
        report["warnings"].append(
            "PDF seems to use a legacy (non-Unicode) Khmer font like Limon/ABC. "
            "Text was automatically converted to Khmer Unicode."
        )
    return report


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode = "ocr" if "--ocr" in sys.argv else "auto"
    rep = convert(sys.argv[1], sys.argv[2], mode)
    print(rep)