"""Platform LLM boundary — product intelligence only.

Used ONLY for work Hunar does not provide: JD understanding, role-family classification,
structured skill extraction, and draft workflow/rubric generation. Never candidate
conversation, never duplicating Hunar evaluation (see docs/architecture.md, docs/intent.md).

All outputs are **drafts** that a human reviews/edits/approves before anything executes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ExtractedJob:
    """Normalized job metadata extracted from a raw JD."""

    title: str | None = None
    department: str | None = None
    location: str | None = None
    employment_type: str | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    role_family: str | None = None  # e.g. engineering, sales, customer_success, general
    skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    must_haves: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DraftCriterion:
    name: str
    kind: str  # 'numeric' | 'rule'
    weight: float | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DraftStage:
    name: str
    purpose: str
    execution_type: str  # 'ai' | 'human' | 'system'
    order: int
    information_requirements: list[str] = field(default_factory=list)
    criteria: list[DraftCriterion] = field(default_factory=list)


class LLMProvider(Protocol):
    """Product-intelligence provider. Implementations return drafts only."""

    key: str

    def extract_job(self, jd_text: str) -> ExtractedJob: ...

    def draft_workflow(self, extracted: ExtractedJob) -> list[DraftStage]: ...
