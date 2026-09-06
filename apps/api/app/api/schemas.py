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


class MeOut(BaseModel):
    org_id: UUID
    user_id: UUID
    role: str


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


class TimelineOut(BaseModel):
    job_candidate: JobCandidateOut
    candidate: CandidateSummary
    stage_runs: list[dict]
    calls: list[dict]
    facts: list[dict]


class WebhookAck(BaseModel):
    status: str
    duplicate: bool
