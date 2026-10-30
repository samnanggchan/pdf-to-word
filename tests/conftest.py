"""
Helper: generate test PDF fixtures programmatically using ReportLab.

Provides:
  - create_khmer_text_pdf()    - a PDF with a real Khmer text layer
  - create_scanned_khmer_pdf() - a PDF containing a rasterised image of
    Khmer text (simulates a scanned document that requires OCR)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


# Sample Khmer text
KHMER_SAMPLE = (
    "\u1780\u1798\u17d2\u1796\u17bb\u1787\u17b6\u1787\u17b6\u1794\u17d2\u179a\u1791\u17c1\u179f\u1798\u17bd\u1799\u1793\u17c5\u17a2\u17b6\u179f\u17ca\u17b8\u17a2\u17b6\u1782\u17d2\u1793\u17c1\u1799\u17cd\u17d4\n"
    "\u179a\u17b6\u1787\u1792\u17b6\u1793\u17b8\u1797\u17d2\u1793\u17c6\u1796\u17c1\u1789\u1787\u17b6\u1791\u17b8\u1780\u17d2\u179a\u17bb\u1784\u1792\u17c6\u1794\u17c6\u1795\u17bb\u178f\u17d4\n"
    "\u1794\u17d2\u179a\u1787\u17b6\u1787\u1793\u1780\u1798\u17d2\u1796\u17bb\u1787\u17b6\u1798\u17b6\u1793\u1794\u17d2\u179a\u1798\u17b6\u178e \u17e1\u17e7 \u179b\u17b6\u1793\u1793\u17b6\u1780\u17cb\u17d4\n"
)

KHMER_HEADING = "\u1796\u17d2\u179a\u17c7\u179a\u17b6\u1787\u17b6\u178e\u17b6\u1785\u1780\u17d2\u179a\u1780\u1798\u17d2\u1796\u17bb\u1787\u17b6"
KHMER_BODY = (
    "\u1780\u1798\u17d2\u1796\u17bb\u1787\u17b6\u1787\u17b6\u1794\u17d2\u179a\u1791\u17c1\u179f\u1798\u17bd\u1799\u1793\u17c5\u17a2\u17b6\u179f\u17ca\u17b8\u17a2\u17b6\u1782\u17d2\u1793\u17c1\u1799\u17cd "
    "\u178a\u17c2\u179b\u1798\u17b6\u1793\u1794\u17d2\u179a\u179c\u178f\u17d2\u178f\u17b7\u179f\u17b6\u179f\u17d2\u178f\u17d2\u179a\u179c\u17c2\u1784\u1786\u17d2\u1784\u17b6\u1799\u17d4 "
    "\u179a\u17b6\u1787\u1792\u17b6\u1793\u17b8\u1797\u17d2\u1793\u17c6\u1796\u17c1\u1789\u1787\u17b6\u1791\u17b8\u1780\u17d2\u179a\u17bb\u1784\u1792\u17c6\u1794\u17c6\u1795\u17bb\u178f\u1793\u17b7\u1784\u1787\u17b6\u1798\u1787\u17d2\u1788\u1798\u178e\u17d2\u178c\u179b\u179f\u17c1\u178a\u17d2\u178b\u1780\u17b7\u1785\u17d2\u1785\u179a\u1794\u179f\u17cb\u1794\u17d2\u179a\u1791\u17c1\u179f\u17d4"
)


def create_khmer_text_pdf(path: str | Path) -> Path:
    """
    Create a minimal PDF with an embedded Khmer Unicode text layer.

    ReportLab will embed the text as real glyphs (even if the font isn't
    installed - the text bytes are still present), making this suitable
    for testing the "text-layer present" path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    # Try to use a system Khmer font; fall back to Helvetica (the text
    # bytes are still Khmer Unicode - just won't render prettily).
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        # Try common system paths for Khmer fonts
        font_paths = [
            "/usr/share/fonts/truetype/khmeros/KhmerOSbattambang.ttf",
            "/usr/share/fonts/truetype/noto-khmer/NotoSansKhmer-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Khmer Sangam MN.ttf",
        ]
        registered = False
        for fp in font_paths:
            if Path(fp).exists():
                pdfmetrics.registerFont(TTFont("KhmerTest", fp))
                c.setFont("KhmerTest", 14)
                registered = True
                break
        if not registered:
            c.setFont("Helvetica", 14)
    except Exception:
        c.setFont("Helvetica", 14)

    y = height - 50 * mm
    for line in KHMER_SAMPLE.strip().splitlines():
        c.drawString(30 * mm, y, line)
        y -= 8 * mm

    c.showPage()
    c.save()
    return path


def create_scanned_khmer_pdf(path: str | Path) -> Path:
    """
    Create a PDF that contains only a rasterised image of Khmer text
    (no real text layer).  This simulates a scanned document.

    We render Khmer text onto a PIL image, then embed that image as
    the sole content of a one-page PDF.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create an image with Khmer text
    img_w, img_h = 2480, 3508  # A4 at 300 DPI
    img = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)

    # Try to find a Khmer font for Pillow
    font_paths = [
        "/usr/share/fonts/truetype/khmeros/KhmerOSbattambang.ttf",
        "/usr/share/fonts/truetype/noto-khmer/NotoSansKhmer-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Khmer Sangam MN.ttf",
    ]
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 42)
                break
            except Exception:
                pass
    if font is None:
        # Fallback: use default (Latin only, but the PDF structure is
        # what matters for the OCR-path test).
        font = ImageFont.load_default()

    y = 200
    for line in KHMER_SAMPLE.strip().splitlines():
        draw.text((150, y), line, fill="black", font=font)
        y += 80

    # Save image as temporary PNG, embed in PDF
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img_path = tmp.name
        img.save(img_path)

    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(img_path, 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()

    # Cleanup temp image
    Path(img_path).unlink(missing_ok=True)

    return path


def create_complex_khmer_pdf(path: str | Path) -> Path:
    """
    Create a complex PDF containing:
      • Khmer header / title text
      • An embedded image (e.g. official stamp / logo)
      • A structured vector table with rows and columns
      • A signature block at bottom right
    """
    import tempfile
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Create a stamp image
    stamp_img = Image.new("RGBA", (150, 150), (255, 255, 255, 0))
    stamp_draw = ImageDraw.Draw(stamp_img)
    stamp_draw.ellipse([10, 10, 140, 140], outline="red", width=3)
    stamp_draw.text((35, 65), "OFFICIAL", fill="red")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        stamp_path = tmp.name
        stamp_img.save(stamp_path)

    # Try registering Khmer font
    font_name = "Helvetica"
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        font_paths = [
            "/System/Library/Fonts/Supplemental/Khmer Sangam MN.ttf",
            "/usr/share/fonts/truetype/khmeros/KhmerOSbattambang.ttf",
            "/usr/share/fonts/truetype/noto-khmer/NotoSansKhmer-Regular.ttf",
        ]
        for fp in font_paths:
            if Path(fp).exists():
                try:
                    pdfmetrics.registerFont(TTFont("KhmerComplex", fp))
                    font_name = "KhmerComplex"
                    break
                except Exception:
                    pass
    except Exception:
        pass

    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    elements = []

    # Title
    title_style = ParagraphStyle(
        "KhmerTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=18,
        leading=22,
        alignment=1,  # Center
    )
    elements.append(Paragraph(KHMER_HEADING, title_style))
    elements.append(Spacer(1, 10*mm))

    # Body Paragraph
    body_style = ParagraphStyle(
        "KhmerBody",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=12,
        leading=16,
    )
    elements.append(Paragraph(KHMER_BODY, body_style))
    elements.append(Spacer(1, 10*mm))

    # Table with 3 columns and 4 rows
    table_data = [
        ["ល.រ", "បរិយាយទំនិញ", "តម្លៃ ($)"],
        ["១", "កុំព្យូទ័រយួរដៃ (Laptop)", "៨៥០.០០"],
        ["២", "ម៉ាស៊ីនបោះពុម្ព (Printer)", "២២០.០០"],
        ["៣", "ក្រដាស A4 (Paper Box)", "៣៥.០០"],
    ]
    t = Table(table_data, colWidths=[25*mm, 90*mm, 45*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15*mm))

    # Signature Block & Stamp Image
    sig_data = [
        ["", "រាជធានីភ្នំពេញ ថ្ងៃទី ៣០ ខែតុលា ឆ្នាំ ២០២៤"],
        ["", "ហត្ថលេខា និងត្រា (Signature & Stamp)"],
        [RLImage(stamp_path, width=30*mm, height=30*mm), ""],
        ["", "លោក ប្រធាននាយកដ្ឋាន"],
    ]
    sig_table = Table(sig_data, colWidths=[80*mm, 80*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (0, 2), (0, 2), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
    ]))
    elements.append(sig_table)

    doc.build(elements)

    Path(stamp_path).unlink(missing_ok=True)
    return path
