"""Launch an AI stage for a job candidate (Phase 3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import LaunchOut
from app.db.session import get_session
from app.modules.candidates.models import CandidateStageRun, JobCandidate
from app.modules.interviews.service import InterviewLaunchError, InterviewService
from app.modules.jobs.models import Job
from app.modules.workflows.models import JobWorkflowStage

router = APIRouter(tags=["interviews"])


@router.post("/job-candidates/{jc_id}/launch", response_model=LaunchOut, status_code=201)
def launch(jc_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    jc = session.get(JobCandidate, jc_id)
    if jc is None:
        raise DomainError("Job candidate not found.", code="not_found", status_code=404)
    job = session.get(Job, jc.job_id)
    if job.org_id != principal.org_id:
        raise DomainError("Job candidate not found.", code="not_found", status_code=404)
    if jc.current_stage_id is None:
        raise DomainError("Candidate has no current stage.", code="conflict", status_code=409)
    stage = session.get(JobWorkflowStage, jc.current_stage_id)
    run = session.scalars(
        select(CandidateStageRun)
        .where(
            CandidateStageRun.job_candidate_id == jc.id,
            CandidateStageRun.job_workflow_stage_id == stage.id,
        )
        .order_by(CandidateStageRun.created_at.desc())
        .limit(1)
    ).first()
    if run is None:
        raise DomainError("No stage run to launch.", code="conflict", status_code=409)
    try:
        call, payload = InterviewService(session, principal.user_id).launch_ai_stage(jc, stage, run)
    except InterviewLaunchError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)
    return LaunchOut(call_id=call.id, normalized_status=call.normalized_status, hunar_payload=payload)
