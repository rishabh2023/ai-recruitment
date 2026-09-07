"""Launch an AI stage for a job candidate (Phase 3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import BulkLaunchOut, BulkLaunchResultItem, CallStatusOut, LaunchOut
from app.config import settings
from app.db.session import get_session
from app.integrations.hunar import HunarClient, HunarError
from app.modules.candidates.models import Candidate, CandidateStageRun, JobCandidate
from app.modules.interviews.models import Call
from app.modules.interviews.service import InterviewLaunchError, InterviewService
from app.modules.jobs.models import Job
from app.modules.webhooks.service import WebhookService
from app.modules.workflows.models import JobWorkflowStage
from app.workflow_execution import StageRunState, WorkflowExecutionService

router = APIRouter(tags=["interviews"])

# A retry is allowed when the previous attempt ended terminally without connecting.
_RETRYABLE_RUN_STATES = {StageRunState.FAILED.value, StageRunState.CANCELLED.value}


def _live_calls_ready(session: Session | None = None, org_id=None) -> bool:
    """Live dialing needs a Hunar key AND the calling switch on — enabled either by the org's
    Settings toggle or the process-level flag."""
    if not settings.hunar_api_key:
        return False
    if session is not None and org_id is not None:
        from app.modules.organizations.settings_service import SettingsService

        return SettingsService(session).live_calls_enabled(org_id)
    return settings.hunar_live_calls_enabled


# A candidate's current-stage run is launchable when it has not yet been dialed to a result:
# fresh (PENDING/READY) or a retryable terminal (FAILED/CANCELLED, relaunched as a new run).
# Every other state — SCHEDULED/IN_PROGRESS/AWAITING_RESULT (a call is live), NEEDS_REVIEW
# (already screened, awaiting the recruiter), COMPLETED, or BLOCKED — is skipped by bulk launch
# so nobody who is already handled gets re-dialed.
_LAUNCHABLE_RUN_STATES = {
    StageRunState.PENDING.value,
    StageRunState.READY.value,
    StageRunState.FAILED.value,
    StageRunState.CANCELLED.value,
}

# Why a candidate is skipped by "launch all", keyed by their current run state (or None).
_SKIP_REASONS = {
    None: "no stage run yet",
    StageRunState.SCHEDULED.value: "a call is already scheduled",
    StageRunState.IN_PROGRESS.value: "a call is already in progress",
    StageRunState.AWAITING_RESULT.value: "already called — awaiting the result",
    StageRunState.NEEDS_REVIEW.value: "already screened — awaiting your review",
    StageRunState.COMPLETED.value: "already completed",
    StageRunState.BLOCKED.value: "blocked by a prior stage",
}


def _latest_run(session: Session, jc_id: UUID, stage_id: UUID) -> CandidateStageRun | None:
    return session.scalars(
        select(CandidateStageRun)
        .where(
            CandidateStageRun.job_candidate_id == jc_id,
            CandidateStageRun.job_workflow_stage_id == stage_id,
        )
        .order_by(CandidateStageRun.created_at.desc())
        .limit(1)
    ).first()


def _launch_current_stage(
    session: Session, principal: Principal, jc: JobCandidate, job: Job
) -> tuple[Call, dict, bool]:
    """Launch the candidate's CURRENT stage as an AI interview and (when live) dispatch it.

    Assumes `jc`/`job` are already validated (belongs to the org, not archived). Raises
    `DomainError` (409) for no current stage / no stage run, or `InterviewLaunchError` for a
    non-AI stage / missing phone. Returns (call, hunar_payload, dispatched).
    """
    if jc.current_stage_id is None:
        raise DomainError("Candidate has no current stage.", code="conflict", status_code=409)
    stage = session.get(JobWorkflowStage, jc.current_stage_id)
    run = _latest_run(session, jc.id, stage.id)
    if run is None:
        raise DomainError("No stage run to launch.", code="conflict", status_code=409)
    # Retry: if the last attempt ended terminally (e.g. candidate didn't answer), start a
    # fresh run for this stage rather than reusing the terminal one.
    if run.status in _RETRYABLE_RUN_STATES:
        run = WorkflowExecutionService(session, principal.user_id).create_stage_run(
            jc, stage, initial=StageRunState.READY
        )
    call, payload = InterviewService(session, principal.user_id).launch_ai_stage(jc, stage, run)

    # Flow B: launching the outreach call marks a sourced candidate as CONTACTED (audited).
    if jc.pipeline_state in ("SOURCED", "OUTREACH_PENDING"):
        from app.modules.audit.log import write_audit

        jc.pipeline_state = "CONTACTED"
        write_audit(
            session, org_id=job.org_id, actor_user_id=principal.user_id,
            action="sourcing.outreach_launched", entity_type="job_candidate",
            entity_id=jc.id, to_state="CONTACTED",
        )

    dispatched = False
    if _live_calls_ready(session, job.org_id):
        # Persist the intent (QUEUED call + AWAITING_RESULT run) BEFORE dispatching, so the
        # task (eager or a real worker) sees a committed row. Then enqueue the real call.
        call_id = call.id
        session.commit()
        from app.tasks import dispatch_hunar_call  # imported here to avoid import at app start

        dispatch_hunar_call.delay(str(call_id))
        dispatched = True
        session.refresh(call)  # eager task updated status/hunar_call_id in its own session
    return call, payload, dispatched


@router.post("/job-candidates/{jc_id}/launch", response_model=LaunchOut, status_code=201)
def launch(jc_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    jc = session.get(JobCandidate, jc_id)
    if jc is None:
        raise DomainError("Job candidate not found.", code="not_found", status_code=404)
    job = session.get(Job, jc.job_id)
    if job.org_id != principal.org_id:
        raise DomainError("Job candidate not found.", code="not_found", status_code=404)
    if job.status == "archived":
        raise DomainError(
            "This role is inactive. Reactivate it before launching outreach or interviews.",
            code="conflict",
            status_code=409,
        )
    try:
        call, payload, dispatched = _launch_current_stage(session, principal, jc, job)
    except InterviewLaunchError as exc:
        raise DomainError(str(exc), code="conflict", status_code=409)

    return LaunchOut(
        call_id=call.id,
        normalized_status=call.normalized_status,
        hunar_payload=payload,
        dispatched=dispatched,
        hunar_call_id=call.hunar_call_id,
    )


@router.post("/jobs/{job_id}/stages/{stage_id}/launch-all", response_model=BulkLaunchOut, status_code=201)
def launch_stage_all(
    job_id: UUID,
    stage_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    """Launch the AI interview for EVERY eligible candidate currently in `stage_id`.

    Eligible = candidate's current stage is this stage, not rejected, and their latest run has
    not been dialed to a result (see `_LAUNCHABLE_RUN_STATES`). Already-handled candidates
    (call in progress, awaiting result, needs review, completed) and rejected ones are skipped
    — never re-dialed. One candidate failing to launch does not stop the rest.
    """
    job = session.get(Job, job_id)
    if job is None or job.org_id != principal.org_id:
        raise DomainError("Job not found.", code="not_found", status_code=404)
    if job.status == "archived":
        raise DomainError(
            "This role is inactive. Reactivate it before launching interviews.",
            code="conflict", status_code=409,
        )
    stage = session.get(JobWorkflowStage, stage_id)
    if stage is None:
        raise DomainError("Stage not found.", code="not_found", status_code=404)
    if stage.execution_type != "ai":
        raise DomainError(
            f"Stage '{stage.name}' is not an AI calling stage.", code="conflict", status_code=409
        )

    jcs = session.scalars(
        select(JobCandidate)
        .where(JobCandidate.job_id == job_id, JobCandidate.current_stage_id == stage_id)
        .order_by(JobCandidate.created_at.asc())
    ).all()

    results: list[BulkLaunchResultItem] = []
    launched = skipped = failed = 0
    for jc in jcs:
        candidate = session.get(Candidate, jc.candidate_id)
        name = candidate.full_name if candidate else None

        if jc.pipeline_state == "REJECTED":
            skipped += 1
            results.append(BulkLaunchResultItem(job_candidate_id=jc.id, name=name, outcome="skipped", reason="already rejected"))
            continue

        run = _latest_run(session, jc.id, stage_id)
        status = run.status if run else None
        if status not in _LAUNCHABLE_RUN_STATES:
            skipped += 1
            reason = _SKIP_REASONS.get(status, f"not launchable (state {status})")
            results.append(BulkLaunchResultItem(job_candidate_id=jc.id, name=name, outcome="skipped", reason=reason))
            continue

        try:
            call, _payload, dispatched = _launch_current_stage(session, principal, jc, job)
        except (DomainError, InterviewLaunchError) as exc:
            session.rollback()
            failed += 1
            results.append(BulkLaunchResultItem(job_candidate_id=jc.id, name=name, outcome="failed", reason=str(exc)))
            continue

        # Persist each success independently so one later failure's rollback can't discard it.
        # (In live mode the helper already committed; this is a harmless no-op there.)
        session.commit()
        launched += 1
        results.append(BulkLaunchResultItem(
            job_candidate_id=jc.id, name=name, outcome="launched", call_id=call.id, dispatched=dispatched
        ))

    return BulkLaunchOut(stage_id=stage_id, launched=launched, skipped=skipped, failed=failed, results=results)


@router.post("/calls/{call_id}/sync", response_model=CallStatusOut)
def sync_call_status(call_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Pull the latest status/result for a call from Hunar and apply it (dev affordance for
    when no public webhook URL is registered). Org-scoped."""
    call = session.get(Call, call_id)
    if call is None:
        raise DomainError("Call not found.", code="not_found", status_code=404)
    jc = session.get(JobCandidate, call.job_candidate_id)
    job = session.get(Job, jc.job_id) if jc else None
    if job is None or job.org_id != principal.org_id:
        raise DomainError("Call not found.", code="not_found", status_code=404)
    if not _live_calls_ready(session, job.org_id):
        raise DomainError("Live Hunar calls are not enabled.", code="conflict", status_code=409)
    if not call.hunar_call_id:
        raise DomainError("This call has no Hunar call id yet.", code="conflict", status_code=409)
    try:
        snapshot = HunarClient.from_settings(settings).get_call(call.hunar_call_id)
    except HunarError as exc:
        raise DomainError(f"Could not fetch call status from Hunar: {exc}", code="bad_gateway", status_code=502)
    WebhookService(session, principal.user_id).sync_call(call, snapshot)
    return CallStatusOut(
        call_id=call.id, normalized_status=call.normalized_status,
        vendor_status=call.vendor_status, hunar_call_id=call.hunar_call_id,
    )
