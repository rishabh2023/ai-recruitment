"""Job creation flow endpoints (Phase 2)."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.pdf import PdfExtractionError, extract_pdf_text
from app.api.schemas import (
    CallingPolicyIn,
    CallingPolicyOut,
    CriterionOut,
    JobCreateIn,
    JobOut,
    JobVersionIn,
    JobVersionOut,
    JobWorkflowOut,
    StageDetailOut,
    StageOut,
    WorkflowStagesIn,
    WorkflowVersionOut,
)
from app.db.session import get_session
from app.integrations.llm import ExtractedJob
from app.modules.audit.log import write_audit
from app.modules.jobs.models import Job, JobVersion
from app.modules.jobs.service import JobActivationError, JobService
from app.modules.workflows.models import (
    CallingPolicy,
    JobWorkflow,
    JobWorkflowStage,
    JobWorkflowVersion,
    StageCriteria,
)
from app.modules.workflows.service import WorkflowEditError, WorkflowService

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
    wf = session.scalars(select(JobWorkflow).where(JobWorkflow.job_id == job_id)).first()
    if wf is None:
        raise DomainError("No workflow drafted for this job yet.", code="not_found", status_code=404)
    version = session.scalars(
        select(JobWorkflowVersion)
        .where(JobWorkflowVersion.job_workflow_id == wf.id)
        .order_by(JobWorkflowVersion.approved.desc(), JobWorkflowVersion.version.desc())
        .limit(1)
    ).first()
    if version is None:
        raise DomainError("No workflow version yet.", code="not_found", status_code=404)
    return _workflow_out(session, version)


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


MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/{job_id}/versions/upload", response_model=JobVersionOut, status_code=201)
async def add_job_version_from_pdf(
    job_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    """Create a JD version from an uploaded PDF: extract its text, then run the same
    extraction path as pasting. Scanned/image-only PDFs (no extractable text) are rejected
    with a clear message so the recruiter can paste instead."""
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
        raise DomainError(
            "No text could be extracted (the PDF may be scanned images). Please paste the JD instead.",
            code="validation_error",
            status_code=422,
        )
    return JobService(session, principal.user_id).add_job_version(job, text)


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


@router.post("/{job_id}/workflow/versions/{version_id}/approve", response_model=WorkflowVersionOut)
def approve_workflow(job_id: UUID, version_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _job_or_404(session, principal, job_id)
    version = session.get(JobWorkflowVersion, version_id)
    if version is None:
        raise DomainError("Workflow version not found.", code="not_found", status_code=404)
    return WorkflowService(session, principal.user_id).approve_workflow_version(version, principal.user_id)


@router.post("/{job_id}/activate", response_model=JobOut)
def activate_job(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    try:
        return JobService(session, principal.user_id).activate_job(job)
    except JobActivationError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)
