"""Claude (Anthropic) platform-LLM provider — JD understanding only.

Uses Claude Haiku to extract normalized job metadata from a raw JD. This is *product
intelligence*, never candidate conversation and never a substitute for Hunar's evaluation.
Output is always a **draft** a human confirms before anything executes.

Robustness: any API/parse failure falls back to the deterministic stub so the job-creation
flow never breaks on a transient LLM error. Workflow drafting is delegated to the stub's
deterministic logic (structural, safer to keep deterministic for now).
"""

from __future__ import annotations

import json
import logging

import anthropic

from .base import DraftStage, ExtractedJob, LLMProvider
from .stub import StubLLMProvider

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You extract structured hiring metadata from a raw job description. "
    "Return ONLY a JSON object (no prose, no code fences) with these keys: "
    "title (string|null), department (string|null), location (string|null), "
    "employment_type (string|null), experience_min_years (integer|null), "
    "experience_max_years (integer|null), "
    "role_family (one of: engineering, sales, customer_success, general), "
    "skills (array of strings), responsibilities (array of strings), "
    "must_haves (array of strings). Use null/empty when unknown; never invent facts."
)

_ALLOWED_ROLE_FAMILIES = {"engineering", "sales", "customer_success", "general"}


class AnthropicLLMProvider:
    key = "anthropic"

    def __init__(self, api_key: str, model: str, *, fallback: LLMProvider | None = None) -> None:
        self._model = model
        self._fallback = fallback or StubLLMProvider()
        # Bound the call so a slow/failing LLM never hangs a web request.
        self._client = anthropic.Anthropic(api_key=api_key, timeout=30.0, max_retries=1)

    def extract_job(self, jd_text: str) -> ExtractedJob:
        text = (jd_text or "").strip()
        if not text:
            return ExtractedJob()
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": text[:20000]}],
            )
            raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(_strip_fences(raw))
            return _to_extracted_job(data)
        except (anthropic.APIError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Anthropic JD extraction failed (%s); using deterministic fallback.", exc)
            return self._fallback.extract_job(jd_text)

    def draft_workflow(self, extracted: ExtractedJob) -> list[DraftStage]:
        # Deterministic, reviewable structure; the recruiter approves before it runs.
        return self._fallback.draft_workflow(extracted)

    def read_pdf_text(self, pdf_bytes: bytes) -> str:
        """Transcribe a (typically scanned/image-only) PDF JD to plain text via Claude's native
        PDF reading. The caller bounds size/pages before calling this. Returns "" on any failure
        so the upload path can fall back to asking the recruiter to paste."""
        import base64

        b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": "This PDF is a job description. Transcribe its full text as plain text. Return ONLY the transcribed job description — no preamble, no commentary."},
                ]}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        except anthropic.APIError as exc:
            logger.warning("Anthropic PDF read failed (%s).", exc)
            return ""


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


def _to_extracted_job(data: dict) -> ExtractedJob:
    def _str_list(v) -> list[str]:
        return [str(x) for x in v if isinstance(x, (str, int, float))] if isinstance(v, list) else []

    def _opt_int(v) -> int | None:
        try:
            return int(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    role_family = data.get("role_family")
    if role_family not in _ALLOWED_ROLE_FAMILIES:
        role_family = "general"
    return ExtractedJob(
        title=(data.get("title") or None),
        department=(data.get("department") or None),
        location=(data.get("location") or None),
        employment_type=(data.get("employment_type") or None),
        experience_min_years=_opt_int(data.get("experience_min_years")),
        experience_max_years=_opt_int(data.get("experience_max_years")),
        role_family=role_family,
        skills=_str_list(data.get("skills")),
        responsibilities=_str_list(data.get("responsibilities")),
        must_haves=_str_list(data.get("must_haves")),
    )
