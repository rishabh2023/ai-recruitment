"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- dev bootstrap ---
class BootstrapIn(BaseModel):
    org_name: str = "Demo Org"
    user_email: str = "recruiter@demo.test"
    password: str = "demo-password"


class BootstrapOut(BaseModel):
    org_id: UUID
    user_id: UUID
    role: str


# --- auth ---
class LoginIn(BaseModel):
    email: str
    password: str


class SignupIn(BaseModel):
    name: str
    email: str
    password: str
    org_name: str | None = None  # company/workspace; defaults to "<name>'s Organization"


class MeOut(BaseModel):
    org_id: UUID
    user_id: UUID
    role: str
    name: str | None = None
    email: str | None = None


# --- dashboard ---
class DashboardSummary(BaseModel):
    total_jobs: int
    active_jobs: int
    candidates_in_pipeline: int
    needs_review: int
    awaiting_result: int
    failed_calls: int


class ActivityItem(BaseModel):
    action: str
    entity_type: str
    to_state: str | None
    reason: str | None
    created_at: datetime


# --- jobs ---
class JobCreateIn(BaseModel):
    title: str


class JobOut(ORMModel):
    id: UUID
    title: str
    status: str
    created_at: datetime


class JobVersionIn(BaseModel):
    jd_text: str


class JobVersionOut(ORMModel):
    id: UUID
    version: int
    confirmed: bool
    extracted: dict


class WorkflowVersionOut(ORMModel):
    id: UUID
    version: int
    approved: bool


class StageOut(ORMModel):
    id: UUID
    stage_order: int
    name: str
    execution_type: str


class CriterionOut(BaseModel):
    name: str
    kind: str
    weight: float | None


class StageDetailOut(BaseModel):
    id: UUID
    stage_order: int
    name: str
    purpose: str | None
    execution_type: str
    information_requirements: list[str]
    requires_human_approval: bool
    criteria: list[CriterionOut]


class JobWorkflowOut(BaseModel):
    version_id: UUID
    version: int
    approved: bool
    stages: list[StageDetailOut]


class CriterionIn(BaseModel):
    name: str
    kind: str = "numeric"  # 'numeric' | 'rule'
    weight: float | None = None


class StageEditIn(BaseModel):
    name: str
    purpose: str | None = None
    execution_type: str  # 'ai' | 'human' | 'system'
    information_requirements: list[str] = []
    requires_human_approval: bool = False
    criteria: list[CriterionIn] = []


class WorkflowStagesIn(BaseModel):
    stages: list[StageEditIn]


# --- candidates ---
class CandidateImportIn(BaseModel):
    full_name: str
    phone: str | None = None
    email: str | None = None
    location: str | None = None
    source: str = "import"
    known_facts: dict[str, str] = {}
    starting_stage_id: UUID | None = None


class JobCandidateOut(ORMModel):
    id: UUID
    job_id: UUID
    candidate_id: UUID
    current_stage_id: UUID | None
    pipeline_state: str | None


class DecisionIn(BaseModel):
    outcome: str  # "pass" | "reject"
    reason: str | None = None


class DecisionOut(BaseModel):
    job_candidate_id: UUID
    outcome: str
    pipeline_state: str | None
    current_stage_id: UUID | None
    current_stage_name: str | None
    advanced: bool


class CandidateSummary(BaseModel):
    """Candidate identity fields recruiters see (never Hunar/telephony internals)."""

    id: UUID
    full_name: str | None
    phone: str | None
    email: str | None
    location: str | None


class JobCandidateListItem(BaseModel):
    id: UUID  # job_candidate id
    candidate: CandidateSummary
    current_stage_id: UUID | None
    current_stage_name: str | None
    pipeline_state: str | None


class LaunchOut(BaseModel):
    call_id: UUID
    normalized_status: str
    hunar_payload: dict
    dispatched: bool = False  # whether a real Hunar call was attempted
    hunar_call_id: str | None = None


class CallStatusOut(BaseModel):
    call_id: UUID
    normalized_status: str | None
    vendor_status: str | None
    hunar_call_id: str | None


class TimelineOut(BaseModel):
    job_candidate: JobCandidateOut
    candidate: CandidateSummary
    stage_runs: list[dict]
    calls: list[dict]
    facts: list[dict]


class WebhookAck(BaseModel):
    status: str
    duplicate: bool
