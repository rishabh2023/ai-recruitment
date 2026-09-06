"""Sourcing endpoints — People Search & Outreach (Flow B).

- GET  /jobs/{job_id}/sourcing/suggested-query  → JD-derived starting query
- POST /jobs/{job_id}/sourcing/search           → run people search (with safe fallback)
- POST /jobs/{job_id}/sourcing/add              → add selected candidates to the pipeline

Recruiters never see provider internals beyond a plain provider label and a notice when the
result is sample/degraded.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    ExternalCandidateOut,
    PeopleSearchIn,
    PeopleSearchOut,
    SourceCandidatesIn,
    SourceCandidatesOut,
)
from app.config import settings
from app.db.session import get_session
from app.integrations.people_search.base import ExternalCandidate, PeopleSearchQuery
from app.modules.jobs.models import Job
from app.modules.sourcing import SourcingService
from app.modules.sourcing.service import SourceCandidateInput

router = APIRouter(prefix="/jobs/{job_id}/sourcing", tags=["sourcing"])


def _job_or_404(session: Session, principal: Principal, job_id: UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != principal.org_id:
        raise DomainError("Job not found.", code="not_found", status_code=404)
    return job


def _query_to_schema(q: PeopleSearchQuery) -> PeopleSearchIn:
    return PeopleSearchIn(
        titles=list(q.titles), keywords=list(q.keywords), locations=list(q.locations),
        skills=list(q.skills), seniorities=list(q.seniorities),
        page=q.page, page_size=q.page_size,
    )


def _candidate_out(c: ExternalCandidate) -> ExternalCandidateOut:
    return ExternalCandidateOut(
        source=c.source, source_id=c.source_id, full_name=c.full_name, title=c.title,
        company=c.company, location=c.location, linkedin_url=c.linkedin_url,
        has_contact=bool(c.phone or c.email),
    )


@router.get("/suggested-query", response_model=PeopleSearchIn)
def suggested_query(job_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    return _query_to_schema(SourcingService(session, principal.user_id).suggest_query(job))


@router.post("/search", response_model=PeopleSearchOut)
def search(job_id: UUID, body: PeopleSearchIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    if body.page_size < 1 or body.page_size > 100:
        raise DomainError("page_size must be 1..100.", code="validation_error", status_code=422)
    if body.page < 1:
        raise DomainError("page must be >= 1.", code="validation_error", status_code=422)
    query = PeopleSearchQuery(
        titles=[t for t in body.titles if t.strip()],
        keywords=[k for k in body.keywords if k.strip()],
        locations=[loc for loc in body.locations if loc.strip()],
        skills=[s for s in body.skills if s.strip()],
        seniorities=[s for s in body.seniorities if s.strip()],
        page=body.page, page_size=body.page_size,
    )
    outcome = SourcingService(session, principal.user_id).search(
        job, query, settings.people_search_provider
    )
    return PeopleSearchOut(
        provider=outcome.provider,
        requested_provider=outcome.requested_provider,
        is_sample=outcome.is_sample,
        notice=outcome.notice,
        total=outcome.result.total,
        page=outcome.result.page,
        has_more=outcome.result.has_more,
        suggested_query=_query_to_schema(query),
        candidates=[_candidate_out(c) for c in outcome.result.candidates],
    )


@router.post("/add", response_model=SourceCandidatesOut, status_code=201)
def add_candidates(job_id: UUID, body: SourceCandidatesIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    if not body.candidates:
        raise DomainError("Select at least one candidate to add.", code="validation_error", status_code=422)
    selections = [
        SourceCandidateInput(
            source=c.source, source_id=c.source_id, full_name=c.full_name, title=c.title,
            company=c.company, location=c.location, linkedin_url=c.linkedin_url,
        )
        for c in body.candidates
    ]
    created = SourcingService(session, principal.user_id).add_to_pipeline(job, selections)
    return SourceCandidatesOut(
        added=len(created),
        skipped=len(selections) - len(created),
        job_candidate_ids=[jc.id for jc in created],
    )
