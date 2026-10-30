# Khmer PDF → Word Converter (High-Fidelity Unicode & Layout)

A high-fidelity Python conversion system (FastAPI REST API + Streamlit Web Dashboard) that converts PDF documents to Word (`.docx`) with **full Khmer Unicode support**, **complex script font preservation (Muol Light, Battambang, Siemreap, etc.)**, **two layout preservation modes**, and an **automated visual verification loop (SSIM)**.

---

## 🌟 Key Features

1. **Comprehensive PDF Analysis (Step 1)**: Inspects page geometry, rotation, content margins, tables, columns, text layer usability, and detects legacy non-Unicode fonts (Limon, ABC).
2. **Exact Positional Extraction (Step 2)**: Extracts text blocks, lines, and styled spans (bbox, font, size, color, bold/italic, origin), embedded images with display bboxes, and vector drawings (rectangles, lines, fills, strokes).
3. **Dynamic Font Resolution (Step 3)**:
   - Strips subset prefixes (`ABCDEF+Name` → `Name`).
   - 4-Tier Resolution Hierarchy: System font matching → Normalized Khmer font map → Embedded font extraction (`.odttf` obfuscated font embedding in DOCX) → Fallback chain (`Noto Sans Khmer` → `Khmer UI` → `Leelawadee UI`).
   - OpenXML complex-script tagging: `w:rFonts` (ascii, hAnsi, cs, eastAsia), `w:szCs`, `w:bCs`, `w:iCs`, and `w:lang w:bidi="km-KH"`.
   - Text Fitting: Measures width via `fontTools`/`PIL`; condenses `w:spacing` first, then scales font size by at most 8% if needed.
4. **Two Output Modes (Step 4)**:
   - **Mode A ("Editable")**: Uses `pdf2docx` for flowing text, tables, and lists, post-processed with exact Khmer font rules and PDF page geometry.
   - **Mode B ("Exact Layout")**: Places every text line as an absolutely positioned frame (`w:framePr`) anchored to the page origin with zero padding, placing images and vector borders at their exact coordinates.
   - **Auto Mode**: Intelligently selects Mode A or Mode B based on layout complexity.
5. **Khmer Text Correctness (Step 5)**:
   - NFC normalization.
   - Preserves single ZWSP (`U+200B`) between words, cleans stray invisible characters (`ZWNJ`, `ZWJ`, `\u2060`, BOM).
   - Protects orthographic clusters (never splits consonant + coeng + vowel across lines).
   - Legacy font conversion (Limon/ABC) with multi-character digraph support (`Ch`, `Df`, `Nn`).
   - 300 DPI in-memory Tesseract OCR fallback using PyMuPDF (no Poppler required).
6. **Visual Verification Loop (Step 6)**:
   - Renders original PDF and converted DOCX (via headless LibreOffice) to PNG at 150 DPI.
   - Computes Structural Similarity Index (SSIM) per page using `scikit-image`.
   - If SSIM < 0.92, automatically retries and optimizes with Mode B up to 3 times.

---

## 📁 Project Structure

```
pdf-to-word/
├── app/
│   ├── __init__.py
│   ├── config.py           # Environment-driven limits, fonts, and directories
│   ├── analyzer.py         # Step 1: Geometry, layers, margins, and font detection
│   ├── extractor.py        # Step 2: Exact coordinate extraction (text, images, vectors)
│   ├── font_resolver.py    # Step 3: Font resolution, embedding (.odttf), text fitting
│   ├── docx_modes.py       # Step 4: Mode A (Editable) & Mode B (Exact Layout)
│   ├── khmer_utils.py      # Step 5: Khmer NFC, ZWSP, cluster safety, Limon conversion, OCR
│   ├── verifier.py         # Step 6: Visual verification loop & SSIM quality assurance
│   ├── converter.py        # High-level orchestrator pipeline
│   ├── api.py              # FastAPI REST API & clean HTML upload interface
│   └── main.py             # Dual entrypoint: uvicorn (FastAPI) & Streamlit Dashboard
├── tests/
│   ├── conftest.py                  # Fixture generators (text, scanned, complex PDFs)
│   ├── test_api.py                  # FastAPI endpoint tests
│   ├── test_khmer_text_pdf.py       # Test 1: Khmer text PDF
│   ├── test_scanned_khmer_pdf.py    # Test 2: Scanned OCR PDF
│   ├── test_complex_khmer_pdf.py    # Test 3: Complex PDF (table, image, signature)
│   ├── test_khmer_utils.py          # Khmer Unicode and legacy utils tests
│   ├── test_step1_analyzer.py       # Step 1 unit tests
│   ├── test_step2_extractor.py      # Step 2 unit tests
│   ├── test_step3_font_resolver.py  # Step 3 unit tests
│   ├── test_step4_docx_modes.py     # Step 4 unit tests
│   ├── test_step5_khmer_correctness.py # Step 5 unit tests
│   └── test_step6_verifier.py       # Step 6 unit tests
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🚀 Quick Start

### 1. Local Setup

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the FastAPI server (includes HTML upload page):
uvicorn app.main:app --reload --port 8000
# Open http://localhost:8000 in your browser

# 4. Or launch the Streamlit Executive Dashboard:
streamlit run app/main.py --server.port 8501
# Open http://localhost:8501 in your browser
```

### 2. Docker Deployment (Recommended)

Docker provides the complete stack including `tesseract-ocr-khm`, `poppler-utils`, `libreoffice`, `fonts-khmeros`, and `fonts-noto-core`:

```bash
docker compose up --build
```

- **REST API & Upload Page**: `http://localhost:8000`
- **Interactive Docs**: `http://localhost:8000/docs`

---

## 🧪 Running Tests

The test suite covers every step in the pipeline:

```bash
# Run all tests
pytest tests/ -v

# Run unit tests by step
pytest tests/test_step1_analyzer.py -v
pytest tests/test_step2_extractor.py -v
pytest tests/test_step3_font_resolver.py -v
pytest tests/test_step4_docx_modes.py -v
pytest tests/test_step5_khmer_correctness.py -v
pytest tests/test_step6_verifier.py -v

# Run document integration tests
pytest tests/test_khmer_text_pdf.py tests/test_complex_khmer_pdf.py tests/test_scanned_khmer_pdf.py -v

# Run FastAPI endpoint tests
pytest tests/test_api.py -v
```

---

## 📡 REST API Endpoints

- `GET /health` — Service health check.
- `GET /` — Interactive HTML upload interface.
- `POST /convert?mode=auto|editable|exact` — Upload a PDF file:
  - Default: Streams converted `.docx` binary attachment.
  - With `?format=json` or `Accept: application/json`: Returns JSON preview metadata and download URL.
- `GET /download/{job_id}?filename=...` — Download converted `.docx` by job ID with path-traversal protection.

---

## 📜 License

MIT License.
