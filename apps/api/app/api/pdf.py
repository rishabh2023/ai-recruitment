"""Extract plain text from an uploaded PDF (job descriptions).

Server-side so JD understanding stays in one place. Text-based PDFs extract cleanly; scanned /
image-only PDFs yield little or no text — callers should surface that and fall back to paste.
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError


class PdfExtractionError(Exception):
    """The bytes could not be parsed as a PDF."""


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, ValueError, OSError) as exc:
        raise PdfExtractionError(str(exc)) from exc
    return "\n".join(parts).strip()
