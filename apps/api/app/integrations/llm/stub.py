"""Deterministic, offline LLM stub.

A rule-based fallback so the job-creation flow works and is testable without a real LLM key.
It is intentionally simple and NOT product-grade intelligence — a real provider plugs in behind
`LLMProvider` when `PLATFORM_LLM_API_KEY` is configured. Because it is deterministic it also
makes tests stable.
"""

from __future__ import annotations

from .base import DraftCriterion, DraftStage, ExtractedJob, LLMProvider

_SKILL_VOCAB = [
    "python", "typescript", "react", "next.js", "fastapi", "postgres", "redis", "celery",
    "aws", "kubernetes", "system design", "llm", "sql", "java", "spring",
]

_SALES_HINTS = ("sales", "account executive", "sdr", "business development", "quota")
_CS_HINTS = ("customer success", "csm", "support")


def _role_family(text: str) -> str:
    t = text.lower()
    if any(h in t for h in _SALES_HINTS):
        return "sales"
    if any(h in t for h in _CS_HINTS):
        return "customer_success"
    if any(h in t for h in ("engineer", "developer", "sde", "programmer", "backend", "frontend")):
        return "engineering"
    return "general"


class StubLLMProvider:
    key = "stub"

    def read_pdf_text(self, pdf_bytes: bytes) -> str:
        return ""  # the offline stub has no vision; caller falls back to paste

    def extract_job(self, jd_text: str) -> ExtractedJob:
        text = (jd_text or "").strip()
        first_line = text.splitlines()[0].strip() if text else None
        lower = text.lower()
        skills = [s for s in _SKILL_VOCAB if s in lower]
        return ExtractedJob(
            title=first_line or None,
            role_family=_role_family(text),
            skills=skills,
        )

    def draft_workflow(self, extracted: ExtractedJob) -> list[DraftStage]:
        screening = DraftStage(
            name="Initial Screening",
            purpose="Confirm interest and basic hiring/logistical fit",
            execution_type="ai",
            order=1,
            information_requirements=[
                "interest", "current_ctc", "expected_ctc", "notice_period", "location",
            ],
            criteria=[DraftCriterion(name="Basic eligibility", kind="rule")],
        )
        if extracted.role_family == "sales":
            assessment = DraftStage(
                name="Sales Assessment", purpose="Evaluate discovery, objection handling, communication",
                execution_type="ai", order=2,
                criteria=[
                    DraftCriterion("Discovery", "numeric", 30.0),
                    DraftCriterion("Objection handling", "numeric", 30.0),
                    DraftCriterion("Communication", "numeric", 40.0),
                ],
            )
        elif extracted.role_family == "engineering":
            assessment = DraftStage(
                name="Technical Assessment", purpose="Evaluate engineering competencies",
                execution_type="ai", order=2,
                criteria=[
                    DraftCriterion("Backend / API engineering", "numeric", 30.0),
                    DraftCriterion("Problem solving", "numeric", 25.0),
                    DraftCriterion("System design", "numeric", 20.0),
                    DraftCriterion("Applied AI / LLM", "numeric", 15.0),
                    DraftCriterion("Communication", "numeric", 10.0),
                ],
            )
        else:
            assessment = DraftStage(
                name="Role Assessment", purpose="Evaluate configured role competencies",
                execution_type="ai", order=2,
                criteria=[DraftCriterion("Role fit", "numeric", 100.0)],
            )
        manager = DraftStage(
            name="Hiring Manager Review", purpose="Human review of evidence and decision",
            execution_type="human", order=3,
        )
        hr = DraftStage(
            name="HR / Compensation", purpose="Compensation and offer logistics",
            execution_type="human", order=4,
        )
        return [screening, assessment, manager, hr]


# Type check: StubLLMProvider satisfies the LLMProvider protocol.
_provider: LLMProvider = StubLLMProvider()
