"""Job creation flow endpoints (Phase 2)."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.pdf import PdfExtractionError, extract_pdf_text, pdf_page_count, tidy_jd_text
from app.api.schemas import (
    CallingPolicyIn,
    CallingPolicyOut,
    CriterionOut,
    FunnelOut,
    FunnelStageOut,
    JobCreateIn,
    JobOut,
    JobVersionIn,
    JobVersionOut,
    StageAgentOut,
    StageAgentOverrideIn,
    StageAgentSpecIn,
    TidyTextIn,
    TidyTextOut,
    JobWorkflowOut,
    StageDetailOut,
    StageOut,
    WorkflowStagesIn,
    WorkflowVersionOut,
)
from app.db.session import get_session
from app.integrations.llm import ExtractedJob, get_llm_provider
from app.modules.audit.log import write_audit
from app.modules.candidates.models import JobCandidate
from app.modules.interviews.agent_provisioning import (
    maybe_provision_version_agents,
    provision_version_agents,
)
from app.integrations.hunar.client import HunarClient
from app.integrations.hunar.keystore import build_client, resolve_api_key
from app.modules.jobs.models import Job, JobVersion
from app.modules.jobs.service import JobActivationError, JobService
from app.config import settings
from app.modules.organizations.models import Organization
from app.modules.workflows.models import (
    CallingPolicy,
    HunarAgentConfig,
    JobWorkflow,
    JobWorkflowStage,
    JobWorkflowVersion,
    StageCriteria,
)
from app.modules.workflows.service import WorkflowEditError, WorkflowService

logger = logging.getLogger(__name__)

_EXEC_TYPES = {"ai", "human", "system"}
_CRITERION_KINDS = {"numeric", "rule"}


def _workflow_out(session: Session, version: JobWorkflowVersion) -> JobWorkflowOut:
    stages = session.scalars(
        select(JobWorkflowStage)
        .where(JobWorkflowStage.job_workflow_version_id == version.id)
        .order_by(JobWorkflowStage.stage_order.asc())
    ).all()
    out = []
    for s in stages:
        crits = session.scalars(
            select(StageCriteria).where(StageCriteria.job_workflow_stage_id == s.id)
        ).all()
        out.append(
            StageDetailOut(
                id=s.id, stage_order=s.stage_order, name=s.name, purpose=s.purpose,
                execution_type=s.execution_type,
                information_requirements=list(s.information_requirements or []),
                requires_human_approval=s.requires_human_approval,
                criteria=[
                    CriterionOut(name=c.name, kind=c.kind, weight=float(c.weight) if c.weight is not None else None)
                    for c in crits
                ],
            )
        )
    return JobWorkflowOut(version_id=version.id, version=version.version, approved=version.approved, stages=out)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_or_404(session: Session, principal: Principal, job_id: UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != principal.org_id:
        raise DomainError("Job not found.", code="not_found", status_code=404)
    return job


def _effective_workflow_version(session: Session, job_id: UUID) -> JobWorkflowVersion | None:
    """The workflow version a candidate pipeline runs against: the approved version if
    any, else the latest draft. Returns None when no workflow has been drafted yet."""
    wf = session.scalars(select(JobWorkflow).where(JobWorkflow.job_id == job_id)).first()
    if wf is None:
        return None
    return session.scalars(
        select(JobWorkflowVersion)
        .where(JobWorkflowVersion.job_workflow_id == wf.id)
        .order_by(JobWorkflowVersion.approved.desc(), JobWorkflowVersion.version.desc())
        .limit(1)
    ).first()


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobCreateIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    return JobService(session, principal.user_id).create_job(principal.org_id, body.title)


@router.get("", response_model=list[JobOut])
def list_jobs(session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    return list(
        session.scalars(
            select(Job).where(Job.org_id == principal.org_id).order_by(Job.created_at.desc())
        )
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    return _job_or_404(session, principal, job_id)


@router.get("/{job_id}/workflow", response_model=JobWorkflowOut)
def get_job_workflow(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """The job's effective workflow: the approved version if any, else the latest draft, with
    full stage detail (purpose, execution type, information to collect, approval, criteria)."""
    _job_or_404(session, principal, job_id)
    version = _effective_workflow_version(session, job_id)
    if version is None:
        raise DomainError("No workflow drafted for this job yet.", code="not_found", status_code=404)
    return _workflow_out(session, version)


@router.get("/{job_id}/version", response_model=JobVersionOut | None)
def get_latest_job_version(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """The most recent JD version (raw text + extracted details + confirmed flag), or null
    when no JD has been added yet. Powers the read/edit JD card on the job workspace."""
    job = _job_or_404(session, principal, job_id)
    return JobService(session, principal.user_id).latest_job_version(job)


@router.get("/{job_id}/funnel", response_model=FunnelOut)
def get_job_funnel(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Cumulative-reached hiring funnel for the job's effective workflow: per stage, how
    many candidates reached that stage or beyond, how many sit there now, plus top-line
    totals and completion %. Computed server-side from persisted pipeline state."""
    _job_or_404(session, principal, job_id)
    version = _effective_workflow_version(session, job_id)
    stages = (
        session.scalars(
            select(JobWorkflowStage)
            .where(JobWorkflowStage.job_workflow_version_id == version.id)
            .order_by(JobWorkflowStage.stage_order.asc())
        ).all()
        if version is not None
        else []
    )
    order_by_stage_id = {s.id: s.stage_order for s in stages}
    max_order = max((s.stage_order for s in stages), default=0)

    candidates = session.scalars(select(JobCandidate).where(JobCandidate.job_id == job_id)).all()
    total = len(candidates)
    rejected = sum(1 for c in candidates if c.pipeline_state == "REJECTED")
    completed = sum(1 for c in candidates if c.pipeline_state == "COMPLETED")
    in_progress = total - rejected - completed

    def furthest_order(c: JobCandidate) -> int:
        # A COMPLETED candidate cleared the whole workflow (past the last stage).
        if c.pipeline_state == "COMPLETED":
            return max_order
        # Otherwise the stage they currently occupy is the furthest they reached.
        # Candidates with no stage (e.g. sourced, not yet in the pipeline) or a stage from
        # a superseded version sit at the top of the funnel only.
        return order_by_stage_id.get(c.current_stage_id, 0)

    furthest = [furthest_order(c) for c in candidates]
    stage_out = []
    for s in stages:
        reached = sum(1 for f in furthest if f >= s.stage_order)
        current = sum(
            1
            for c in candidates
            if c.current_stage_id == s.id and c.pipeline_state not in ("REJECTED", "COMPLETED")
        )
        stage_out.append(
            FunnelStageOut(
                stage_id=s.id, stage_order=s.stage_order, name=s.name,
                execution_type=s.execution_type, reached=reached, current=current,
                reached_pct=round(reached / total * 100, 1) if total else 0.0,
            )
        )
    return FunnelOut(
        total=total, in_progress=in_progress, rejected=rejected, completed=completed,
        completion_pct=round(completed / total * 100, 1) if total else 0.0,
        stages=stage_out,
    )


@router.put("/{job_id}/workflow/versions/{version_id}/stages", response_model=JobWorkflowOut)
def edit_workflow_stages(
    job_id: UUID, version_id: UUID, body: WorkflowStagesIn,
    session: Session = Depends(get_session), principal: Principal = Depends(get_principal),
):
    """Replace the stages + criteria of an unapproved workflow version (review/customize)."""
    job = _job_or_404(session, principal, job_id)
    version = session.get(JobWorkflowVersion, version_id)
    if version is None or session.get(JobWorkflow, version.job_workflow_id).job_id != job.id:
        raise DomainError("Workflow version not found.", code="not_found", status_code=404)
    if not body.stages:
        raise DomainError("A workflow needs at least one stage.", code="validation_error", status_code=422)
    for s in body.stages:
        if s.execution_type not in _EXEC_TYPES:
            raise DomainError(f"Invalid execution_type '{s.execution_type}'.", code="validation_error", status_code=422)
        if not s.name.strip():
            raise DomainError("Every stage needs a name.", code="validation_error", status_code=422)
        for c in s.criteria:
            if c.kind not in _CRITERION_KINDS:
                raise DomainError(f"Invalid criterion kind '{c.kind}'.", code="validation_error", status_code=422)
    try:
        WorkflowService(session, principal.user_id).replace_stages(
            version, [s.model_dump() for s in body.stages]
        )
    except WorkflowEditError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)
    return _workflow_out(session, version)


_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
_RETRY_INTERVALS = {0, 3, 6, 9, 12, 24}
_LANGUAGES = {"ENGLISH", "HINDI", "TAMIL", "TELUGU", "KANNADA", "MARATHI", "MALAYALAM", "GUJARATI", "BENGALI", "TURKISH", "ARABIC", "SPANISH"}


def _parse_hhmm(s: str | None):
    if not s:
        return None
    try:
        hh, mm = s.split(":")
        from datetime import time as _t
        return _t(int(hh), int(mm))
    except (ValueError, TypeError):
        raise DomainError(f"Invalid time '{s}' (use HH:MM).", code="validation_error", status_code=422)


def _policy_out(p: CallingPolicy) -> CallingPolicyOut:
    return CallingPolicyOut(
        id=p.id, allowed_days=list(p.allowed_days or []),
        earliest_call_time=p.earliest_call_time.strftime("%H:%M") if p.earliest_call_time else None,
        last_call_time=p.last_call_time.strftime("%H:%M") if p.last_call_time else None,
        timezone=p.timezone, max_attempts=p.max_attempts,
        retry_interval_hours=p.retry_interval_hours, language=p.language,
    )


@router.get("/{job_id}/calling-policy", response_model=CallingPolicyOut | None)
def get_calling_policy(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _job_or_404(session, principal, job_id)
    p = session.scalars(select(CallingPolicy).where(CallingPolicy.job_id == job_id)).first()
    return _policy_out(p) if p else None


@router.put("/{job_id}/calling-policy", response_model=CallingPolicyOut)
def set_calling_policy(job_id: UUID, body: CallingPolicyIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Upsert the job's calling window / retry / language policy (Hunar guardrails)."""
    job = _job_or_404(session, principal, job_id)
    days = [d.upper() for d in body.allowed_days]
    if any(d not in _DAYS for d in days):
        raise DomainError("allowed_days must be MON..SUN.", code="validation_error", status_code=422)
    if len(set(days)) < 3:
        raise DomainError("Hunar requires at least 3 distinct calling days.", code="validation_error", status_code=422)
    earliest, last = _parse_hhmm(body.earliest_call_time), _parse_hhmm(body.last_call_time)
    if not earliest or not last or not body.timezone:
        raise DomainError("Calling policy needs a start time, end time, and IANA timezone.", code="validation_error", status_code=422)
    span = (last.hour * 60 + last.minute) - (earliest.hour * 60 + earliest.minute)
    if span < 180:
        raise DomainError("Calling window must be at least 3 hours.", code="validation_error", status_code=422)
    if body.retry_interval_hours not in _RETRY_INTERVALS:
        raise DomainError("retry_interval_hours must be one of 0,3,6,9,12,24.", code="validation_error", status_code=422)
    if not (1 <= body.max_attempts <= 10):
        raise DomainError("max_attempts must be 1..10.", code="validation_error", status_code=422)
    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except ZoneInfoNotFoundError:
            raise DomainError("timezone must be a valid IANA timezone.", code="validation_error", status_code=422)
    if body.language and body.language not in _LANGUAGES:
        raise DomainError("language is not supported by Hunar.", code="validation_error", status_code=422)

    p = session.scalars(select(CallingPolicy).where(CallingPolicy.job_id == job_id)).first()
    if p is None:
        p = CallingPolicy(org_id=job.org_id, job_id=job_id)
        session.add(p)
    p.allowed_days = list(dict.fromkeys(days))
    p.earliest_call_time = earliest
    p.last_call_time = last
    p.timezone = body.timezone
    p.max_attempts = body.max_attempts
    p.retry_interval_hours = body.retry_interval_hours
    p.language = body.language
    session.flush()
    write_audit(
        session, org_id=job.org_id, actor_user_id=principal.user_id,
        action="calling_policy.saved", entity_type="calling_policy", entity_id=p.id,
        meta={"job_id": str(job.id), "allowed_days": p.allowed_days, "max_attempts": p.max_attempts,
              "retry_interval_hours": p.retry_interval_hours, "language": p.language},
    )
    return _policy_out(p)


@router.post("/{job_id}/versions", response_model=JobVersionOut, status_code=201)
def add_job_version(job_id: UUID, body: JobVersionIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    return JobService(session, principal.user_id).add_job_version(job, body.jd_text)


@router.post("/{job_id}/versions/tidy", response_model=TidyTextOut)
def tidy_job_description(job_id: UUID, body: TidyTextIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Reflow messy JD text (e.g. one-word-per-line from a PDF copy-paste) into clean prose
    in place — same deterministic normalizer the PDF upload path uses, no LLM. Lets the
    recruiter fix formatting from the editor without leaving the app or saving a version."""
    _job_or_404(session, principal, job_id)
    return TidyTextOut(text=tidy_jd_text(body.text))


MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB
# Bounds for sending a PDF to the LLM's native reader (vision is token-expensive): a JD is a
# page or three, so cap the AI-read fallback well below the API's own limits.
LLM_PDF_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LLM_PDF_MAX_PAGES = 4


@router.post("/{job_id}/versions/upload", response_model=JobVersionOut, status_code=201)
async def add_job_version_from_pdf(
    job_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    """Create a JD version from an uploaded PDF. Primary path: extract text with pypdf (free,
    instant) and run the same extraction as pasting. If a PDF yields no text (scanned/image
    only), fall back to the LLM's native PDF reading — but only within tight size/page bounds,
    since PDF vision is token-expensive. If that also yields nothing, ask the recruiter to paste."""
    job = _job_or_404(session, principal, job_id)
    is_pdf = file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise DomainError("Only PDF files are supported.", code="validation_error", status_code=422)
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise DomainError("PDF is too large (max 10 MB).", code="validation_error", status_code=422)
    if not data:
        raise DomainError("The uploaded file is empty.", code="validation_error", status_code=422)
    try:
        text = extract_pdf_text(data)
    except PdfExtractionError:
        raise DomainError("Could not read this PDF. Please upload a valid PDF or paste the JD.", code="validation_error", status_code=422)

    if not text:
        # Scanned/image-only PDF: try Claude's native PDF reading, bounded by size + pages.
        text = _read_pdf_with_llm(data)
    if not text:
        raise DomainError(
            "No text could be read from this PDF (it may be a scan larger than the 4-page / 2 MB limit "
            "for AI reading). Please paste the JD text instead.",
            code="validation_error",
            status_code=422,
        )
    return JobService(session, principal.user_id).add_job_version(job, text)


def _read_pdf_with_llm(data: bytes) -> str:
    """LLM PDF-vision fallback for scanned PDFs, gated on size + page count. Returns "" when the
    file is over the bounds, the page count can't be read, or the provider has no vision."""
    if len(data) > LLM_PDF_MAX_BYTES:
        return ""
    try:
        if pdf_page_count(data) > LLM_PDF_MAX_PAGES:
            return ""
    except PdfExtractionError:
        return ""
    return get_llm_provider().read_pdf_text(data).strip()


@router.post("/{job_id}/versions/{version_id}/confirm", response_model=JobVersionOut)
def confirm_version(job_id: UUID, version_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    jv = session.get(JobVersion, version_id)
    if jv is None or jv.job_id != job.id:
        raise DomainError("Job version not found.", code="not_found", status_code=404)
    return JobService(session, principal.user_id).confirm_job_version(jv)


@router.post("/{job_id}/workflow/draft", response_model=WorkflowVersionOut, status_code=201)
def draft_workflow(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    jobs = JobService(session, principal.user_id)
    jv = jobs.latest_job_version(job)
    if jv is None or not jv.confirmed:
        raise DomainError("Confirm a JD version before drafting a workflow.", code="conflict", status_code=409)
    return WorkflowService(session, principal.user_id).draft_workflow_for_job(job, ExtractedJob(**jv.extracted))


@router.get("/{job_id}/workflow/versions/{version_id}/stages", response_model=list[StageOut])
def list_stages(job_id: UUID, version_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _job_or_404(session, principal, job_id)
    return list(
        session.scalars(
            select(JobWorkflowStage)
            .where(JobWorkflowStage.job_workflow_version_id == version_id)
            .order_by(JobWorkflowStage.stage_order.asc())
        )
    )


def _stage_agents_view(session: Session, version_id: UUID, *, job_title: str, company: str) -> list[StageAgentOut]:
    """The voice agent resolved for each AI stage of a version, newest binding wins. Includes a
    product-safe profile (objective + what it collects) so the recruiter has clear visibility."""
    from app.integrations.hunar.agent_spec import agent_profile, stage_intent

    stages = session.scalars(
        select(JobWorkflowStage)
        .where(JobWorkflowStage.job_workflow_version_id == version_id)
        .order_by(JobWorkflowStage.stage_order.asc())
    ).all()
    out: list[StageAgentOut] = []
    for stage in stages:
        if (stage.execution_type or "").lower() != "ai":
            continue
        cfg = session.scalars(
            select(HunarAgentConfig)
            .where(HunarAgentConfig.job_workflow_stage_id == stage.id)
            .order_by(HunarAgentConfig.created_at.desc())
        ).first()
        if cfg and (cfg.hunar_agent_id or "").strip():
            agent_id, source, editable = cfg.hunar_agent_id, "bound", True
        elif (settings.hunar_default_agent_id or "").strip():
            agent_id, source, editable = settings.hunar_default_agent_id, "default", False
        else:
            agent_id, source, editable = None, "unset", False
        # Prefer the stored (possibly recruiter-edited) profile; otherwise derive a faithful
        # preview from the stage's own intent.
        stored = cfg.spec if (cfg and isinstance(cfg.spec, dict)) else None
        preview = agent_profile(stage_intent(
            job_title=job_title, company=company, stage_name=stage.name,
            information_requirements=stage.information_requirements, purpose=stage.purpose or "",
            criteria=_criteria_names(session, stage.id),
        ))
        profile = stored or preview
        out.append(StageAgentOut(
            stage_id=stage.id, stage_name=stage.name, execution_type=stage.execution_type,
            hunar_agent_id=agent_id, source=source,
            purpose_family=profile.get("purpose_family") or preview["purpose_family"],
            stage_purpose=stage.purpose,
            objective=profile.get("objective") or preview["objective"],
            collects=profile.get("collects") or preview["collects"],
            collect_keys=profile.get("collect_keys") or preview["collect_keys"],
            editable=editable,
        ))
    return out


def _job_title_company(session: Session, job: Job) -> tuple[str, str]:
    org = session.get(Organization, job.org_id)
    return job.title, (org.name if org else "our company")


def _criteria_names(session: Session, stage_id: UUID) -> list[str]:
    return list(session.scalars(select(StageCriteria.name).where(StageCriteria.job_workflow_stage_id == stage_id)))


@router.get("/{job_id}/workflow/versions/{version_id}/agents", response_model=list[StageAgentOut])
def list_stage_agents(job_id: UUID, version_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """View the voice agent chosen for each AI stage (F-009)."""
    job = _job_or_404(session, principal, job_id)
    title, company = _job_title_company(session, job)
    return _stage_agents_view(session, version_id, job_title=title, company=company)


@router.post("/{job_id}/workflow/versions/{version_id}/agents/provision", response_model=list[StageAgentOut])
def provision_stage_agents(job_id: UUID, version_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Re-run provisioning for every AI stage of this version (idempotent — bound stages keep
    their agent). Requires the live-calls guard, since it creates vendor resources."""
    job = _job_or_404(session, principal, job_id)
    version = session.get(JobWorkflowVersion, version_id)
    if version is None:
        raise DomainError("Workflow version not found.", code="not_found", status_code=404)
    api_key, _ = resolve_api_key(session)
    from app.modules.interviews.agent_provisioning import provisioning_ready

    if not api_key or not provisioning_ready(session, job.org_id):
        raise DomainError(
            "Voice calling must be configured and enabled before provisioning agents.",
            code="conflict", status_code=409,
        )
    provision_version_agents(session, version, build_client(api_key), actor_user_id=principal.user_id)
    title, company = _job_title_company(session, job)
    return _stage_agents_view(session, version_id, job_title=title, company=company)


@router.put("/{job_id}/workflow/stages/{stage_id}/agent", response_model=StageAgentOut)
def override_stage_agent(job_id: UUID, stage_id: UUID, body: StageAgentOverrideIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Bind a specific account agent to an AI stage, overriding provisioning (F-009)."""
    job = _job_or_404(session, principal, job_id)
    stage = session.get(JobWorkflowStage, stage_id)
    if stage is None:
        raise DomainError("Stage not found.", code="not_found", status_code=404)
    if (stage.execution_type or "").lower() != "ai":
        raise DomainError("Only AI stages have a voice agent.", code="conflict", status_code=409)
    agent_id = (body.hunar_agent_id or "").strip()
    if not agent_id:
        raise DomainError("A voice agent id is required.", code="validation", status_code=422)
    from app.integrations.hunar.agent_spec import agent_profile, stage_intent

    title, company = _job_title_company(session, job)
    profile = agent_profile(stage_intent(
        job_title=title, company=company, stage_name=stage.name,
        information_requirements=stage.information_requirements, purpose=stage.purpose or "",
        criteria=_criteria_names(session, stage.id),
    ))
    session.add(HunarAgentConfig(
        job_workflow_stage_id=stage.id, hunar_agent_id=agent_id, configuration_version="override",
        spec=profile,
    ))
    write_audit(
        session, org_id=job.org_id, actor_user_id=principal.user_id,
        action="interview.agent_overridden", entity_type="job_workflow_stage", entity_id=stage.id,
        meta={"hunar_agent_id": agent_id},
    )
    session.flush()
    return _stage_agent_out_for(session, stage, job_title=title, company=company)


def _stage_agent_out_for(session: Session, stage: JobWorkflowStage, *, job_title: str, company: str) -> StageAgentOut:
    """Enriched view of a single stage's agent (reuses the version-level builder)."""
    rows = _stage_agents_view(session, stage.job_workflow_version_id, job_title=job_title, company=company)
    for r in rows:
        if r.stage_id == stage.id:
            return r
    raise DomainError("Stage not found in its version.", code="not_found", status_code=404)


@router.put("/{job_id}/workflow/stages/{stage_id}/agent/spec", response_model=StageAgentOut)
def edit_stage_agent_spec(job_id: UUID, stage_id: UUID, body: StageAgentSpecIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Edit what a stage's AI agent does — its objective and the fields it collects (F-009).
    Stored durably and pushed to the bound Hunar agent (best-effort when calling is configured)."""
    job = _job_or_404(session, principal, job_id)
    stage = session.get(JobWorkflowStage, stage_id)
    if stage is None:
        raise DomainError("Stage not found.", code="not_found", status_code=404)
    if (stage.execution_type or "").lower() != "ai":
        raise DomainError("Only AI stages have a voice agent.", code="conflict", status_code=409)
    if not (body.objective or "").strip():
        raise DomainError("An objective is required.", code="validation", status_code=422)
    title, company = _job_title_company(session, job)
    api_key, _ = resolve_api_key(session)
    client = build_client(api_key) if api_key else HunarClient.from_settings(settings)
    from app.modules.interviews.agent_provisioning import AgentProvisioningError, AgentProvisioningService

    try:
        AgentProvisioningService(session, client, actor_user_id=principal.user_id).update_stage_agent(
            stage, objective=body.objective, collects=body.collects, job_title=title,
            company=company, org_id=job.org_id,
        )
    except AgentProvisioningError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)
    return _stage_agent_out_for(session, stage, job_title=title, company=company)


@router.post("/{job_id}/workflow/versions/{version_id}/approve", response_model=WorkflowVersionOut)
def approve_workflow(job_id: UUID, version_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _job_or_404(session, principal, job_id)
    version = session.get(JobWorkflowVersion, version_id)
    if version is None:
        raise DomainError("Workflow version not found.", code="not_found", status_code=404)
    out = WorkflowService(session, principal.user_id).approve_workflow_version(version, principal.user_id)
    # F-009: eagerly bind each AI stage to an on-intent voice agent so the funnel is call-ready.
    # Best-effort — a Hunar hiccup must never block approval (stages fall back to the default).
    try:
        maybe_provision_version_agents(session, version, actor_user_id=principal.user_id)
    except Exception:  # noqa: BLE001 — provisioning is advisory at approval time
        logger.exception("Eager agent provisioning failed for workflow version %s", version_id)
    return out


@router.post("/{job_id}/activate", response_model=JobOut)
def activate_job(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    try:
        return JobService(session, principal.user_id).activate_job(job)
    except JobActivationError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)


@router.post("/{job_id}/archive", response_model=JobOut)
def archive_job(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Mark a role inactive while retaining its workflow and candidate history."""
    job = _job_or_404(session, principal, job_id)
    try:
        return JobService(session, principal.user_id).archive_job(job)
    except JobActivationError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Permanently delete a non-active role and its cascaded data. An active role must be
    archived first (409)."""
    job = _job_or_404(session, principal, job_id)
    try:
        JobService(session, principal.user_id).delete_job(job)
    except JobActivationError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)
    return None
