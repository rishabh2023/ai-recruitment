"""Job creation flow endpoints (Phase 2)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    JobCreateIn,
    JobOut,
    JobVersionIn,
    JobVersionOut,
    StageOut,
    WorkflowVersionOut,
)
from app.db.session import get_session
from app.integrations.llm import ExtractedJob
from app.modules.jobs.models import Job, JobVersion
from app.modules.jobs.service import JobActivationError, JobService
from app.modules.workflows.models import JobWorkflowStage, JobWorkflowVersion
from app.modules.workflows.service import WorkflowService

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


@router.post("/{job_id}/versions", response_model=JobVersionOut, status_code=201)
def add_job_version(job_id: UUID, body: JobVersionIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    return JobService(session, principal.user_id).add_job_version(job, body.jd_text)


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
