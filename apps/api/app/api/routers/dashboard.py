"""Action-oriented dashboard: org-scoped counts + recent activity.

Answers "what is happening in hiring right now, and what needs my attention?" (architecture
§31). All counts are scoped to the authenticated principal's organization.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.schemas import ActivityItem, AuditLogItem, AuditPage, DashboardSummary
from app.db.session import get_session
from app.modules.audit.models import AuditEvent
from app.modules.organizations.models import User
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


@router.get("/audit", response_model=AuditPage)
def audit_log(
    page: int = 1,
    page_size: int = 50,
    q: str | None = None,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    """Paginated org audit trail (most recent first). Immutable record of consequential
    actions. `q` matches action, entity type, state transition, reason, or actor email —
    server-side so a long-lived org's log stays bounded per request."""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)

    base = select(AuditEvent).where(AuditEvent.org_id == principal.org_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        # Resolve actor emails matching the term to their user ids so a search on actor works.
        actor_ids = session.scalars(
            select(User.id).where(User.org_id == principal.org_id, User.email.ilike(like))
        ).all()
        conds = [
            AuditEvent.action.ilike(like),
            AuditEvent.entity_type.ilike(like),
            AuditEvent.from_state.ilike(like),
            AuditEvent.to_state.ilike(like),
            AuditEvent.reason.ilike(like),
        ]
        if actor_ids:
            conds.append(AuditEvent.actor_user_id.in_(actor_ids))
        base = base.where(or_(*conds))

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.scalars(
        base.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    emails = {
        u.id: u.email
        for u in session.scalars(
            select(User).where(User.id.in_({r.actor_user_id for r in rows if r.actor_user_id}))
        ).all()
    } if rows else {}
    items = [
        AuditLogItem(
            id=r.id, action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
            from_state=r.from_state, to_state=r.to_state, reason=r.reason,
            actor_email=emails.get(r.actor_user_id), created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditPage(items=items, total=total, page=page, page_size=page_size)
