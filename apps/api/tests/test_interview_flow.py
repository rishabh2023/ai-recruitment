"""Phase 3: existing candidate → launch AI stage → webhook → result → review (DB-backed)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.integrations.llm import ExtractedJob
from app.modules.candidates.models import CandidateFact, CandidateStageRun
from app.modules.candidates.service import CandidateService
from app.modules.interviews.models import Call, StageResult
from app.modules.interviews.service import InterviewLaunchError, InterviewService
from app.modules.jobs.service import JobService
from app.modules.organizations.models import Organization, User
from app.modules.webhooks.models import WebhookEvent
from app.modules.webhooks.service import WebhookService
from app.modules.workflows.models import JobWorkflowStage
from app.modules.workflows.service import WorkflowService
from app.workflow_execution import StageOutcome, StageRunState, WorkflowExecutionService

ENG_JD = "Backend Engineer\nPython, FastAPI, system design."


def _active_job_with_workflow(session):
    org = Organization(name="Acme"); session.add(org); session.flush()
    user = User(org_id=org.id, email="r@acme.com", role="recruiter"); session.add(user); session.flush()
    jobs = JobService(session, actor_user_id=user.id)
    wf = WorkflowService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, "Backend Engineer")
    jv = jobs.add_job_version(job, ENG_JD)
    jobs.confirm_job_version(jv)
    version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
    wf.approve_workflow_version(version, approver_user_id=user.id)
    jobs.activate_job(job)
    stages = session.scalars(
        select(JobWorkflowStage)
        .where(JobWorkflowStage.job_workflow_version_id == version.id)
        .order_by(JobWorkflowStage.stage_order.asc())
    ).all()
    return org, user, job, stages


def test_import_candidate_creates_run_and_facts(session):
    org, user, job, stages = _active_job_with_workflow(session)
    cands = CandidateService(session, actor_user_id=user.id)
    jc = cands.import_candidate(
        job, full_name="Asha", phone="+919999999999",
        known_facts={"interest": "yes", "location": "Bengaluru"},
    )
    assert jc.current_stage_id == stages[0].id
    run = session.scalars(
        select(CandidateStageRun).where(CandidateStageRun.job_candidate_id == jc.id)
    ).first()
    assert run.status == StageRunState.READY.value
    keys = cands.known_field_keys(jc)
    assert {"interest", "location"} <= keys


def test_start_at_later_stage_is_audited(session):
    org, user, job, stages = _active_job_with_workflow(session)
    from app.modules.audit.models import AuditEvent

    cands = CandidateService(session, actor_user_id=user.id)
    jc = cands.import_candidate(job, full_name="Bo", phone="+911111111111", starting_stage=stages[1])
    assert jc.current_stage_id == stages[1].id
    actions = set(session.scalars(select(AuditEvent.action).where(AuditEvent.org_id == org.id)).all())
    assert "candidate.started_at_later_stage" in actions


def test_launch_requires_phone(session):
    org, user, job, stages = _active_job_with_workflow(session)
    cands = CandidateService(session, actor_user_id=user.id)
    jc = cands.import_candidate(job, full_name="NoPhone")
    run = session.scalars(select(CandidateStageRun).where(CandidateStageRun.job_candidate_id == jc.id)).first()
    with pytest.raises(InterviewLaunchError):
        InterviewService(session, user.id).launch_ai_stage(jc, stages[0], run)


def test_launch_builds_payload_and_awaits_result(session):
    org, user, job, stages = _active_job_with_workflow(session)
    cands = CandidateService(session, actor_user_id=user.id)
    jc = cands.import_candidate(
        job, full_name="Asha", phone="+919999999999", known_facts={"location": "Bengaluru"}
    )
    run = session.scalars(select(CandidateStageRun).where(CandidateStageRun.job_candidate_id == jc.id)).first()
    call, payload = InterviewService(session, user.id).launch_ai_stage(jc, stages[0], run)
    assert call.normalized_status == "QUEUED"
    assert run.status == StageRunState.AWAITING_RESULT.value
    # screening asks for interest/ctc/etc.; location already known so it's excluded.
    collect = payload["custom_data"]["collect"].split(",")
    assert "location" not in collect and "interest" in collect
    assert payload["mobile_number"] == "+919999999999"


def test_webhook_result_flow_and_idempotency(session):
    org, user, job, stages = _active_job_with_workflow(session)
    cands = CandidateService(session, actor_user_id=user.id)
    jc = cands.import_candidate(job, full_name="Asha", phone="+919999999999")
    run = session.scalars(select(CandidateStageRun).where(CandidateStageRun.job_candidate_id == jc.id)).first()
    call, payload = InterviewService(session, user.id).launch_ai_stage(jc, stages[0], run)

    event = {
        "event": "call_result_done",
        "id": "hunar-call-1",
        "request_id": call.request_id,
        "status": "COMPLETED",
        "result": {"interested": "yes", "expected_ctc": "24 LPA", "notice_period": "30 days"},
        "recording_url": "https://rec/1",
    }
    hooks = WebhookService(session, user.id)
    ev1 = hooks.handle_hunar_event(event)
    assert ev1.processed_at is not None

    session.refresh(call)
    assert call.normalized_status == "COMPLETED" and call.hunar_call_id == "hunar-call-1"
    session.refresh(run)
    assert run.status == StageRunState.NEEDS_REVIEW.value
    sr = session.scalars(select(StageResult).where(StageResult.candidate_stage_run_id == run.id)).all()
    assert len(sr) == 1 and sr[0].recording_url == "https://rec/1"
    facts = {f.field_key for f in session.scalars(select(CandidateFact).where(CandidateFact.job_candidate_id == jc.id))}
    assert {"expected_ctc", "notice_period"} <= facts

    # Duplicate delivery: no new event, no new StageResult, no double-advance.
    ev2 = hooks.handle_hunar_event(event)
    assert ev2.id == ev1.id
    assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 1
    assert session.scalar(select(func.count()).select_from(StageResult).where(StageResult.candidate_stage_run_id == run.id)) == 1

    # Recruiter reviews → PASS advances to the next stage.
    nxt = WorkflowExecutionService(session, user.id).complete_with_outcome(run, StageOutcome.PASS)
    assert nxt is not None and nxt.job_workflow_stage_id == stages[1].id
