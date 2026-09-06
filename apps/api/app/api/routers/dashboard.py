"""Action-oriented dashboard: org-scoped counts + recent activity.

Answers "what is happening in hiring right now, and what needs my attention?" (architecture
§31). All counts are scoped to the authenticated principal's organization.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.schemas import ActivityItem, DashboardSummary
from app.db.session import get_session
from app.modules.audit.models import AuditEvent
from app.modules.candidates.models import CandidateStageRun, JobCandidate
from app.modules.interviews.models import Call
from app.modules.jobs.models import Job

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    org = principal.org_id

    def scalar(stmt) -> int:
        return int(session.scalar(stmt) or 0)

    # Candidate runs / calls are org-scoped by joining through their job.
    runs_for_org = (
        select(func.count())
        .select_from(CandidateStageRun)
        .join(JobCandidate, JobCandidate.id == CandidateStageRun.job_candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.org_id == org)
    )
    calls_for_org = (
        select(func.count())
        .select_from(Call)
        .join(JobCandidate, JobCandidate.id == Call.job_candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.org_id == org)
    )
    return DashboardSummary(
        total_jobs=scalar(select(func.count()).select_from(Job).where(Job.org_id == org)),
        active_jobs=scalar(
            select(func.count()).select_from(Job).where(Job.org_id == org, Job.status == "active")
        ),
        candidates_in_pipeline=scalar(
            select(func.count())
            .select_from(JobCandidate)
            .join(Job, Job.id == JobCandidate.job_id)
            .where(Job.org_id == org)
        ),
        needs_review=scalar(runs_for_org.where(CandidateStageRun.status == "NEEDS_REVIEW")),
        awaiting_result=scalar(runs_for_org.where(CandidateStageRun.status == "AWAITING_RESULT")),
        failed_calls=scalar(calls_for_org.where(Call.normalized_status == "FAILED")),
    )


@router.get("/activity", response_model=list[ActivityItem])
def activity(session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    rows = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.org_id == principal.org_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(15)
    ).all()
    return [
        ActivityItem(
            action=r.action,
            entity_type=r.entity_type,
            to_state=r.to_state,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]
