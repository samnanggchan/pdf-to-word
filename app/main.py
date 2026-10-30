"""
Main Entrypoint: Supports both FastAPI (uvicorn app.main:app) and Streamlit (streamlit run app/main.py).

Features:
  • FastAPI ASGI app exported as `app`
  • Rich interactive Streamlit UI when executed via `streamlit run app/main.py`
  • Preserves all Khmer fonts (Muol Light, Battambang, Siemreap, etc.) and original layout
"""

from __future__ import annotations

import html
import io
import sys
import tempfile
from pathlib import Path

# Export FastAPI app for uvicorn and pytest
from app.api import app

# Check if running under Streamlit runtime
try:
    from streamlit.runtime import exists as _streamlit_runtime_exists
    _IN_STREAMLIT = _streamlit_runtime_exists()
except Exception:
    _IN_STREAMLIT = False

if _IN_STREAMLIT or ("streamlit" in sys.argv[0]):
    import fitz  # PyMuPDF
    import streamlit as st
    from docx import Document
    from PIL import Image

    from app.converter import convert_pdf

    # ── Streamlit Page Configuration ──────────────────────────────────────
    st.set_page_config(
        page_title="PDF → Word (Khmer Fonts & Layout)",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Typography & Modern Styling ───────────────────────────────────────
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Battambang:wght@400;700&family=Inter:wght@400;500;600;700&family=Moul&family=Noto+Sans+Khmer:wght@400;600;700&family=Outfit:wght@500;600;700;800&family=Siemreap&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', 'Noto Sans Khmer', sans-serif;
        }
        .app-header {
            padding: 0.5rem 0 1.25rem;
            border-bottom: 1px solid rgba(100, 116, 139, 0.2);
            margin-bottom: 1.5rem;
        }
        .app-title {
            font-family: 'Outfit', 'Inter', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            color: #1e1b4b;
            background: linear-gradient(135deg, #1e1b4b 20%, #4338ca 70%, #1d4ed8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.35rem;
            line-height: 1.2;
        }
        .app-khmer-sub {
            font-family: 'Battambang', 'Noto Sans Khmer', sans-serif;
            font-size: 1.1rem;
            color: #4f46e5;
            font-weight: 700;
            margin-bottom: 0.75rem;
            line-height: 1.5;
        }
        .badge-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.65rem;
        }
        .badge-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.78rem;
            font-weight: 600;
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            color: #334155;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        .badge-chip.emerald { background: #ecfdf5; border-color: #a7f3d0; color: #065f46; }
        .badge-chip.indigo { background: #eef2ff; border-color: #c7d2fe; color: #3730a3; }

        .word-card {
            background: #151828;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
        }
        .word-card-top { display: flex; align-items: center; gap: 1.1rem; margin-bottom: 1.25rem; }
        .docx-emblem {
            width: 52px; height: 62px;
            background: linear-gradient(145deg, #185abd, #0f3e82);
            border-radius: 7px;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            color: #ffffff; font-family: 'Outfit', sans-serif;
            box-shadow: 0 6px 18px rgba(24, 90, 189, 0.45); flex-shrink: 0;
        }
        .docx-emblem-w { font-size: 1.5rem; font-weight: 800; line-height: 1; }
        .docx-emblem-tag { font-size: 0.52rem; font-weight: 800; letter-spacing: 0.08em; color: #bae6fd; margin-top: 2px; }
        .word-file-meta h3 { font-family: 'Outfit', 'Noto Sans Khmer', sans-serif; font-size: 1.25rem; font-weight: 700; color: #ffffff; margin: 0 0 4px 0; }
        .word-file-meta p { font-size: 0.8rem; color: #94a3b8; margin: 0; }

        .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem; }
        .meta-item { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 0.65rem 0.85rem; }
        .meta-label { font-size: 0.7rem; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; margin-bottom: 2px; }
        .meta-value { font-size: 0.95rem; font-weight: 700; color: #ffffff; }

        .font-pills { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
        .font-pill { font-size: 0.75rem; font-weight: 600; padding: 0.25rem 0.65rem; border-radius: 6px; background: rgba(24, 90, 189, 0.15); border: 1px solid rgba(24, 90, 189, 0.35); color: #93c5fd; }

        .paper-sheet {
            background: #ffffff; color: #1e293b; width: 100%; max-width: 820px; margin: 0 auto;
            padding: 3.5rem 3.5rem 4rem; box-shadow: 0 15px 45px rgba(0, 0, 0, 0.45); border-radius: 4px;
            line-height: 1.85; font-size: 15px; border: 1px solid #e2e8f0;
        }
        .paper-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.75rem; margin-bottom: 2rem; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; }
        .paper-footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #e2e8f0; padding-top: 0.85rem; margin-top: 2.5rem; font-size: 0.75rem; color: #94a3b8; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── App Header ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="app-header">
            <div class="app-title">Khmer PDF → Word Converter</div>
            <div class="app-khmer-sub">បម្លែងឯកសារ PDF ទៅជា Word (.docx) ដោយរក្សាពុម្ពអក្សរខ្មែរគ្រប់ប្រភេទ និងទម្រង់ដើម</div>
            <div class="badge-bar">
                <span class="badge-chip emerald">🇰🇭 Khmer Unicode 100%</span>
                <span class="badge-chip indigo">✨ Preserves Muol Light &amp; Battambang</span>
                <span class="badge-chip">📐 Two Modes: Mode A (Editable) &amp; Mode B (Exact)</span>
                <span class="badge-chip">🔍 300 DPI OCR Fallback</span>
                <span class="badge-chip">📑 Visual SSIM Verification</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar Controls ──────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Conversion Settings")
        mode = st.radio(
            "Output Mode",
            ["auto", "editable", "exact"],
            index=0,
            help="auto = intelligent hybrid; editable = Mode A (flowing tables & text); exact = Mode B (absolute coordinate layout).",
        )

        verify_ssim = st.checkbox(
            "Run Visual Verification (SSIM)",
            value=False,
            help="Compares converted Word output against original PDF at 150 DPI (requires LibreOffice).",
        )

        st.markdown("---")
        st.markdown("### ℹ️ Supported Khmer Fonts")
        st.markdown(
            """
            - **Khmer OS Muol Light / Moul** *(Headings & Royal Decrees)*
            - **Khmer OS Battambang** *(Standard Body Text)*
            - **Khmer OS Siemreap / Bokor / Content**
            - **Noto Sans Khmer / Noto Serif Khmer**
            - **Legacy Font Conversion** *(Limon, ABC)*
            """
        )

    # ── File Uploader ─────────────────────────────────────────────────────
    up = st.file_uploader("Upload a PDF document (text-based or scanned)", type=["pdf"])

    def render_docx_preview(docx_path: str, filename: str) -> str:
        try:
            doc = Document(docx_path)
            paras = []
            for p in doc.paragraphs:
                txt = p.text.strip()
                if txt:
                    paras.append(f"<p style='margin-bottom: 0.85rem;'>{html.escape(txt)}</p>")
            body = "".join(paras) if paras else "<p style='text-align:center; color:#94a3b8;'>(No text extracted)</p>"
        except Exception:
            body = "<p>(Could not parse DOCX preview)</p>"

        return f"""
        <div class="paper-sheet">
            <div class="paper-header"><span>{html.escape(filename)}</span><span>DOCX Preview</span></div>
            {body}
            <div class="paper-footer"><span>Khmer Unicode NFC</span><span>Layout Preserved</span></div>
        </div>
        """

    if up:
        clean_filename = Path(up.name).name
        original_stem = Path(clean_filename).stem
        docx_filename = f"{original_stem}.docx"

        col1, _ = st.columns([1, 4])
        with col1:
            start_btn = st.button("🚀 Convert to Word (.docx)", type="primary", use_container_width=True)

        if start_btn:
            with tempfile.TemporaryDirectory() as tmp_dir:
                src = Path(tmp_dir) / clean_filename
                dst = Path(tmp_dir) / docx_filename
                src.write_bytes(up.getvalue())

                with st.spinner("Converting PDF to Word with Khmer Unicode & dynamic font handling..."):
                    try:
                        conv_res = convert_pdf(src, dst, mode=mode, run_verification=verify_ssim)
                    except Exception as e:
                        st.error(f"Conversion failed: {e}")
                        st.stop()

                docx_bytes = dst.read_bytes()
                docx_size_kb = len(docx_bytes) / 1024

                # Render up to 3 pages for comparison
                pdf_doc = fitz.open(str(src))
                total_pages = len(pdf_doc)
                preview_images = []
                for p_idx in range(min(total_pages, 3)):
                    pix = pdf_doc[p_idx].get_pixmap(dpi=150)
                    preview_images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
                pdf_doc.close()

                docx_html = render_docx_preview(str(dst), docx_filename)

                st.session_state["converted"] = {
                    "docx_filename": docx_filename,
                    "docx_bytes": docx_bytes,
                    "docx_size_kb": docx_size_kb,
                    "conv_res": conv_res,
                    "docx_html": docx_html,
                    "preview_images": preview_images,
                    "total_pages": total_pages,
                }

        if "converted" in st.session_state:
            data = st.session_state["converted"]
            res = data["conv_res"]

            st.markdown("---")
            st.markdown(
                f"""
                <div class="word-card">
                    <div class="word-card-top">
                        <div class="docx-emblem"><div class="docx-emblem-w">W</div><div class="docx-emblem-tag">DOCX</div></div>
                        <div class="word-file-meta">
                            <h3>{html.escape(data['docx_filename'])}</h3>
                            <p>Ready for Microsoft Word · Converted with Khmer Font Preservation</p>
                        </div>
                    </div>
                    <div class="meta-grid">
                        <div class="meta-item"><div class="meta-label">📦 File Size</div><div class="meta-value">{data['docx_size_kb']:.1f} KB</div></div>
                        <div class="meta-item"><div class="meta-label">📄 Page Count</div><div class="meta-value">{data['total_pages']} Page(s)</div></div>
                        <div class="meta-item"><div class="meta-label">⚙️ Mode</div><div class="meta-value">{res.suggested_mode.upper()}</div></div>
                    </div>
                    <div class="font-pills">
                        <span style="font-size:0.78rem; color:#94a3b8; align-self:center; margin-right:4px;">Fonts:</span>
                        {"".join(f'<span class="font-pill">🇰🇭 {html.escape(f)}</span>' for f in res.applied_fonts)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.download_button(
                label=f"⬇️ Download {data['docx_filename']}",
                data=data["docx_bytes"],
                file_name=data["docx_filename"],
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )

            st.markdown("### 👁️ Document Preview")
            tab_word, tab_pdf, tab_text = st.tabs(["📄 Word Document Preview", "🖼️ Original PDF Comparison", "📝 Extracted Text"])

            with tab_word:
                st.markdown(data["docx_html"], unsafe_allow_html=True)

            with tab_pdf:
                cols = st.columns(min(len(data["preview_images"]), 3))
                for idx, img in enumerate(data["preview_images"]):
                    with cols[idx]:
                        st.image(img, caption=f"Page {idx + 1}", use_container_width=True)

            with tab_text:
                st.text_area("Plain Text Content", value=res.raw_text, height=350)
