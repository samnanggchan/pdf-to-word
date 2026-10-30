"""
Step 3: Dynamic Font Resolution, Font Embedding, and Text Fitting.

Implements per-span font resolution:
  1. System font matching
  2. Normalized Khmer font mapping table
  3. PDF embedded font extraction & DOCX font obfuscation (.odttf)
  4. Fallback chain: Noto Sans Khmer -> Khmer UI -> Leelawadee UI -> Khmer OS Battambang
  5. OpenXML tagging: w:rFonts (ascii, hAnsi, cs, eastAsia), w:szCs, w:bCs, w:iCs, w:lang (w:bidi="km-KH")
  6. Text fitting: measures width via fontTools / PIL; compresses w:spacing and/or reduces font size by max 8%
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import ImageFont

from app.analyzer import SUBSET_PREFIX_RE

logger = logging.getLogger(__name__)

# Standard Khmer Font Map (Normalized key -> canonical Windows/Word font name)
KHMER_FONT_MAP: dict[str, str] = {
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
    "khmersangammn": "Khmer Sangam MN",
    "khmermn": "Khmer MN",
}

# Fallback hierarchy
FALLBACK_FONTS = [
    "Noto Sans Khmer",
    "Khmer UI",
    "Leelawadee UI",
    "Khmer OS Battambang",
]

# Standard directories where fonts might reside
SYSTEM_FONT_DIRS = [
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path(os.path.expanduser("~/.fonts")),
    Path("C:/Windows/Fonts"),
]


@dataclass
class ResolvedFont:
    """Result of resolving a PDF font to Word formatting & embedded assets."""
    original_name: str
    resolved_name: str
    is_embedded: bool = False
    embedded_data: bytes | None = None
    embedded_font_key: str | None = None  # GUID with brackets: {GUID}
    obfuscated_filename: str | None = None  # e.g. "font1.odttf"
    resolution_source: str = "fallback"  # 'system', 'map', 'embedded', 'fallback'


@dataclass
class FontFitResult:
    """Text fitting metrics."""
    original_size: float
    adjusted_size: float
    spacing_twips: int = 0  # 1/20 of a pt (negative compresses)
    width_ratio: float = 1.0


class FontResolver:
    """Manages font matching, embedded extraction, and text width fitting."""

    def __init__(self, doc: Any = None):
        self.doc = doc  # PyMuPDF fitz.Document if available
        self._system_fonts_cache: dict[str, Path] = {}
        self._resolved_cache: dict[str, ResolvedFont] = {}
        self._embedded_fonts_counter: int = 0
        self._embedded_fonts: dict[str, ResolvedFont] = {}
        self._scan_system_fonts()

    def _scan_system_fonts(self):
        """Build an index of system fonts by normalized lowercase name."""
        for d in SYSTEM_FONT_DIRS:
            if not d.exists():
                continue
            try:
                for p in d.rglob("*.[tT][tT][fF]"):
                    key = re.sub(r"[^a-z0-9]", "", p.stem.lower())
                    if key not in self._system_fonts_cache:
                        self._system_fonts_cache[key] = p
                for p in d.rglob("*.[oO][tT][fF]"):
                    key = re.sub(r"[^a-z0-9]", "", p.stem.lower())
                    if key not in self._system_fonts_cache:
                        self._system_fonts_cache[key] = p
            except Exception:
                pass

    def clean_font_name(self, raw_name: str | None) -> str:
        """Strip subset prefix (ABCDEF+Name) and clean formatting."""
        if not raw_name:
            return "Khmer OS Battambang"
        name = SUBSET_PREFIX_RE.sub("", raw_name.strip())
        return name

    def resolve_font(self, raw_font_name: str, xref: int = 0) -> ResolvedFont:
        """
        Resolve font through the 4-step hierarchy:
          1. System installed font with matching name
          2. Normalized Khmer font mapping table
          3. Embedded font extraction from PDF
          4. Fallback chain
        """
        if raw_font_name in self._resolved_cache:
            return self._resolved_cache[raw_font_name]

        cleaned = self.clean_font_name(raw_font_name)
        norm_key = re.sub(r"[^a-z0-9]", "", cleaned.lower())

        # 1. Direct system font matching
        if norm_key in self._system_fonts_cache:
            res = ResolvedFont(
                original_name=raw_font_name,
                resolved_name=cleaned,
                resolution_source="system",
            )
            self._resolved_cache[raw_font_name] = res
            return res

        # 2. Direct mapping table match (before stripping suffixes)
        if norm_key in KHMER_FONT_MAP:
            res = ResolvedFont(
                original_name=raw_font_name,
                resolved_name=KHMER_FONT_MAP[norm_key],
                resolution_source="map",
            )
            self._resolved_cache[raw_font_name] = res
            return res

        # Strip standard weight/style suffixes for mapping
        base_key = norm_key
        for suffix in ("bolditalic", "bold", "italic", "regular", "light", "medium", "semibold"):
            if base_key.endswith(suffix) and len(base_key) > len(suffix):
                test_key = base_key[: -len(suffix)]
                if test_key in KHMER_FONT_MAP or test_key in self._system_fonts_cache:
                    base_key = test_key
                    break

        if base_key in KHMER_FONT_MAP:
            mapped_name = KHMER_FONT_MAP[base_key]
            res = ResolvedFont(
                original_name=raw_font_name,
                resolved_name=mapped_name,
                resolution_source="map",
            )
            self._resolved_cache[raw_font_name] = res
            return res

        # Smart heuristics for Khmer font variants
        if "muol" in norm_key or "moul" in norm_key:
            res = ResolvedFont(original_name=raw_font_name, resolved_name="Khmer OS Muol Light", resolution_source="map")
            self._resolved_cache[raw_font_name] = res
            return res
        if "battambang" in norm_key or "sangam" in norm_key:
            res = ResolvedFont(original_name=raw_font_name, resolved_name="Khmer OS Battambang", resolution_source="map")
            self._resolved_cache[raw_font_name] = res
            return res
        if "siemreap" in norm_key:
            res = ResolvedFont(original_name=raw_font_name, resolved_name="Khmer OS Siemreap", resolution_source="map")
            self._resolved_cache[raw_font_name] = res
            return res

        # 3. Extract embedded font from PDF
        if self.doc and xref > 0:
            try:
                font_info = self.doc.extract_font(xref)
                if font_info and font_info[3]:  # font buffer bytes
                    font_buf = font_info[3]
                    font_ext = font_info[1] or "ttf"
                    if font_ext.lower() in ("ttf", "otf"):
                        self._embedded_fonts_counter += 1
                        guid = str(uuid.uuid4()).upper()
                        font_key = f"{{{guid}}}"
                        obf_filename = f"font{self._embedded_fonts_counter}.odttf"
                        res = ResolvedFont(
                            original_name=raw_font_name,
                            resolved_name=cleaned,
                            is_embedded=True,
                            embedded_data=font_buf,
                            embedded_font_key=font_key,
                            obfuscated_filename=obf_filename,
                            resolution_source="embedded",
                        )
                        self._embedded_fonts[cleaned] = res
                        self._resolved_cache[raw_font_name] = res
                        return res
            except Exception as e:
                logger.debug("Could not extract embedded font xref=%s: %s", xref, e)

        # 4. Fallback chain
        fallback = FALLBACK_FONTS[0]
        for f in FALLBACK_FONTS:
            f_key = re.sub(r"[^a-z0-9]", "", f.lower())
            if f_key in self._system_fonts_cache:
                fallback = f
                break

        res = ResolvedFont(
            original_name=raw_font_name,
            resolved_name=fallback,
            resolution_source="fallback",
        )
        self._resolved_cache[raw_font_name] = res
        return res

    def fit_text(
        self,
        text: str,
        font_name: str,
        font_size_pt: float,
        target_width_pt: float,
    ) -> FontFitResult:
        """
        Measure text width and fit within target_width_pt:
          • If wider: reduce w:spacing first, then reduce font size by at most 8%
          • If narrower: leave unchanged
        """
        if not text or target_width_pt <= 0:
            return FontFitResult(original_size=font_size_pt, adjusted_size=font_size_pt)

        # Measure rendered width
        measured_width = self._measure_string_width(text, font_name, font_size_pt)

        if measured_width <= target_width_pt:
            # Fits naturally
            return FontFitResult(
                original_size=font_size_pt,
                adjusted_size=font_size_pt,
                spacing_twips=0,
                width_ratio=measured_width / max(target_width_pt, 1.0),
            )

        # Overflow: calculate excess
        excess = measured_width - target_width_pt
        num_chars = len(text)

        # 1. First, reduce spacing (w:spacing in twips: 1 pt = 20 twips)
        # Max spacing reduction of -1.0 pt (-20 twips) per inter-character gap
        gaps = max(num_chars - 1, 1)
        spacing_needed_pt = excess / gaps
        allowed_spacing_pt = min(spacing_needed_pt, 1.0)
        spacing_twips = -int(round(allowed_spacing_pt * 20))

        # Remaining excess after spacing adjustment
        repaired_width = measured_width - (allowed_spacing_pt * gaps)

        adjusted_size = font_size_pt
        if repaired_width > target_width_pt:
            # 2. Reduce font size by at most 8%
            scale = target_width_pt / repaired_width
            max_reduction = 0.92  # at most 8% reduction
            factor = max(scale, max_reduction)
            adjusted_size = font_size_pt * factor

        return FontFitResult(
            original_size=font_size_pt,
            adjusted_size=adjusted_size,
            spacing_twips=spacing_twips,
            width_ratio=measured_width / max(target_width_pt, 1.0),
        )

    def _measure_string_width(self, text: str, font_name: str, font_size_pt: float) -> float:
        """Measure rendered width in points using PIL ImageFont or character heuristics."""
        norm_key = re.sub(r"[^a-z0-9]", "", font_name.lower())
        font_path = self._system_fonts_cache.get(norm_key)

        if font_path and font_path.exists():
            try:
                img_font = ImageFont.truetype(str(font_path), int(round(font_size_pt)))
                # getlength gives exact width in pixels at standard 72 DPI
                return float(img_font.getlength(text))
            except Exception:
                pass

        # Robust heuristic fallback based on character script
        width = 0.0
        for ch in text:
            cp = ord(ch)
            if 0x1780 <= cp <= 0x17FF:
                # Khmer characters
                if 0x17B6 <= cp <= 0x17D3:
                    # Dependent vowels and signs (combining / coeng) take minimal advance
                    width += font_size_pt * 0.15
                else:
                    # Consonants and independent vowels
                    width += font_size_pt * 0.65
            elif ch.isspace():
                width += font_size_pt * 0.28
            elif ch.isupper():
                width += font_size_pt * 0.68
            else:
                width += font_size_pt * 0.52
        return width


def obfuscate_font_data(font_bytes: bytes, guid_key: str) -> bytes:
    """
    Obfuscate font bytes according to ECMA-376 Part 4 font obfuscation standard.
    XORs the first 32 bytes with the 16-byte key derived from the GUID.
    """
    clean_guid = guid_key.replace("{", "").replace("}", "").replace("-", "")
    if len(clean_guid) != 32:
        return font_bytes

    # Form the 16-byte key with reversed byte order per standard
    key_bytes = bytearray.fromhex(clean_guid)
    # Reverse byte order of GUID fields
    rev_key = bytearray(16)
    rev_key[0:4] = key_bytes[0:4][::-1]
    rev_key[4:6] = key_bytes[4:6][::-1]
    rev_key[6:8] = key_bytes[6:8][::-1]
    rev_key[8:16] = key_bytes[8:16]

    out = bytearray(font_bytes)
    n = min(len(out), 32)
    for i in range(n):
        out[i] ^= rev_key[i % 16]
    return bytes(out)


def apply_khmer_run_properties(
    run: Any,
    font_name: str,
    font_size_pt: float,
    is_bold: bool = False,
    is_italic: bool = False,
    color_hex: str | None = None,
    spacing_twips: int = 0,
):
    """
    Apply comprehensive OpenXML typography properties to a python-docx Run:
      • w:rFonts: ascii, hAnsi, cs, eastAsia
      • w:sz and w:szCs (in half-points)
      • w:b, w:bCs, w:i, w:iCs
      • w:lang with w:bidi="km-KH"
      • w:spacing (character condensation/expansion)
    """
    run.font.name = font_name
    rPr = run._r.get_or_add_rPr()

    # 1. w:rFonts
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), font_name)

    # 2. Font size: w:sz and w:szCs in half-points
    half_pt = str(int(round(font_size_pt * 2)))
    sz = rPr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rPr.append(sz)
    sz.set(qn("w:val"), half_pt)

    szCs = rPr.find(qn("w:szCs"))
    if szCs is None:
        szCs = OxmlElement("w:szCs")
        rPr.append(szCs)
    szCs.set(qn("w:val"), half_pt)

    # 3. Bold: w:b and w:bCs
    if is_bold:
        run.bold = True
        if rPr.find(qn("w:bCs")) is None:
            rPr.append(OxmlElement("w:bCs"))

    # 4. Italic: w:i and w:iCs
    if is_italic:
        run.italic = True
        if rPr.find(qn("w:iCs")) is None:
            rPr.append(OxmlElement("w:iCs"))

    # 5. Language / Bidi: w:lang w:bidi="km-KH"
    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:bidi"), "km-KH")

    # 6. Spacing: w:spacing in twips
    if spacing_twips != 0:
        sp = rPr.find(qn("w:spacing"))
        if sp is None:
            sp = OxmlElement("w:spacing")
            rPr.append(sp)
        sp.set(qn("w:val"), str(spacing_twips))

    # 7. Color: w:color
    if color_hex and color_hex.startswith("#") and len(color_hex) == 7:
        color_val = color_hex[1:]
        col_elem = rPr.find(qn("w:color"))
        if col_elem is None:
            col_elem = OxmlElement("w:color")
            rPr.append(col_elem)
        col_elem.set(qn("w:val"), color_val)
