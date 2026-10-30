"""
Step 2: PDF Content Extractor with Exact Geometric Positions.

Extracts per page:
  • Text blocks, lines, and spans with exact bbox, font name, size, color, bold/italic, and origin
  • Embedded images with their exact placed bounding boxes
  • Vector drawings (lines, rectangles, fills, stroke widths, paths)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

KHMER_RE = re.compile(r"[\u1780-\u17FF\u19E0-\u19FF]")


def srgb_to_hex(color_int: int) -> str:
    """Convert an sRGB integer color from PyMuPDF to '#RRGGBB'."""
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_tuple_to_hex(rgb: tuple[float, ...] | None) -> str | None:
    """Convert float RGB tuple (0.0 - 1.0) to '#RRGGBB'."""
    if not rgb:
        return None
    if len(rgb) == 1:
        # Grayscale
        v = int(round(rgb[0] * 255))
        return f"#{v:02X}{v:02X}{v:02X}"
    elif len(rgb) >= 3:
        r = int(round(rgb[0] * 255))
        g = int(round(rgb[1] * 255))
        b = int(round(rgb[2] * 255))
        return f"#{r:02X}{g:02X}{b:02X}"
    return None


@dataclass
class TextSpan:
    """A styled run of text with precise geometric bounds."""
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    font: str
    size: float  # points
    color: str  # '#RRGGBB'
    flags: int = 0
    is_bold: bool = False
    is_italic: bool = False
    origin: tuple[float, float] = (0.0, 0.0)  # (x, y) baseline origin
    is_khmer: bool = False

    @property
    def width(self) -> float:
        return max(0.0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return max(0.0, self.bbox[3] - self.bbox[1])


@dataclass
class TextLine:
    """A line of text composed of styled spans."""
    bbox: tuple[float, float, float, float]
    spans: list[TextSpan] = field(default_factory=list)
    dir: tuple[float, float] = (1.0, 0.0)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def is_khmer(self) -> bool:
        return any(s.is_khmer for s in self.spans)


@dataclass
class TextBlock:
    """A block of text lines (e.g. paragraph or text column segment)."""
    bbox: tuple[float, float, float, float]
    lines: list[TextLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class ExtractedImage:
    """An image extracted from a PDF page with its display bbox."""
    bbox: tuple[float, float, float, float]  # display coords on page
    data: bytes
    ext: str  # 'png', 'jpeg', etc.
    width: int  # pixel width
    height: int  # pixel height
    xref: int = 0


@dataclass
class VectorDrawing:
    """Vector path, line, or rectangle drawn on a PDF page."""
    bbox: tuple[float, float, float, float]
    drawing_type: str  # 'rect', 'line', 'curve', 'path'
    stroke_color: str | None = None  # '#RRGGBB'
    fill_color: str | None = None  # '#RRGGBB'
    stroke_width: float = 1.0
    dashes: str | None = None
    opacity: float = 1.0
    items: list[Any] = field(default_factory=list)


@dataclass
class ExtractedPage:
    """All extracted content on a single page with precise positions."""
    page_number: int  # 1-indexed
    width: float
    height: float
    rotation: int
    text_blocks: list[TextBlock] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    drawings: list[VectorDrawing] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.text_blocks if b.text.strip())


def extract_page_content(page: fitz.Page, page_number: int) -> ExtractedPage:
    """Extract all text, images, and vector drawings with exact positions from a page."""
    rect = page.rect
    width, height = float(rect.width), float(rect.height)
    rotation = int(page.rotation)

    # 1. Extract text with dict
    text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    raw_blocks = text_dict.get("blocks", [])
    text_blocks: list[TextBlock] = []

    for b in raw_blocks:
        if b.get("type") != 0:  # 0 is text block, 1 is image block
            continue
        lines: list[TextLine] = []
        for l in b.get("lines", []):
            spans: list[TextSpan] = []
            for s in l.get("spans", []):
                txt = s.get("text", "")
                if not txt:
                    continue
                flags = int(s.get("flags", 0))
                font_name = s.get("font", "")
                font_lower = font_name.lower()
                is_bold = bool(flags & 16) or ("bold" in font_lower)
                is_italic = bool(flags & 2) or ("italic" in font_lower) or ("oblique" in font_lower)
                color_hex = srgb_to_hex(int(s.get("color", 0)))
                size = float(s.get("size", 11.0))
                bbox = tuple(float(x) for x in s.get("bbox", (0, 0, 0, 0)))
                origin = tuple(float(x) for x in s.get("origin", (bbox[0], bbox[1])))
                is_khmer = bool(KHMER_RE.search(txt))

                spans.append(
                    TextSpan(
                        text=txt,
                        bbox=bbox,  # type: ignore[arg-type]
                        font=font_name,
                        size=size,
                        color=color_hex,
                        flags=flags,
                        is_bold=is_bold,
                        is_italic=is_italic,
                        origin=origin,  # type: ignore[arg-type]
                        is_khmer=is_khmer,
                    )
                )
            if spans:
                line_bbox = tuple(float(x) for x in l.get("bbox", (0, 0, 0, 0)))
                line_dir = tuple(float(x) for x in l.get("dir", (1.0, 0.0)))
                lines.append(TextLine(bbox=line_bbox, spans=spans, dir=line_dir))  # type: ignore[arg-type]

        if lines:
            b_bbox = tuple(float(x) for x in b.get("bbox", (0, 0, 0, 0)))
            text_blocks.append(TextBlock(bbox=b_bbox, lines=lines))  # type: ignore[arg-type]

    # 2. Extract images with exact placed rects
    extracted_images: list[ExtractedImage] = []
    image_list = page.get_images(full=True)
    seen_img_xrefs = set()

    for img_item in image_list:
        xref = img_item[0]
        try:
            base_image = page.parent.extract_image(xref)
            if not base_image:
                continue
            img_data = base_image["image"]
            img_ext = base_image["ext"]
            img_w = base_image["width"]
            img_h = base_image["height"]

            # Obtain placed bboxes on this page
            rects = page.get_image_rects(xref)
            if not rects:
                # Fallback: full page or zero bbox
                rects = [fitz.Rect(0, 0, width, height)]

            for r in rects:
                extracted_images.append(
                    ExtractedImage(
                        bbox=(float(r.x0), float(r.y0), float(r.x1), float(r.y1)),
                        data=img_data,
                        ext=img_ext,
                        width=img_w,
                        height=img_h,
                        xref=xref,
                    )
                )
        except Exception:
            logger.warning("Failed extracting image xref=%s on page %s", xref, page_number)

    # 3. Extract vector drawings
    extracted_drawings: list[VectorDrawing] = []
    raw_drawings = page.get_drawings()

    for d in raw_drawings:
        r = d.get("rect", fitz.Rect(0, 0, 0, 0))
        bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
        items = d.get("items", [])

        # Determine drawing type
        dtype = "path"
        if len(items) == 1:
            cmd = items[0][0]
            if cmd == "re":
                dtype = "rect"
            elif cmd == "l":
                dtype = "line"
            elif cmd == "c":
                dtype = "curve"

        stroke_color = rgb_tuple_to_hex(d.get("color"))
        fill_color = rgb_tuple_to_hex(d.get("fill"))
        raw_width = d.get("width")
        stroke_width = float(raw_width) if raw_width is not None else 1.0
        dashes = str(d.get("dashes", "")) if d.get("dashes") else None
        raw_opacity = d.get("opacity")
        opacity = float(raw_opacity) if raw_opacity is not None else 1.0

        extracted_drawings.append(
            VectorDrawing(
                bbox=bbox,
                drawing_type=dtype,
                stroke_color=stroke_color,
                fill_color=fill_color,
                stroke_width=stroke_width,
                dashes=dashes,
                opacity=opacity,
                items=items,
            )
        )

    return ExtractedPage(
        page_number=page_number,
        width=width,
        height=height,
        rotation=rotation,
        text_blocks=text_blocks,
        images=extracted_images,
        drawings=extracted_drawings,
    )


def extract_pdf_document(pdf_path: str | Path) -> list[ExtractedPage]:
    """Extract content with exact positions from all pages of a PDF."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages: list[ExtractedPage] = []
    for i in range(len(doc)):
        ep = extract_page_content(doc[i], i + 1)
        pages.append(ep)
    doc.close()
    return pages
