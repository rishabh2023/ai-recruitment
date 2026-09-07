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


class AuditLogItem(BaseModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    from_state: str | None
    to_state: str | None
    reason: str | None
    actor_email: str | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int


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


class TidyTextIn(BaseModel):
    text: str


class TidyTextOut(BaseModel):
    text: str


class JobVersionOut(ORMModel):
    id: UUID
    version: int
    confirmed: bool
    jd_text: str
    extracted: dict


class FunnelStageOut(BaseModel):
    stage_id: UUID
    stage_order: int
    name: str
    execution_type: str
    reached: int  # candidates whose furthest-reached stage is at or beyond this one
    current: int  # candidates sitting in this stage now (not rejected/completed)
    reached_pct: float  # reached / total, 0..100 (0 when no candidates)


class FunnelOut(BaseModel):
    total: int
    in_progress: int
    rejected: int
    completed: int
    completion_pct: float  # completed / total, 0..100
    stages: list[FunnelStageOut]


class WorkflowVersionOut(ORMModel):
    id: UUID
    version: int
    approved: bool


class StageOut(ORMModel):
    id: UUID
    stage_order: int
    name: str
    execution_type: str


class StageAgentOut(BaseModel):
    """The voice agent chosen for one AI stage (F-009). ``source`` tells the recruiter whether the
    stage has its own bound agent or is falling back to the global default. ``objective`` and
    ``collects`` describe, in product language, what the agent does — no telephony internals."""

    stage_id: UUID
    stage_name: str
    execution_type: str
    hunar_agent_id: str | None
    source: str  # bound | default | unset
    purpose_family: str  # screening | technical | sales | manager | compensation
    stage_purpose: str | None
    objective: str  # what the agent is trying to accomplish on the call
    collects: list[str]  # plain-language list of what it will ask about
    collect_keys: list[str]  # the underlying field keys (for editing)
    editable: bool  # true when the stage has its own bound agent that can be edited


class StageAgentOverrideIn(BaseModel):
    hunar_agent_id: str


class StageAgentSpecIn(BaseModel):
    """Recruiter edit of what a stage's agent does."""

    objective: str
    collects: list[str]  # field keys to collect (e.g. interest, expected_ctc, notice_period)


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


# --- funnels (org-owned reusable workflow templates) ---
class FunnelSummaryOut(BaseModel):
    id: UUID
    name: str
    version: int  # latest version number (0 when a funnel somehow has no version)
    stage_count: int
    archived: bool
    created_at: datetime


class FunnelStageSpecOut(BaseModel):
    stage_order: int
    name: str
    purpose: str | None
    execution_type: str
    information_requirements: list[str]
    requires_human_approval: bool
    criteria: list[CriterionOut]


class FunnelDetailOut(BaseModel):
    id: UUID
    name: str
    version: int
    archived: bool
    stages: list[FunnelStageSpecOut]


class FunnelPresetOut(BaseModel):
    key: str
    name: str
    description: str
    stages: list[FunnelStageSpecOut]


class FunnelCreateIn(BaseModel):
    name: str
    stages: list[StageEditIn]


class FunnelStagesIn(BaseModel):
    stages: list[StageEditIn]


class FunnelRenameIn(BaseModel):
    name: str


class FunnelUseIn(BaseModel):
    job_id: UUID


class CallingPolicyIn(BaseModel):
    allowed_days: list[str] = []  # MON..SUN
    earliest_call_time: str | None = None  # "HH:MM"
    last_call_time: str | None = None  # "HH:MM"
    timezone: str | None = None  # IANA, e.g. Asia/Kolkata
    max_attempts: int = 3
    retry_interval_hours: int = 6
    language: str | None = None  # ENGLISH, HINDI, ... (Hunar agent-level)


class CallingPolicyOut(CallingPolicyIn):
    id: UUID


# --- candidates ---
class CandidateImportIn(BaseModel):
    full_name: str
    phone: str | None = None
    email: str | None = None
    location: str | None = None
    source: str = "import"
    known_facts: dict[str, str] = {}
    starting_stage_id: UUID | None = None


class CandidateUpdateIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    location: str | None = None


class PipelinePage(ORMModel):
    items: list["JobCandidateListItem"]
    total: int  # matching the current filter (for "X of N" + pagination)
    page: int
    page_size: int


class CsvRowError(BaseModel):
    row: int
    reason: str


class CsvImportResult(BaseModel):
    added: int
    skipped: int
    errors: list[CsvRowError]


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


class OrgCandidateListItem(BaseModel):
    """A candidate participation across the whole org (candidate + which job)."""

    id: UUID  # job_candidate id
    candidate: CandidateSummary
    job_id: UUID
    job_title: str
    current_stage_name: str | None
    pipeline_state: str | None
    created_at: datetime


class LaunchOut(BaseModel):
    call_id: UUID
    normalized_status: str
    hunar_payload: dict
    dispatched: bool = False  # whether a real Hunar call was attempted
    hunar_call_id: str | None = None


class BulkLaunchResultItem(BaseModel):
    job_candidate_id: UUID
    name: str | None = None
    # "launched" (a call was created/dispatched), "skipped" (already handled), or
    # "failed" (an error prevented launching this one — the others still proceed).
    outcome: str
    reason: str | None = None
    call_id: UUID | None = None
    dispatched: bool = False


class BulkLaunchOut(BaseModel):
    stage_id: UUID
    launched: int
    skipped: int
    failed: int
    results: list[BulkLaunchResultItem]


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
    # Latest platform-LLM assessment of a completed call (recommendation, summary, per-criterion),
    # or null when none has been produced yet.
    assessment: dict | None = None


class WebhookAck(BaseModel):
    status: str
    duplicate: bool


# --- sourcing (people search & outreach — Flow B) ---
class PeopleSearchIn(BaseModel):
    titles: list[str] = []
    keywords: list[str] = []
    locations: list[str] = []
    skills: list[str] = []
    seniorities: list[str] = []
    page: int = 1
    page_size: int = 25
    provider: str | None = None  # which people-search provider to query; default = configured


class ProviderOption(BaseModel):
    key: str
    label: str
    configured: bool  # whether this provider has an API key set (usable)


class ProvidersOut(BaseModel):
    default: str | None  # configured default provider, if any is usable
    providers: list[ProviderOption]


class ExternalCandidateOut(BaseModel):
    source: str
    source_id: str
    full_name: str | None
    title: str | None
    company: str | None
    location: str | None
    linkedin_url: str | None
    has_contact: bool  # whether contact details exist without enrichment (search rarely does)


class PeopleSearchOut(BaseModel):
    provider: str  # provider that produced these results
    requested_provider: str  # manually requested provider, or "auto"
    is_sample: bool  # True when these are sample profiles, not live data
    notice: str | None  # shown to the recruiter when the result is degraded/sample
    total: int | None
    page: int
    has_more: bool
    suggested_query: PeopleSearchIn  # original recruiter/JD query
    applied_query: PeopleSearchIn  # query that produced results (may be Auto-broadened)
    candidates: list[ExternalCandidateOut]


class SourceCandidateIn(BaseModel):
    source: str
    source_id: str
    full_name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    linkedin_url: str | None = None


class SourceCandidatesIn(BaseModel):
    candidates: list[SourceCandidateIn]


class SourceCandidatesOut(BaseModel):
    added: int
    skipped: int  # duplicates or invalid rows not added
    job_candidate_ids: list[UUID]


# --- settings ---
class SettingsUserOut(BaseModel):
    id: UUID
    name: str | None
    email: str
    role: str


class PendingInviteOut(BaseModel):
    id: UUID
    email: str
    name: str | None
    role: str
    created_at: datetime
    expires_at: datetime


class SettingsOut(BaseModel):
    org_name: str
    is_admin: bool  # whether the current user may edit settings
    default_provider: str | None
    providers: list[ProviderOption]  # configured reflects org keys + env
    live_calls_enabled: bool
    users: list[SettingsUserOut]
    invites: list[PendingInviteOut]  # pending team invitations


class InviteCreateIn(BaseModel):
    email: str
    role: str = "recruiter"  # recruiter | hiring_manager | admin
    name: str | None = None


class InviteCreatedOut(BaseModel):
    id: UUID
    email: str
    name: str | None
    role: str
    expires_at: datetime
    accept_url: str  # one-time link (contains the token) — shown once, share with the invitee


class InvitePreviewOut(BaseModel):
    org_name: str
    email: str
    role: str


class AcceptInviteIn(BaseModel):
    token: str
    password: str
    name: str | None = None


class SettingsUpdateIn(BaseModel):
    org_name: str | None = None
    default_provider: str | None = None
    live_calls_enabled: bool | None = None
    # provider -> api key. Non-empty sets/replaces; empty string clears. Never echoed back.
    provider_keys: dict[str, str] | None = None


class EnrichOut(BaseModel):
    phone: str | None
    email: str | None
    provider: str
    requested_provider: str
    is_sample: bool
    already_had_contact: bool
    notice: str | None
    pipeline_state: str | None


# --- hunar ---
class HunarHealthOut(BaseModel):
    status: str  # healthy | invalid | unconfigured | unreachable
    source: str | None  # override | env | None
    checked_at: str


class HunarKeyUpdateIn(BaseModel):
    api_key: str
