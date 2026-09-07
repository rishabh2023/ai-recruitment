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

_MATCH_SYSTEM = (
    "You match a hiring stage to an existing voice-interview agent for reuse. You are precise and "
    "conservative: reusing a wrong-role or wrong-purpose agent means candidates get the wrong "
    "interview, so when in doubt you return null (the platform then creates a correct agent). "
    "Return ONLY a JSON object, no prose, no code fences."
)
# Reuse only on a confident match; below this the platform creates a purpose-built agent instead.
_MATCH_THRESHOLD = 0.7

_ASSESS_SYSTEM = (
    "You are a hiring analyst. From a completed screening/interview call's collected fields and "
    "summary, produce a concise, evidence-grounded assessment of the candidate against the "
    "stage's success criteria. Be fair and specific; never invent facts not present in the input. "
    "Return ONLY a JSON object, no prose, no code fences."
)


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

    def assess_interview(self, *, role, stage_name, stage_purpose, criteria, collected, call_summary):
        crit_lines = "\n".join(
            f"- {c.get('name')}" + (f" (weight {c.get('weight')})" if c.get("weight") is not None else "")
            for c in (criteria or [])
        ) or "- (no explicit criteria; assess overall fit and interest)"
        collected_lines = "\n".join(f"- {k}: {v}" for k, v in (collected or {}).items()) or "- (none captured)"
        user = (
            f"Role: {role}\nStage: {stage_name} — {stage_purpose or 'screening'}\n\n"
            f"Success criteria to evaluate against:\n{crit_lines}\n\n"
            f"Fields collected on the call:\n{collected_lines}\n\n"
            f"Call summary:\n{(call_summary or '(none)')[:4000]}\n\n"
            "Assess this candidate for THIS stage. Reply with ONLY a JSON object: "
            '{"recommendation": "strong"|"moderate"|"weak", "headline": <=10 words, '
            '"summary": 1-3 sentences for the recruiter, '
            '"criteria": [{"name": <criterion>, "score": 0-100 or null if not assessable, "notes": <=20 words}]}. '
            "Base every judgement only on the evidence above; do not invent facts."
        )
        try:
            resp = self._client.messages.create(
                model=self._model, max_tokens=700, system=_ASSESS_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(_strip_fences(raw))
        except (anthropic.APIError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Anthropic interview assessment failed (%s); using deterministic fallback.", exc)
            return self._fallback.assess_interview(
                role=role, stage_name=stage_name, stage_purpose=stage_purpose,
                criteria=criteria, collected=collected, call_summary=call_summary,
            )
        rec = str(data.get("recommendation", "")).lower()
        if rec not in ("strong", "moderate", "weak"):
            rec = "moderate"
        crit = data.get("criteria")
        return {
            "recommendation": rec,
            "headline": str(data.get("headline", ""))[:120],
            "summary": str(data.get("summary", "")),
            "criteria": crit if isinstance(crit, list) else [],
            "engine": "anthropic",
        }

    def match_agent(self, *, role, stage_purpose, company, collect, candidates):
        """Semantically pick the best-fitting existing voice agent for this stage, or None to
        create a new one. Strict: only returns an id from ``candidates`` and only above a
        confidence threshold; any API/parse error or weak match → None (caller falls back)."""
        pool = [c for c in (candidates or []) if (c.get("id") and c.get("name"))]
        if not pool:
            return None
        valid_ids = {str(c["id"]) for c in pool}
        listing = "\n".join(
            f'- id={c["id"]} | name="{c.get("name")}"'
            + (f' | objective="{str(c.get("objective"))[:200]}"' if c.get("objective") else "")
            for c in pool
        )
        collect_s = ", ".join(collect) if collect else "(interest only)"
        user = (
            f"Target stage to staff with a voice agent:\n"
            f"- role: {role}\n- company: {company}\n- stage purpose: {stage_purpose or '(unspecified)'}\n"
            f"- information to collect: {collect_s}\n\n"
            f"Existing account agents:\n{listing}\n\n"
            "Choose the agent that fits the SAME role and stage purpose. A different role, or a "
            "different stage type (e.g. a screening agent for a technical-interview stage), is NOT "
            "a match. Reply with ONLY a JSON object: "
            '{\"agent_id\": <id or null>, \"confidence\": <0..1>}.'
        )
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=200,
                system=_MATCH_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(_strip_fences(raw))
        except (anthropic.APIError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Anthropic agent match failed (%s); deferring to deterministic match.", exc)
            return None
        agent_id = data.get("agent_id")
        try:
            confidence = float(data.get("confidence", 0))
        except (ValueError, TypeError):
            confidence = 0.0
        if agent_id is None or str(agent_id) not in valid_ids or confidence < _MATCH_THRESHOLD:
            return None
        return str(agent_id)

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
