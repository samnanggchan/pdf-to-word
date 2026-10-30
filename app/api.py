"""
FastAPI REST API & Interactive Document Studio for Khmer PDF to Word Converter.
Provides:
  • 100% Free, zero-fee self-hosted web app with live interactive document preview
  • Left thumbnail page sidebar & realistic A4 paper canvas viewer (like Zendocs / Smallpdf)
  • Immediate .docx download with RFC 5987 Khmer Unicode filename preservation
  • REST API endpoints: /health, /convert, /download/{job_id}, /preview/{job_id}/page/{page_num}
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import fitz  # PyMuPDF
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.config import MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB, TEMP_DIR
from app.converter import convert_pdf

logger = logging.getLogger(__name__)


def make_content_disposition_header(filename: str) -> str:
    """
    Format Content-Disposition header conforming to RFC 5987 / RFC 6266.
    Ensures HTTP header value contains only Latin-1 compatible characters
    while preserving the full Unicode filename in filename*=UTF-8''...
    """
    quoted = quote(filename)
    if quoted == filename:
        return f'attachment; filename="{filename}"'
    safe_ascii = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{quoted}'


app = FastAPI(
    title="Khmer PDF → Word Converter Studio",
    description="High-fidelity PDF to DOCX converter with live interactive preview and Khmer Unicode preservation.",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.1.0"}


@app.get("/", response_class=HTMLResponse)
def index_page():
    """Interactive Document Editor & Studio UI (Free, no fee, like Zendocs/Smallpdf)."""
    return """<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="utf-8">
    <title>Khmer PDF → Word Studio (Free Preview & Download)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Battambang:wght@400;700&family=Inter:wght@400;500;600;700&family=Moul&family=Outfit:wght@500;600;700;800&family=Siemreap&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-canvas: #f1f5f9;
            --sidebar-bg: #ffffff;
            --header-bg: #0f172a;
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --accent: #4f46e5;
            --border: #e2e8f0;
            --text-dark: #0f172a;
            --text-muted: #64748b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', 'Battambang', sans-serif;
            background: var(--bg-canvas);
            color: var(--text-dark);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Top Navbar */
        .navbar {
            height: 60px;
            background: var(--header-bg);
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 1.25rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            flex-shrink: 0;
            z-index: 100;
        }
        .nav-left { display: flex; align-items: center; gap: 1rem; }
        .logo-badge {
            display: flex; align-items: center; gap: 0.5rem;
            font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.15rem;
            color: #ffffff; text-decoration: none;
        }
        .logo-icon {
            width: 32px; height: 32px; background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            border-radius: 8px; display: flex; align-items: center; justify-content: center;
            font-size: 1rem; box-shadow: 0 2px 8px rgba(37,99,235,0.4);
        }
        .free-pill {
            background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #6ee7b7;
            padding: 0.2rem 0.55rem; border-radius: 9999px; font-size: 0.72rem; font-weight: 600;
        }

        .nav-center { display: flex; align-items: center; gap: 0.5rem; }
        .file-title-pill {
            background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15);
            padding: 0.35rem 0.9rem; border-radius: 8px; font-size: 0.82rem; font-weight: 500;
            color: #e2e8f0; max-width: 380px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        .nav-right { display: flex; align-items: center; gap: 0.75rem; }
        .btn-download {
            background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; border: none;
            padding: 0.55rem 1.25rem; font-size: 0.88rem; font-weight: 600; border-radius: 8px;
            display: inline-flex; align-items: center; gap: 0.4rem; cursor: pointer;
            box-shadow: 0 4px 12px rgba(37,99,235,0.3); transition: all 0.15s ease; text-decoration: none;
        }
        .btn-download:hover { background: #1e40af; transform: translateY(-1px); }
        .btn-convert-another {
            background: rgba(255,255,255,0.08); color: #cbd5e1; border: 1px solid rgba(255,255,255,0.2);
            padding: 0.5rem 0.9rem; font-size: 0.82rem; font-weight: 500; border-radius: 8px;
            cursor: pointer; transition: background 0.15s;
        }
        .btn-convert-another:hover { background: rgba(255,255,255,0.15); color: white; }

        /* Main Workspace Container */
        .workspace {
            flex: 1;
            display: flex;
            overflow: hidden;
            position: relative;
        }

        /* Initial Upload Screen */
        .upload-view {
            flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; padding: 2rem; background: #0f172a; color: white;
            text-align: center;
        }
        .upload-card {
            max-width: 580px; width: 100%; background: #1e293b; border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 2.5rem 2rem; box-shadow: 0 20px 45px rgba(0,0,0,0.5);
        }
        .app-headline { font-size: 1.8rem; font-weight: 800; color: #ffffff; margin-bottom: 0.4rem; }
        .app-sub { font-size: 0.95rem; color: #94a3b8; margin-bottom: 1.75rem; line-height: 1.5; font-family: 'Battambang', sans-serif; }
        .dropzone {
            border: 2px dashed #475569; border-radius: 12px; padding: 2.5rem 1.5rem;
            cursor: pointer; transition: all 0.2s; background: rgba(255,255,255,0.02); margin-bottom: 1.5rem;
        }
        .dropzone:hover, .dropzone.dragover { border-color: #38bdf8; background: rgba(56,189,248,0.05); }
        .drop-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
        .drop-text { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.25rem; }
        .drop-hint { font-size: 0.8rem; color: #64748b; }
        .mode-row { display: flex; justify-content: center; gap: 1rem; margin-bottom: 1.5rem; }
        .mode-option {
            display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; color: #cbd5e1;
            cursor: pointer; background: rgba(255,255,255,0.05); padding: 0.4rem 0.8rem; border-radius: 6px;
        }
        .mode-option input { cursor: pointer; }

        /* Progress / Converting Overlay */
        .progress-box { display: none; margin-top: 1.5rem; }
        .spinner {
            width: 38px; height: 38px; border: 3px solid rgba(255,255,255,0.1);
            border-top-color: #38bdf8; border-radius: 50%; animation: spin 0.8s linear infinite;
            margin: 0 auto 1rem;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .progress-status { font-size: 0.95rem; font-weight: 600; color: #38bdf8; }
        .progress-step { font-size: 0.8rem; color: #94a3b8; margin-top: 0.35rem; }

        /* Preview Studio Workspace (like Zendocs) */
        .studio-view {
            display: none; width: 100%; height: 100%;
        }

        /* Left Thumbnails Sidebar */
        .thumbnail-sidebar {
            width: 170px; background: var(--sidebar-bg); border-right: 1px solid var(--border);
            display: flex; flex-direction: column; overflow-y: auto; padding: 1rem 0.75rem;
            gap: 1rem; flex-shrink: 0; box-shadow: 2px 0 6px rgba(0,0,0,0.02);
        }
        .sidebar-title { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; margin-bottom: 0.25rem; padding-left: 0.25rem; }
        .thumb-card {
            cursor: pointer; border: 2px solid transparent; border-radius: 8px; overflow: hidden;
            background: #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.08); transition: all 0.15s;
            text-align: center; padding: 4px;
        }
        .thumb-card:hover { border-color: #93c5fd; transform: translateY(-1px); }
        .thumb-card.active { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.25); }
        .thumb-img { width: 100%; display: block; border-radius: 4px; border: 1px solid #e2e8f0; }
        .thumb-label { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); margin-top: 4px; }

        /* Center Canvas */
        .canvas-area {
            flex: 1; overflow: auto; display: flex; flex-direction: column;
            align-items: center; padding: 2.5rem 1.5rem 5rem; position: relative;
        }

        /* Virtual A4 Paper Sheet */
        .paper-sheet {
            background: #ffffff;
            width: 100%;
            max-width: 820px;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15), 0 2px 8px rgba(0, 0, 0, 0.08);
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid #cbd5e1;
            transition: transform 0.2s ease;
        }
        .page-render-img {
            width: 100%; height: auto; display: block;
        }

        /* Floating Toolbar */
        .floating-bar {
            position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
            background: #1e293b; color: white; padding: 0.45rem 1rem; border-radius: 9999px;
            display: flex; align-items: center; gap: 1rem; box-shadow: 0 10px 30px rgba(0,0,0,0.35);
            border: 1px solid rgba(255,255,255,0.15); z-index: 50; font-size: 0.85rem;
        }
        .zoom-btn {
            background: none; border: none; color: #94a3b8; font-size: 1.1rem; cursor: pointer;
            width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
            border-radius: 50%; transition: background 0.15s;
        }
        .zoom-btn:hover { background: rgba(255,255,255,0.15); color: white; }
    </style>
</head>
<body>

    <!-- Top Navbar -->
    <header class="navbar">
        <div class="nav-left">
            <a href="/" class="logo-badge">
                <div class="logo-icon">📄</div>
                <span>KhmerDocs</span>
            </a>
            <span class="free-pill">✨ 100% Free · No Fee</span>
        </div>

        <div class="nav-center" id="navCenter" style="display: none;">
            <div class="file-title-pill" id="fileTitlePill">document.docx</div>
        </div>

        <div class="nav-right" id="navRight" style="display: none;">
            <button class="btn-convert-another" onclick="location.reload()">Convert Another</button>
            <a id="btnDownloadWord" href="#" class="btn-download">
                <span>⬇️ Download Word (.docx)</span>
            </a>
        </div>
    </header>

    <!-- Main Workspace -->
    <div class="workspace">

        <!-- 1. Initial Upload View -->
        <div class="upload-view" id="uploadView">
            <div class="upload-card">
                <h1 class="app-headline">PDF → Word Studio</h1>
                <p class="app-sub">បម្លែងឯកសារ PDF ទៅជា Word (.docx) ដោយរក្សាពុម្ពអក្សរខ្មែរគ្រប់ប្រភេទ និងទម្រង់ដើម ១០០% ឥតគិតថ្លៃ</p>

                <div class="mode-row">
                    <label class="mode-option">
                        <input type="radio" name="modeSelect" value="auto" checked>
                        <span>Auto Hybrid</span>
                    </label>
                    <label class="mode-option">
                        <input type="radio" name="modeSelect" value="editable">
                        <span>Mode A (Editable)</span>
                    </label>
                    <label class="mode-option">
                        <input type="radio" name="modeSelect" value="exact">
                        <span>Mode B (Exact Layout)</span>
                    </label>
                </div>

                <div class="dropzone" id="dropzone">
                    <input type="file" id="fileInput" accept=".pdf" style="display:none;">
                    <div class="drop-icon">📁</div>
                    <div class="drop-text">Drop your PDF here, or click to browse</div>
                    <div class="drop-hint">Preserves Khmer OS Muol Light, Battambang, and complex layouts</div>
                </div>

                <div class="progress-box" id="progressBox">
                    <div class="spinner"></div>
                    <div class="progress-status" id="progressStatus">Converting PDF to Word...</div>
                    <div class="progress-step" id="progressStep">Resolving fonts and preserving complex script OpenXML</div>
                </div>
            </div>
        </div>

        <!-- 2. Preview Studio View (like Zendocs) -->
        <div class="studio-view" id="studioView">
            <!-- Left Thumbnails Sidebar -->
            <aside class="thumbnail-sidebar" id="thumbnailSidebar">
                <div class="sidebar-title">Pages</div>
                <!-- Thumbnails dynamically rendered -->
            </aside>

            <!-- Center Virtual Paper Canvas -->
            <main class="canvas-area" id="canvasArea">
                <div class="paper-sheet" id="paperSheet">
                    <img id="mainPageImg" class="page-render-img" src="" alt="Document Preview">
                </div>
            </main>

            <!-- Floating Zoom & Page Controls -->
            <div class="floating-bar">
                <button class="zoom-btn" onclick="adjustZoom(-10)">−</button>
                <span id="zoomLevelText">100%</span>
                <button class="zoom-btn" onclick="adjustZoom(10)">+</button>
                <span style="color:#64748b;">|</span>
                <span id="pageIndicatorText">Page 1 of 1</span>
            </div>
        </div>

    </div>

    <script>
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('fileInput');
        const uploadView = document.getElementById('uploadView');
        const progressBox = document.getElementById('progressBox');
        const progressStatus = document.getElementById('progressStatus');
        const progressStep = document.getElementById('progressStep');
        const studioView = document.getElementById('studioView');
        const navCenter = document.getElementById('navCenter');
        const navRight = document.getElementById('navRight');
        const fileTitlePill = document.getElementById('fileTitlePill');
        const btnDownloadWord = document.getElementById('btnDownloadWord');
        const mainPageImg = document.getElementById('mainPageImg');
        const thumbnailSidebar = document.getElementById('thumbnailSidebar');
        const pageIndicatorText = document.getElementById('pageIndicatorText');
        const paperSheet = document.getElementById('paperSheet');
        const zoomLevelText = document.getElementById('zoomLevelText');

        let currentJob = null;
        let activePage = 1;
        let currentZoom = 100;

        dropzone.addEventListener('click', () => fileInput.click());
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
        });

        async function handleFile(file) {
            if (!file.name.toLowerCase().endsWith('.pdf')) {
                alert('Please upload a PDF document.');
                return;
            }

            dropzone.style.display = 'none';
            progressBox.style.display = 'block';

            const mode = document.querySelector('input[name="modeSelect"]:checked').value;
            const formData = new FormData();
            formData.append('file', file);

            try {
                progressStatus.innerText = 'Analyzing PDF geometry and fonts...';
                progressStep.innerText = 'Extracting vectors, tables, and Khmer Unicode text';

                const response = await fetch(`/convert?format=json&mode=${mode}`, {
                    method: 'POST',
                    headers: { 'Accept': 'application/json' },
                    body: formData
                });

                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Conversion failed');
                }

                const data = await response.json();
                currentJob = data;
                displayStudioView(data);
            } catch (err) {
                alert('Conversion failed: ' + err.message);
                location.reload();
            }
        }

        function displayStudioView(job) {
            uploadView.style.display = 'none';
            studioView.style.display = 'flex';
            navCenter.style.display = 'flex';
            navRight.style.display = 'flex';

            fileTitlePill.innerText = job.filename;
            fileTitlePill.title = job.filename;
            btnDownloadWord.href = job.download_url;

            // Build Thumbnails
            thumbnailSidebar.innerHTML = '<div class="sidebar-title">Pages (' + job.total_pages + ')</div>';
            for (let i = 1; i <= job.total_pages; i++) {
                const thumb = document.createElement('div');
                thumb.className = 'thumb-card' + (i === 1 ? ' active' : '');
                thumb.id = 'thumb-' + i;
                thumb.onclick = () => selectPage(i);

                const img = document.createElement('img');
                img.className = 'thumb-img';
                img.src = `/preview/${job.job_id}/page/${i}`;
                img.alt = 'Page ' + i;

                const lbl = document.createElement('div');
                lbl.className = 'thumb-label';
                lbl.innerText = 'Page ' + i;

                thumb.appendChild(img);
                thumb.appendChild(lbl);
                thumbnailSidebar.appendChild(thumb);
            }

            selectPage(1);
        }

        function selectPage(pageNum) {
            activePage = pageNum;
            mainPageImg.src = `/preview/${currentJob.job_id}/page/${pageNum}`;
            pageIndicatorText.innerText = `Page ${pageNum} of ${currentJob.total_pages}`;

            // Update thumb active state
            document.querySelectorAll('.thumb-card').forEach((el) => el.classList.remove('active'));
            const activeThumb = document.getElementById('thumb-' + pageNum);
            if (activeThumb) activeThumb.classList.add('active');
        }

        function adjustZoom(delta) {
            currentZoom = Math.min(180, Math.max(50, currentZoom + delta));
            paperSheet.style.maxWidth = (820 * (currentZoom / 100)) + 'px';
            zoomLevelText.innerText = currentZoom + '%';
        }
    </script>
</body>
</html>
"""


@app.get("/preview/{job_id}/page/{page_num}")
def preview_page(job_id: str, page_num: int):
    """
    Render and serve high-resolution page image for live in-browser preview.
    Caches page render to disk for instant thumbnail & canvas viewing.
    """
    safe_job_id = Path(job_id).name
    job_dir = TEMP_DIR / safe_job_id
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Job directory not found.")

    cache_img = job_dir / f"render_page_{page_num}.png"
    if cache_img.exists():
        return FileResponse(path=str(cache_img), media_type="image/png")

    # Locate source PDF
    pdf_files = list(job_dir.glob("*.pdf"))
    if not pdf_files:
        raise HTTPException(status_code=404, detail="Source PDF not found.")
    src_pdf = pdf_files[0]

    try:
        doc = fitz.open(str(src_pdf))
        if page_num < 1 or page_num > len(doc):
            doc.close()
            raise HTTPException(status_code=404, detail="Page number out of range.")
        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        cache_img.write_bytes(img_bytes)
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        logger.exception("Could not render page preview: %s", e)
        raise HTTPException(status_code=500, detail="Page rendering error.")


@app.post("/convert")
async def convert_endpoint(
    request: Request,
    file: UploadFile = File(...),
    format: Optional[str] = Query(None),
    mode: str = Query("auto"),
):
    """
    Convert an uploaded PDF file to DOCX.
    Supports binary DOCX attachment download or JSON preview metadata.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename.")

    clean_filename = Path(file.filename).name
    if not clean_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF document.")

    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
        )

    job_id = str(uuid.uuid4())
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    src_path = job_dir / clean_filename
    original_stem = Path(clean_filename).stem
    docx_filename = f"{original_stem}.docx"
    dst_path = job_dir / docx_filename

    src_path.write_bytes(content)

    try:
        conv_result = convert_pdf(src_path, dst_path, mode=mode)
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        logger.exception("Conversion failed for %s", clean_filename)
        raise HTTPException(status_code=500, detail=f"Conversion error: {e}")

    accept_header = request.headers.get("accept", "")
    wants_json = (format and format.lower() == "json") or ("application/json" in accept_header and "text/html" not in accept_header)

    if wants_json:
        pages_data = [
            {
                "page_number": p.page_number,
                "text": p.text,
                "width": p.width,
                "height": p.height,
                "used_ocr": p.used_ocr,
                "has_text_layer": p.has_text_layer,
            }
            for p in conv_result.pages
        ]

        return JSONResponse(
            content={
                "success": True,
                "filename": docx_filename,
                "job_id": job_id,
                "download_url": f"/download/{job_id}?filename={docx_filename}",
                "total_pages": conv_result.total_pages,
                "pages": pages_data,
                "word_count": conv_result.word_count,
                "char_count": conv_result.char_count,
                "used_ocr": conv_result.used_ocr,
                "applied_fonts": conv_result.applied_fonts,
            }
        )

    # Direct DOCX download with RFC 5987 Unicode header support
    disposition_header = make_content_disposition_header(docx_filename)
    return FileResponse(
        path=str(dst_path),
        filename=docx_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition_header},
    )


@app.get("/download/{job_id}")
def download_job_file(job_id: str, filename: Optional[str] = Query(None)):
    """Download converted file by job_id with path traversal protection."""
    safe_job_id = Path(job_id).name
    job_dir = TEMP_DIR / safe_job_id

    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Conversion job not found or expired.")

    if filename:
        safe_filename = Path(filename).name
        target_file = job_dir / safe_filename
    else:
        docx_files = list(job_dir.glob("*.docx"))
        if not docx_files:
            raise HTTPException(status_code=404, detail="File not found in job directory.")
        target_file = docx_files[0]

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="Requested file not found.")

    disposition_header = make_content_disposition_header(target_file.name)
    return FileResponse(
        path=str(target_file),
        filename=target_file.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition_header},
    )
