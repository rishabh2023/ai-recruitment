"""Extract plain text from an uploaded PDF (job descriptions).

Server-side so JD understanding stays in one place. Text-based PDFs extract cleanly; scanned /
image-only PDFs yield little or no text — callers should surface that and fall back to paste.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PyPdfError


class PdfExtractionError(Exception):
    """The bytes could not be parsed as a PDF."""


# A line that opens a list item: •, ●, ○, ▪, ‣, ⁃, ·, -, –, *, or "1." / "2)".
_BULLET_RE = re.compile(r"^\s*(?:[•●○▪‣⁃·*–‐\-]|\d+[.)])\s+")
# A space that pypdf wrongly inserted before punctuation ("databases :" -> "databases:").
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")


def tidy_jd_text(raw: str) -> str:
    """Reflow text that a PDF extractor broke into ragged / one-word-per-line fragments back
    into readable prose, without an LLM.

    PDF text extraction often emits a newline after every wrapped word, so a single sentence
    arrives as a column of single words. We rebuild logical lines with a conservative rule:
    a line is a *continuation* of the previous one (join with a space) only when it clearly
    is — it starts lowercase and is not a list item. Anything that starts with a bullet, a
    capital letter, or a digit begins a new line, so real headings, list items, and sentence
    starts are preserved. Worst case a wrapped line starting with a proper noun stays on its
    own line — readable — never the one-word-per-line column we started with.
    """
    if not raw:
        return raw
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of spaces/tabs inside each physical line and drop blank lines (the blank
    # lines here are extraction artifacts between fragments, not paragraph structure).
    phys = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.split("\n")]

    out: list[str] = []
    for ln in phys:
        if not ln:
            continue
        first = ln[0]
        is_continuation = out and not _BULLET_RE.match(ln) and (first.islower() or first in "/&(")
        if is_continuation:
            prev = out[-1]
            # "well-\ndefined" -> "well-defined"; otherwise separate with a space.
            out[-1] = prev[:-1] + ln if prev.endswith("-") else prev + " " + ln
        else:
            out.append(ln)

    cleaned = "\n".join(out)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    return cleaned.strip()


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, ValueError, OSError) as exc:
        raise PdfExtractionError(str(exc)) from exc
    return tidy_jd_text("\n".join(parts))


def pdf_page_count(data: bytes) -> int:
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise PdfExtractionError(str(exc)) from exc
