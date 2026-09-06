"""JD-from-PDF upload: text extraction (pure) + the upload endpoint (HTTP)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.pdf import PdfExtractionError, extract_pdf_text, tidy_jd_text
from app.db.session import engine
from app.main import app


def make_pdf(body_text: str) -> bytes:
    """A minimal single-page PDF with one line of extractable text (valid xref)."""
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\nBT /F1 18 Tf 20 120 Td (%s) Tj ET\nendstream"
        % (len(body_text) + 26, body_text.encode()),
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + obj + b"endobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref_pos)
    return bytes(out)


# --- text reflow (pure) ---
def test_tidy_rejoins_one_word_per_line_fragments():
    raw = "We are looking for someone who can deliver\nfeatures\n \nacross\n \nfrontend\n \nand\n \nbackend\n \nsystems."
    assert tidy_jd_text(raw) == "We are looking for someone who can deliver features across frontend and backend systems."


def test_tidy_preserves_headings_and_bullets():
    raw = "Key Responsibilities\n●  Build things\n●  Ship\n them\nRequired Skills\n○  Python"
    # bullets stay separate; a lowercase wrapped continuation ("them") folds into its bullet;
    # headings (capitalized, non-bullet) start their own line.
    assert tidy_jd_text(raw) == (
        "Key Responsibilities\n● Build things\n● Ship them\nRequired Skills\n○ Python"
    )


def test_tidy_collapses_double_spaces_and_space_before_punctuation():
    assert tidy_jd_text("Full  Stack  Engineer  \nExperience with databases :") == (
        "Full Stack Engineer\nExperience with databases:"
    )


def test_tidy_is_noop_on_clean_text():
    clean = "Backend Engineer\nWe want a strong Python developer."
    assert tidy_jd_text(clean) == clean


# --- pure extractor ---
def test_extract_text_from_pdf():
    assert extract_pdf_text(make_pdf("Backend Engineer JD")) == "Backend Engineer JD"


def test_extract_rejects_non_pdf_bytes():
    with pytest.raises(PdfExtractionError):
        extract_pdf_text(b"this is not a pdf")


# --- HTTP upload ---
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))


def _auth_and_job(client):
    client.post("/dev/bootstrap", json={"org_name": "Acme", "user_email": "r@acme.test", "password": "pw-123456"})
    client.post("/auth/login", json={"email": "r@acme.test", "password": "pw-123456"})
    return client.post("/jobs", json={"title": "Backend Engineer"}).json()["id"]


def test_upload_pdf_creates_version(client):
    jid = _auth_and_job(client)
    r = client.post(
        f"/jobs/{jid}/versions/upload",
        files={"file": ("jd.pdf", make_pdf("Backend Engineer Python FastAPI"), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["confirmed"] is False and "role_family" in r.json()["extracted"]


def test_upload_rejects_non_pdf(client):
    jid = _auth_and_job(client)
    r = client.post(
        f"/jobs/{jid}/versions/upload",
        files={"file": ("notes.txt", b"just text", "text/plain")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_upload_scanned_pdf_without_text_is_rejected(client):
    jid = _auth_and_job(client)
    # Valid PDF structure but no text content → no extractable text.
    empty_pdf = make_pdf("").replace(b"BT /F1 18 Tf 20 120 Td () Tj ET", b" ")
    r = client.post(
        f"/jobs/{jid}/versions/upload",
        files={"file": ("scan.pdf", empty_pdf, "application/pdf")},
    )
    assert r.status_code == 422


def test_tidy_endpoint_reflows_text(client):
    jid = _auth_and_job(client)
    r = client.post(
        f"/jobs/{jid}/versions/tidy",
        json={"text": "We deliver\nfeatures\n \nacross\n \nsystems."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "We deliver features across systems."


def test_upload_scanned_pdf_falls_back_to_llm_read(client, monkeypatch):
    """A text-less (scanned) PDF within the size/page bounds is transcribed via the provider's
    native PDF reader, and the transcribed text runs through the normal extraction path."""
    from app.api.routers import jobs as jobs_router

    class _VisionProvider:
        key = "vision-stub"

        def read_pdf_text(self, pdf_bytes: bytes) -> str:
            return "Backend Engineer Python FastAPI"

    monkeypatch.setattr(jobs_router, "get_llm_provider", lambda: _VisionProvider())

    jid = _auth_and_job(client)
    empty_pdf = make_pdf("").replace(b"BT /F1 18 Tf 20 120 Td () Tj ET", b" ")
    r = client.post(
        f"/jobs/{jid}/versions/upload",
        files={"file": ("scan.pdf", empty_pdf, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["jd_text"] == "Backend Engineer Python FastAPI"
