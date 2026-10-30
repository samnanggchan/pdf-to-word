"""
Tests for the FastAPI endpoints.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import create_khmer_text_pdf


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def sample_pdf(tmp_path: Path) -> Path:
    return create_khmer_text_pdf(tmp_path / "api_test.pdf")


class TestAPI:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_convert_success(self, client, sample_pdf: Path):
        with open(sample_pdf, "rb") as f:
            r = client.post(
                "/convert",
                files={"file": ("test.pdf", f, "application/pdf")},
            )
        assert r.status_code == 200
        assert "wordprocessingml" in r.headers["content-type"]
        assert len(r.content) > 0

    def test_convert_rejects_non_pdf(self, client):
        r = client.post(
            "/convert",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert r.status_code == 400

    def test_convert_rejects_empty_file(self, client):
        r = client.post(
            "/convert",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert r.status_code == 400

    def test_convert_returns_exact_docx_filename(self, client, sample_pdf: Path):
        with open(sample_pdf, "rb") as f:
            r = client.post(
                "/convert",
                files={"file": ("khmer_report_2024.pdf", f, "application/pdf")},
            )
        assert r.status_code == 200
        disposition = r.headers.get("content-disposition", "")
        assert 'filename="khmer_report_2024.docx"' in disposition

    def test_convert_khmer_unicode_filename(self, client, sample_pdf: Path):
        khmer_name = "02_ពាក្យសុំប្តូរ_QR_CODE_លី_ហេង_និងនាង_តាន់_គឹមហឿន.pdf"
        with open(sample_pdf, "rb") as f:
            r = client.post(
                "/convert",
                files={"file": (khmer_name, f, "application/pdf")},
            )
        assert r.status_code == 200
        assert "wordprocessingml" in r.headers["content-type"]
        disposition = r.headers.get("content-disposition", "")
        assert "filename*=" in disposition

    def test_convert_with_preview_json(self, client, sample_pdf: Path):
        with open(sample_pdf, "rb") as f:
            r = client.post(
                "/convert?format=json",
                files={"file": ("my_doc.pdf", f, "application/pdf")},
                headers={"Accept": "application/json"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["filename"] == "my_doc.docx"
        assert "download_url" in data
        assert data["total_pages"] >= 1
        assert len(data["pages"]) >= 1
        assert "text" in data["pages"][0]
        assert data["word_count"] > 0

        # Now test the download endpoint with the returned job_id
        job_id = data["job_id"]
        dl_res = client.get(f"/download/{job_id}?filename=my_doc.docx")
        assert dl_res.status_code == 200
        assert "wordprocessingml" in dl_res.headers["content-type"]
        assert 'filename="my_doc.docx"' in dl_res.headers["content-disposition"]

        # Test the page preview endpoint
        preview_res = client.get(f"/preview/{job_id}/page/1")
        assert preview_res.status_code == 200
        assert preview_res.headers["content-type"] == "image/png"
        assert len(preview_res.content) > 0

