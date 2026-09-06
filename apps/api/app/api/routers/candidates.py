"""Candidate import + timeline (Phase 3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    CandidateImportIn,
    CandidateSummary,
    JobCandidateListItem,
    JobCandidateOut,
    TimelineOut,
)
from app.db.session import get_session
from app.modules.candidates.models import Candidate, CandidateFact, CandidateStageRun, JobCandidate
from app.modules.candidates.service import CandidateService
from app.modules.interviews.models import Call
from app.modules.jobs.models import Job
from app.modules.workflows.models import JobWorkflowStage

router = APIRouter(tags=["candidates"])


def _job_or_404(session: Session, principal: Principal, job_id: UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != principal.org_id:
        raise DomainError("Job not found.", code="not_found", status_code=404)
    return job


def _jc_or_404(session: Session, principal: Principal, jc_id: UUID) -> JobCandidate:
    jc = session.get(JobCandidate, jc_id)
    if jc is None:
        raise DomainError("Job candidate not found.", code="not_found", status_code=404)
    job = session.get(Job, jc.job_id)
    if job.org_id != principal.org_id:
        raise DomainError("Job candidate not found.", code="not_found", status_code=404)
    return jc


@router.post("/jobs/{job_id}/candidates", response_model=JobCandidateOut, status_code=201)
def import_candidate(job_id: UUID, body: CandidateImportIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    starting = None
    if body.starting_stage_id:
        starting = session.get(JobWorkflowStage, body.starting_stage_id)
        if starting is None:
            raise DomainError("Starting stage not found.", code="not_found", status_code=404)
    return CandidateService(session, principal.user_id).import_candidate(
        job, full_name=body.full_name, phone=body.phone, email=body.email,
        location=body.location, source=body.source, known_facts=body.known_facts,
        starting_stage=starting,
    )


def _summary(c: Candidate) -> CandidateSummary:
    return CandidateSummary(
        id=c.id, full_name=c.full_name, phone=c.phone, email=c.email, location=c.location
    )


def _stage_names(session: Session, stage_ids: set[UUID]) -> dict[UUID, str]:
    """Resolve stage id → name for the stages referenced by a candidate's runs/current stage."""
    if not stage_ids:
        return {}
    rows = session.scalars(
        select(JobWorkflowStage).where(JobWorkflowStage.id.in_(stage_ids))
    ).all()
    return {s.id: s.name for s in rows}


@router.get("/jobs/{job_id}/candidates", response_model=list[JobCandidateListItem])
def list_candidates(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _job_or_404(session, principal, job_id)
    jcs = session.scalars(
        select(JobCandidate).where(JobCandidate.job_id == job_id).order_by(JobCandidate.created_at.desc())
    ).all()
    names = _stage_names(session, {jc.current_stage_id for jc in jcs if jc.current_stage_id})
    items = []
    for jc in jcs:
        candidate = session.get(Candidate, jc.candidate_id)
        items.append(
            JobCandidateListItem(
                id=jc.id,
                candidate=_summary(candidate),
                current_stage_id=jc.current_stage_id,
                current_stage_name=names.get(jc.current_stage_id) if jc.current_stage_id else None,
                pipeline_state=jc.pipeline_state,
            )
        )
    return items


@router.get("/job-candidates/{jc_id}/timeline", response_model=TimelineOut)
def timeline(jc_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    jc = _jc_or_404(session, principal, jc_id)
    candidate = session.get(Candidate, jc.candidate_id)
    runs = session.scalars(
        select(CandidateStageRun)
        .where(CandidateStageRun.job_candidate_id == jc.id)
        .order_by(CandidateStageRun.created_at.asc())
    ).all()
    calls = session.scalars(
        select(Call).where(Call.job_candidate_id == jc.id).order_by(Call.created_at.asc())
    ).all()
    facts = session.scalars(select(CandidateFact).where(CandidateFact.job_candidate_id == jc.id)).all()
    names = _stage_names(session, {r.job_workflow_stage_id for r in runs})
    return TimelineOut(
        job_candidate=JobCandidateOut.model_validate(jc),
        candidate=_summary(candidate),
        stage_runs=[
            {
                "id": str(r.id),
                "stage_id": str(r.job_workflow_stage_id),
                "stage_name": names.get(r.job_workflow_stage_id),
                "status": r.status,
            }
            for r in runs
        ],
        calls=[{"id": str(c.id), "normalized_status": c.normalized_status, "hunar_call_id": c.hunar_call_id} for c in calls],
        facts=[{"field_key": f.field_key, "value": f.value, "source": f.source} for f in facts],
    )
