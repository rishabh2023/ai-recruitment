"""Candidate import + timeline (Phase 3)."""

from __future__ import annotations

from uuid import UUID

import csv
import io

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    CandidateImportIn,
    CandidateSummary,
    CandidateUpdateIn,
    CsvImportResult,
    CsvRowError,
    DecisionIn,
    DecisionOut,
    EnrichOut,
    JobCandidateListItem,
    JobCandidateOut,
    OrgCandidateListItem,
    PipelinePage,
    TimelineOut,
)
from app.modules.audit.log import write_audit
from app.modules.sourcing import SourcingProviderError, SourcingService
from app.db.session import get_session
from app.modules.candidates.models import Candidate, CandidateFact, CandidateStageRun, JobCandidate
from app.modules.candidates.service import CandidateService
from app.modules.interviews.models import Call
from app.modules.jobs.models import Job
from app.modules.workflows.models import JobWorkflowStage
from app.workflow_execution import StageOutcome, StageRunState, WorkflowExecutionService

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


def _digits(v: str | None) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _phone_match(a: str, b: str) -> bool:
    """Same number, tolerant of country-code presence: equal, or one is the other's suffix
    (e.g. "+918965823672" vs a bare "8965823672"). The 7-digit floor avoids false matches."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 7 and long.endswith(short)


def _duplicate_in_job(session: Session, job_id: UUID, *, phone: str | None, email: str | None) -> str | None:
    """A candidate is a duplicate within a role if the same phone or the same email already
    participates in that job. Returns a human message, or None when unique."""
    new_phone, new_email = _digits(phone), (email or "").strip().lower()
    if not new_phone and not new_email:
        return None
    rows = session.execute(
        select(Candidate.phone, Candidate.email)
        .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
        .where(JobCandidate.job_id == job_id)
    ).all()
    for ph, em in rows:
        if new_phone and _phone_match(_digits(ph), new_phone):
            return "A candidate with this phone number is already in this role."
        if new_email and (em or "").strip().lower() == new_email:
            return "A candidate with this email is already in this role."
    return None


@router.post("/jobs/{job_id}/candidates", response_model=JobCandidateOut, status_code=201)
def import_candidate(job_id: UUID, body: CandidateImportIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    job = _job_or_404(session, principal, job_id)
    dup = _duplicate_in_job(session, job_id, phone=body.phone, email=body.email)
    if dup:
        raise DomainError(dup, code="conflict", status_code=409)
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


# Header aliases → canonical field. Recruiters export from many tools, so accept common spellings.
_CSV_NAME_KEYS = {"name", "full name", "fullname", "full_name", "candidate", "candidate name"}
_CSV_PHONE_KEYS = {"mobile", "phone", "phone number", "mobile number", "contact", "contact number", "phone_number", "mobile_number"}
_CSV_CC_KEYS = {"country code", "countrycode", "country", "dial code", "dialcode", "isd", "code"}
_CSV_EMAIL_KEYS = {"email", "e-mail", "email address", "mail"}
_CSV_LOCATION_KEYS = {"location", "city", "place", "based in"}
CSV_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
CSV_MAX_ROWS = 2000


def _norm_header(h: str) -> str:
    return " ".join((h or "").strip().lower().replace("_", " ").split())


def _pick(row: dict[str, str], header_map: dict[str, str], keys: set[str]) -> str:
    for norm, original in header_map.items():
        if norm in keys:
            return (row.get(original) or "").strip()
    return ""


def _to_e164(phone: str, country_code: str) -> str | None:
    """Combine a national number + country code into an E.164 string (+<cc><digits>).

    A number that already carries a '+' is kept as-is (just cleaned). Otherwise a country code
    is required — Hunar (and any dialer) cannot route a bare national number. Returns None when
    no country code is available so the caller can report the row instead of dialing garbage.
    """
    raw = (phone or "").strip()
    if not raw:
        return None
    if raw.startswith("+"):
        digits = "".join(ch for ch in raw if ch.isdigit())
        return f"+{digits}" if digits else None
    national = "".join(ch for ch in raw if ch.isdigit())
    if not national:
        return None
    cc = "".join(ch for ch in (country_code or "") if ch.isdigit())
    if not cc:
        return None
    return f"+{cc}{national}"


@router.post("/jobs/{job_id}/candidates/import-csv", response_model=CsvImportResult, status_code=201)
async def import_candidates_csv(
    job_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    """Bulk-add candidates from a CSV. Name and mobile are mandatory per row; email and
    location are optional. Unrecognized/blank rows are reported per-row rather than failing
    the whole upload, so a recruiter can fix a few lines and re-upload. Duplicate phones
    already in this job are skipped (idempotent re-uploads)."""
    job = _job_or_404(session, principal, job_id)
    raw = await file.read()
    if not raw:
        raise DomainError("The CSV file is empty.", code="validation_error", status_code=422)
    if len(raw) > CSV_MAX_BYTES:
        raise DomainError("CSV is too large (max 2 MB).", code="validation_error", status_code=422)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise DomainError("Could not read CSV headers. The first row must be column names.", code="validation_error", status_code=422)
    header_map = {_norm_header(h): h for h in reader.fieldnames if h}
    if not (set(header_map) & _CSV_NAME_KEYS) or not (set(header_map) & _CSV_PHONE_KEYS):
        raise DomainError(
            "CSV needs a name column and a mobile/phone column. Header row example: name,mobile,email,location",
            code="validation_error", status_code=422,
        )

    svc = CandidateService(session, principal.user_id)
    # Digits-only so "+918965823672" and a bare "8965823672" count as the same person.
    existing_phones = {
        _digits(p)
        for p in session.scalars(
            select(Candidate.phone).join(JobCandidate, JobCandidate.candidate_id == Candidate.id).where(JobCandidate.job_id == job_id)
        ).all()
        if _digits(p)
    }

    added = 0
    errors: list[CsvRowError] = []
    seen_phones: set[str] = set()
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        if i - 1 > CSV_MAX_ROWS:
            errors.append(CsvRowError(row=i, reason=f"Stopped: over the {CSV_MAX_ROWS}-row limit."))
            break
        name = _pick(row, header_map, _CSV_NAME_KEYS)
        phone_raw = _pick(row, header_map, _CSV_PHONE_KEYS)
        if not name and not phone_raw:
            continue  # silently skip fully blank lines
        if not name:
            errors.append(CsvRowError(row=i, reason="Missing name."))
            continue
        if not phone_raw:
            errors.append(CsvRowError(row=i, reason="Missing mobile."))
            continue
        phone = _to_e164(phone_raw, _pick(row, header_map, _CSV_CC_KEYS))
        if not phone:
            errors.append(CsvRowError(row=i, reason=f"Missing country code for '{phone_raw}' — add a country_code column or a + prefix."))
            continue
        pd = _digits(phone)
        if pd in existing_phones or pd in seen_phones:
            errors.append(CsvRowError(row=i, reason=f"Duplicate mobile ({phone}) — skipped."))
            continue
        seen_phones.add(pd)
        svc.import_candidate(
            job, full_name=name, phone=phone,
            email=_pick(row, header_map, _CSV_EMAIL_KEYS) or None,
            location=_pick(row, header_map, _CSV_LOCATION_KEYS) or None,
            source="csv",
        )
        added += 1

    if added:
        write_audit(
            session, org_id=job.org_id, actor_user_id=principal.user_id,
            action="job_candidate.imported_csv", entity_type="job", entity_id=job_id,
            meta={"added": added, "skipped": len(errors)},
        )
    return CsvImportResult(added=added, skipped=len(errors), errors=errors[:50])


def _summary(c: Candidate) -> CandidateSummary:
    return CandidateSummary(
        id=c.id, full_name=c.full_name, phone=c.phone, email=c.email, location=c.location
    )


@router.patch("/job-candidates/{jc_id}", response_model=CandidateSummary)
def update_candidate(jc_id: UUID, body: CandidateUpdateIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Edit a candidate's profile (name / phone / email / location). Only provided fields change;
    a field sent as empty string clears it. Phone should be E.164 so calls can be placed."""
    jc = _jc_or_404(session, principal, jc_id)
    candidate = session.get(Candidate, jc.candidate_id)
    fields = body.model_dump(exclude_unset=True)
    if "full_name" in fields:
        name = (fields["full_name"] or "").strip()
        if not name:
            raise DomainError("Full name cannot be empty.", code="validation_error", status_code=422)
        candidate.full_name = name
    for attr in ("phone", "email", "location"):
        if attr in fields:
            setattr(candidate, attr, (fields[attr] or "").strip() or None)
    session.flush()
    write_audit(
        session, org_id=jc_job_org(session, jc), actor_user_id=principal.user_id,
        action="candidate.updated", entity_type="candidate", entity_id=candidate.id,
        meta={"job_candidate_id": str(jc.id), "fields": sorted(fields.keys())},
    )
    return _summary(candidate)


def jc_job_org(session: Session, jc: JobCandidate):
    job = session.get(Job, jc.job_id)
    return job.org_id


def _stage_names(session: Session, stage_ids: set[UUID]) -> dict[UUID, str]:
    """Resolve stage id → name for the stages referenced by a candidate's runs/current stage."""
    if not stage_ids:
        return {}
    rows = session.scalars(
        select(JobWorkflowStage).where(JobWorkflowStage.id.in_(stage_ids))
    ).all()
    return {s.id: s.name for s in rows}


@router.get("/jobs/{job_id}/pipeline", response_model=PipelinePage)
def pipeline_page(
    job_id: UUID,
    stage: str | None = None,   # a stage UUID, "new" (no stage yet), or None/"all"
    state: str | None = None,   # pipeline_state filter, e.g. REJECTED
    q: str | None = None,       # search name / phone / email
    page: int = 1,
    page_size: int = 25,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    """One page of a job's candidates, filtered by stage/state/search. Server-side pagination
    so a funnel with hundreds or thousands of candidates loads a bounded slice, not everything."""
    _job_or_404(session, principal, job_id)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    conds = [JobCandidate.job_id == job_id]
    if stage and stage not in ("all", ""):
        if stage == "new":
            conds.append(JobCandidate.current_stage_id.is_(None))
        else:
            try:
                conds.append(JobCandidate.current_stage_id == UUID(stage))
            except ValueError:
                raise DomainError("Invalid stage filter.", code="validation_error", status_code=422)
    if state:
        conds.append(JobCandidate.pipeline_state == state)

    base = select(JobCandidate).where(*conds)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.join(Candidate, Candidate.id == JobCandidate.candidate_id).where(
            Candidate.full_name.ilike(like) | Candidate.phone.ilike(like) | Candidate.email.ilike(like)
        )

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    jcs = session.scalars(
        base.order_by(JobCandidate.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    names = _stage_names(session, {jc.current_stage_id for jc in jcs if jc.current_stage_id})
    items = [
        JobCandidateListItem(
            id=jc.id, candidate=_summary(session.get(Candidate, jc.candidate_id)),
            current_stage_id=jc.current_stage_id,
            current_stage_name=names.get(jc.current_stage_id) if jc.current_stage_id else None,
            pipeline_state=jc.pipeline_state,
        )
        for jc in jcs
    ]
    return PipelinePage(items=items, total=total, page=page, page_size=page_size)


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


@router.delete("/job-candidates/{jc_id}", status_code=204)
def delete_job_candidate(jc_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Remove a candidate's participation in a job (and its cascaded stage runs, facts, and
    calls). The candidate person record is org-scoped and is not deleted."""
    jc = _jc_or_404(session, principal, jc_id)
    job = session.get(Job, jc.job_id)
    write_audit(
        session, org_id=job.org_id, actor_user_id=principal.user_id,
        action="job_candidate.deleted", entity_type="job_candidate", entity_id=jc.id,
        meta={"job_id": str(jc.job_id), "candidate_id": str(jc.candidate_id)},
    )
    session.delete(jc)
    session.flush()
    return None


@router.get("/candidates", response_model=list[OrgCandidateListItem])
def list_all_candidates(session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Org-wide candidate directory: every candidate participation across all jobs, newest
    first, with the person, their job, current stage, and pipeline state. A person appearing
    in multiple jobs appears once per job."""
    rows = session.execute(
        select(JobCandidate, Job.title, Candidate)
        .join(Job, Job.id == JobCandidate.job_id)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .where(Job.org_id == principal.org_id)
        .order_by(JobCandidate.created_at.desc())
    ).all()
    names = _stage_names(session, {jc.current_stage_id for (jc, _t, _c) in rows if jc.current_stage_id})
    return [
        OrgCandidateListItem(
            id=jc.id,
            candidate=_summary(candidate),
            job_id=jc.job_id,
            job_title=title,
            current_stage_name=names.get(jc.current_stage_id) if jc.current_stage_id else None,
            pipeline_state=jc.pipeline_state,
            created_at=jc.created_at,
        )
        for (jc, title, candidate) in rows
    ]


@router.post("/job-candidates/{jc_id}/decision", response_model=DecisionOut, status_code=201)
def decide(jc_id: UUID, body: DecisionIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Recruiter decision on a candidate awaiting review: advance (pass) or reject.

    Operates on the current stage's run, which must be in NEEDS_REVIEW. PASS advances the
    candidate to the next stage (or completes the pipeline); REJECT stops them. Audited."""
    jc = _jc_or_404(session, principal, jc_id)
    outcome_map = {"pass": StageOutcome.PASS, "reject": StageOutcome.REJECT}
    outcome = outcome_map.get(body.outcome.lower())
    if outcome is None:
        raise DomainError("outcome must be 'pass' or 'reject'.", code="validation_error", status_code=422)
    if jc.current_stage_id is None:
        raise DomainError("Candidate has no current stage.", code="conflict", status_code=409)
    run = session.scalars(
        select(CandidateStageRun)
        .where(
            CandidateStageRun.job_candidate_id == jc.id,
            CandidateStageRun.job_workflow_stage_id == jc.current_stage_id,
        )
        .order_by(CandidateStageRun.created_at.desc())
        .limit(1)
    ).first()
    if run is None or run.status != StageRunState.NEEDS_REVIEW.value:
        raise DomainError(
            "Candidate is not awaiting a decision (current stage run must be NEEDS_REVIEW).",
            code="conflict", status_code=409,
        )
    next_run = WorkflowExecutionService(session, principal.user_id).complete_with_outcome(
        run, outcome, reason=body.reason
    )
    session.flush()
    session.refresh(jc)
    next_stage = session.get(JobWorkflowStage, jc.current_stage_id) if jc.current_stage_id else None
    return DecisionOut(
        job_candidate_id=jc.id,
        outcome=body.outcome.lower(),
        pipeline_state=jc.pipeline_state,
        current_stage_id=jc.current_stage_id,
        current_stage_name=next_stage.name if next_stage else None,
        advanced=next_run is not None,
    )


@router.post("/job-candidates/{jc_id}/enrich", response_model=EnrichOut, status_code=201)
def enrich(jc_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Reveal a sourced candidate's contact details so an outreach call can be placed.

    Uses the provider the candidate was sourced from, degrading to a flagged sample contact
    when that provider can't enrich synchronously (Apollo async/plan gate). Idempotent."""
    jc = _jc_or_404(session, principal, jc_id)
    try:
        outcome = SourcingService(session, principal.user_id).enrich(jc)
    except SourcingProviderError as exc:
        raise DomainError(str(exc), code="provider_unavailable", status_code=502)
    session.refresh(jc)
    return EnrichOut(
        phone=outcome.phone, email=outcome.email, provider=outcome.provider,
        requested_provider=outcome.requested_provider, is_sample=outcome.is_sample,
        already_had_contact=outcome.already_had_contact, notice=outcome.notice,
        pipeline_state=jc.pipeline_state,
    )


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
