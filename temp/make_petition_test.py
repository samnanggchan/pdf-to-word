"""
Scratch script: Test conversion on the user's exact administrative petition layout.
"""

from pathlib import Path
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.converter import convert_pdf

# Register Khmer fonts
font_path = "/System/Library/Fonts/Supplemental/Khmer Sangam MN.ttf"
if Path(font_path).exists():
    pdfmetrics.registerFont(TTFont("KhmerBody", font_path))
    pdfmetrics.registerFont(TTFont("KhmerMuol", font_path))
else:
    pdfmetrics.registerFont(TTFont("KhmerBody", "Helvetica"))
    pdfmetrics.registerFont(TTFont("KhmerMuol", "Helvetica-Bold"))

out_pdf = Path("temp/petition_test.pdf")
out_pdf.parent.mkdir(parents=True, exist_ok=True)

c = canvas.Canvas(str(out_pdf), pagesize=A4)
width, height = A4

# 1. Header (Centered Motto)
c.setFont("KhmerMuol", 14)
c.drawCentredString(width / 2.0, height - 35 * mm, "ព្រះរាជាណាចក្រកម្ពុជា")
c.drawCentredString(width / 2.0, height - 42 * mm, "ជាតិ សាសនា ព្រះមហាក្សត្រ")

# Decorative line
c.setLineWidth(1)
c.line(width / 2.0 - 25 * mm, height - 46 * mm, width / 2.0 + 25 * mm, height - 46 * mm)

# 2. Blue Reference Number (Top right)
c.setFont("KhmerBody", 11)
c.setFillColorRGB(0.1, 0.2, 0.8)  # Blue
c.drawRightString(width - 25 * mm, height - 52 * mm, "លេខ: ៥ . ខ. ស . ស រាជធានីភ្នំពេញ")

# Reset color
c.setFillColorRGB(0, 0, 0)

# 3. Document Title
c.setFont("KhmerMuol", 13)
c.drawCentredString(width / 2.0, height - 62 * mm, "ពាក្យសុំចុះបញ្ជីបំពេញបន្ថែម (ចេញ/ប្ដូរប័ណ្ណថ្មី)")

# 4. Applicant Info
c.setFont("KhmerBody", 11)
y = height - 74 * mm
c.drawString(30 * mm, y, "ខ្ញុំបាទឈ្មោះ: លី ហេង ភេទ ប្រុស អាយុ ៥៧ ឆ្នាំ សញ្ជាតិ ខ្មែរ កាន់អត្តសញ្ញាណប័ណ្ណសញ្ជាតិខ្មែរលេខ")
y -= 6 * mm
c.drawString(25 * mm, y, "១៧០០៤០៧៨៩ (០២) ចុះថ្ងៃទី២៨ ខែតុលា ឆ្នាំ២០២៤ និងប្រពន្ធឈ្មោះ: គាន់ គីមហៀង ភេទ ស្រី អាយុ ៥៣ ឆ្នាំ")
y -= 6 * mm
c.drawString(25 * mm, y, "សញ្ជាតិ ខ្មែរ កាន់អត្តសញ្ញាណប័ណ្ណសញ្ជាតិខ្មែរលេខ ១៧០០៤០៥៥៨ (០២) ចុះថ្ងៃទី២៨ ខែតុលា ឆ្នាំ២០២៤ មាន")
y -= 6 * mm
c.drawString(25 * mm, y, "អាសយដ្ឋានបច្ចុប្បន្នស្ថិតនៅផ្ទះលេខ១៦៧ ក្រុម០៨ ភូមិព្រែកព្នៅ សង្កាត់ព្រែកព្នៅ ក្រុងព្រែកព្នៅ ខេត្តព្រែកព្នៅ។")

# 5. Salutation
y -= 10 * mm
c.setFont("KhmerMuol", 11)
c.drawCentredString(width / 2.0, y, "សូមគោរពជូន")
y -= 6 * mm
c.drawCentredString(width / 2.0, y, "ឯកឧត្តមអភិបាល នៃគណៈអភិបាលរាជធានីភ្នំពេញ")

# 6. Subject & Reference
y -= 10 * mm
c.setFont("KhmerMuol", 10.5)
c.drawString(25 * mm, y, "កម្មវត្ថុ: -")
c.setFont("KhmerBody", 10.5)
c.drawString(42 * mm, y, "សំណើសុំចុះបញ្ជីបំពេញបន្ថែម (ចេញ/ប្ដូរប័ណ្ណថ្មី) ដីដែលមានប័ណ្ណសំគាល់សិទ្ធិកាន់កាប់អចលនវត្ថុលេខ:")
y -= 5.5 * mm
c.drawString(42 * mm, y, "ភព ២៣៦៥៣ (k_ ០៧៨៩) ចុះថ្ងៃទី០៣ ខែវិច្ឆិកា ឆ្នាំ២០១៤ មានទីតាំងស្ថិតនៅភូមិ៤ សង្កាត់ច្រាំងចំរេះទី១")
y -= 5.5 * mm
c.drawString(42 * mm, y, "ខណ្ឌឫស្សីកែវ រាជធានីភ្នំពេញ ។")

y -= 8 * mm
c.setFont("KhmerMuol", 10.5)
c.drawString(25 * mm, y, "យោង: -")
c.setFont("KhmerBody", 10.5)
c.drawString(42 * mm, y, "ប័ណ្ណសំគាល់សិទ្ធិកាន់កាប់អចលនវត្ថុលេខ: ភព ២៣៦៥៣ (k_ ០៧៨៩) ចុះថ្ងៃទី០៣ ខែវិច្ឆិកា ឆ្នាំ២០១៤។")

# 7. Body Text
y -= 10 * mm
c.drawString(35 * mm, y, "សេចក្តីដូចមានចែងក្នុងកម្មវត្ថុ និងយោងខាងលើ យើងខ្ញុំសូមគោរពជម្រាបជូន ឯកឧត្តមអភិបាល មេត្តាជ្រាបថា:")
y -= 5.5 * mm
c.drawString(25 * mm, y, "ខ្ញុំបាទមានដី ០១ កន្លែង មានប័ណ្ណសំគាល់សិទ្ធិកាន់កាប់អចលនវត្ថុលេខ ភព ២៣៦៥៣ (k_ ០៧៨៩) ចុះថ្ងៃទី០៣ ខែវិច្ឆិកា")
y -= 5.5 * mm
c.drawString(25 * mm, y, "ឆ្នាំ២០១៤ មានទីតាំងស្ថិតនៅភូមិ៤ សង្កាត់ច្រាំងចំរេះទី១ ខណ្ឌឫស្សីកែវ រាជធានីភ្នំពេញ។ មានទំហំដី ៤៩ ម៉ែត្រការ៉េ កន្លងមក")
y -= 5.5 * mm
c.drawString(25 * mm, y, "យើងខ្ញុំបានខកខានពុំបានចូលរួមចុះបញ្ជីដីធ្លីមានលក្ខណៈជាប្រព័ន្ធ ហេតុដូច្នេះយើងខ្ញុំស្នើសុំចុះបញ្ជីបំពេញបន្ថែម ចេញ/")
y -= 5.5 * mm
c.drawString(25 * mm, y, "ប្ដូរប័ណ្ណថ្មី យកមកប្រើប្រាស់ស្របតាមច្បាប់។")

y -= 8 * mm
c.drawString(35 * mm, y, "អាស្រ័យហេតុនេះ សូម ឯកឧត្តមអភិបាល មេត្តាពិនិត្យ និងអនុញ្ញាតដោយក្តីអនុគ្រោះ ។")
y -= 5.5 * mm
c.drawString(35 * mm, y, "សូម ឯកឧត្តមអភិបាល មេត្តាទទួលនូវការគោរពដ៏ខ្ពង់ខ្ពស់អំពីយើងខ្ញុំ ។")

# 8. Date and Dual Thumbprint Signature block
y -= 14 * mm
c.drawString(width - 110 * mm, y, "ថ្ងៃ               ខែ               ឆ្នាំ មមី អដ្ឋស័ក ព.ស.២៥៧០")
y -= 6 * mm
c.drawString(width - 95 * mm, y, "រាជធានីភ្នំពេញ ថ្ងៃទី          ខែ          ឆ្នាំ២០២៦")
y -= 6 * mm
c.drawString(width - 70 * mm, y, "ស្នាមមេដៃស្តាំ")

y -= 22 * mm
c.setFont("KhmerMuol", 11)
c.drawString(55 * mm, y, "លី ហេង")
c.drawString(width - 75 * mm, y, "គាន់ គីមហៀង")

c.showPage()
c.save()
print("Generated petition_test.pdf successfully.")

