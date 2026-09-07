"""HunarDispatchService: real-call wiring with a fake client (no network).

Covers the success path (call updated, required custom vars filled), the vendor-failure path
(call + run marked FAILED with an audit record), and the missing-agent guard.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.integrations.hunar import HunarError
from app.integrations.llm import ExtractedJob
from app.modules.audit.models import AuditEvent
from app.modules.candidates.models import CandidateStageRun
from app.modules.candidates.service import CandidateService
from app.modules.interviews.dispatch import HunarDispatchError, HunarDispatchService
from app.modules.interviews.service import InterviewService
from app.modules.jobs.models import Job
from app.modules.jobs.service import JobService
from app.modules.organizations.models import Organization, User
from app.modules.workflows.models import HunarAgentConfig, JobWorkflowStage
from app.modules.workflows.service import WorkflowService
from app.workflow_execution import StageRunState


class FakeHunar:
    def __init__(self, *, required=None, create_resp=None, raise_on_create=None, can_provision=True):
        self._required = required or []
        self._create_resp = create_resp or {"id": "hunar-xyz", "status": "NOT_STARTED"}
        self._raise = raise_on_create
        self._can_provision = can_provision
        self.last_payload = None

    def get_agent(self, agent_id):
        return {"required_variables": self._required}

    def list_agents(self, *, page: int = 1):
        # No pre-existing account agents → provisioning would create one, unless disabled.
        if not self._can_provision:
            raise HunarError("agent listing unavailable", status_code=503)
        return {"results": []}

    def create_agent(self, payload):
        if not self._can_provision:
            raise HunarError("agent creation unavailable", status_code=503)
        return {"id": "hunar-agent-new", "status": "ACTIVE"}

    def create_call(self, payload):
        self.last_payload = payload
        if self._raise:
            raise self._raise
        return self._create_resp


def _setup(session, *, with_agent="agent-1"):
    org = Organization(name="Acme"); session.add(org); session.flush()
    user = User(org_id=org.id, email="r@acme.com", role="recruiter"); session.add(user); session.flush()
    jobs = JobService(session, actor_user_id=user.id)
    wf = WorkflowService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, "Backend Engineer")
    jv = jobs.add_job_version(job, "Backend Engineer\nPython, FastAPI")
    jobs.confirm_job_version(jv)
    version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
    wf.approve_workflow_version(version, approver_user_id=user.id)
    jobs.activate_job(job)
    stages = session.scalars(
        select(JobWorkflowStage).where(JobWorkflowStage.job_workflow_version_id == version.id)
        .order_by(JobWorkflowStage.stage_order.asc())
    ).all()
    stage = stages[0]
    if with_agent:
        session.add(HunarAgentConfig(job_workflow_stage_id=stage.id, hunar_agent_id=with_agent))
        session.flush()
    jc = CandidateService(session, user.id).import_candidate(
        job, full_name="Asha", phone="+919999999999", location="Bengaluru",
    )
    run = session.scalars(
        select(CandidateStageRun).where(
            CandidateStageRun.job_candidate_id == jc.id,
            CandidateStageRun.job_workflow_stage_id == stage.id,
        )
    ).first()
    call, _ = InterviewService(session, user.id).launch_ai_stage(jc, stage, run)
    return org, user, jc, stage, run, call


def test_dispatch_registers_webhook_callbacks_when_public_url_set(session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "public_base_url", "https://example.test", raising=False)
    org, user, jc, stage, run, call = _setup(session)
    fake = FakeHunar()
    HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)
    cb = fake.last_payload["callback_config"]
    url = "https://example.test/webhooks/hunar"
    assert cb["call_result_callback_url"] == url
    assert cb["call_status_callback_url"] == url
    assert cb["call_recording_callback_url"] == url
    assert cb["call_summary_callback_url"] == url


def test_dispatch_applies_calling_policy(session):
    from datetime import time

    from app.modules.workflows.models import CallingPolicy

    org, user, jc, stage, run, call = _setup(session)
    session.add(CallingPolicy(
        org_id=org.id, job_id=jc.job_id, allowed_days=["MON", "TUE", "WED"],
        earliest_call_time=time(9, 0), last_call_time=time(18, 0), timezone="Asia/Kolkata",
        max_attempts=3, retry_interval_hours=6,
    ))
    session.flush()
    fake = FakeHunar()
    HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)
    p = fake.last_payload
    assert p["guardrails"]["allowed_days"] == ["MON", "TUE", "WED"]
    assert p["guardrails"]["earliest_call_time"] == "09:00"
    assert p["retry_config"] == {"max_retry_count": 2, "retry_interval_hours": 6}


def test_dispatch_omits_callbacks_when_no_public_url(session):
    org, user, jc, stage, run, call = _setup(session)
    fake = FakeHunar()
    HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)
    assert "callback_config" not in fake.last_payload  # nothing to register


def test_dispatch_success_updates_call_and_fills_required_vars(session):
    org, user, jc, stage, run, call = _setup(session)
    fake = FakeHunar(required=["candidate_name", "job_role", "company", "location", "hobby"])
    HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)

    assert call.hunar_call_id == "hunar-xyz"
    assert call.normalized_status == "QUEUED"  # NOT_STARTED → QUEUED
    cd = fake.last_payload["custom_data"]
    assert cd["candidate_name"] == "Asha"
    assert cd["job_role"] == "Backend Engineer"
    # Common aliases are sent so an agent scripted with {role}/{persona_name}/{callee_name} etc.
    # is satisfied whichever naming it uses (Hunar 422s on a script placeholder we don't send).
    assert cd["role"] == "Backend Engineer"
    assert cd["callee_name"] == "Asha"
    assert cd["persona_name"]  # non-empty interviewer name
    assert cd["company"] == "Acme"
    assert cd["location"] == "Bengaluru"
    # A required-but-unknown variable is filled with a neutral placeholder (never empty), so
    # Hunar does not 422 on it — the call goes through regardless of missing optional details.
    assert cd["hobby"] == "Not provided"
    assert fake.last_payload["mobile_number"] == "+919999999999"


def test_missing_location_does_not_send_empty_required_var(session):
    org, user, jc, stage, run, call = _setup(session)
    # Candidate has no location on file, and the agent requires it → must be filled, not empty.
    from app.modules.candidates.models import Candidate
    cand = session.get(Candidate, jc.candidate_id)
    cand.location = None
    session.flush()
    fake = FakeHunar(required=["candidate_name", "job_role", "company", "location", "email"])
    HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)
    cd = fake.last_payload["custom_data"]
    assert cd["location"] == "Not provided"
    assert cd["email"] == "Not provided"
    assert call.hunar_call_id == "hunar-xyz"  # call still placed


def test_dispatch_failure_marks_call_and_run_failed(session):
    org, user, jc, stage, run, call = _setup(session)
    fake = FakeHunar(raise_on_create=HunarError("rejected", status_code=422, body={"message": "bad"}))
    with pytest.raises(HunarError):
        HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)

    assert call.normalized_status == "FAILED"
    assert run.status == StageRunState.FAILED.value
    actions = [a.action for a in session.scalars(select(AuditEvent)).all()]
    assert "interview.dispatch_failed" in actions


def test_dispatch_without_agent_fails_cleanly(session):
    org, user, jc, stage, run, call = _setup(session, with_agent=None)  # no config, no default
    # can_provision=False → the lazy safety net can neither match nor create an agent, so with no
    # default configured the dispatch must fail cleanly rather than dial a wrong/absent agent.
    with pytest.raises(HunarDispatchError):
        HunarDispatchService(
            session, client=FakeHunar(can_provision=False), actor_user_id=user.id
        ).dispatch(call.id)
    assert call.normalized_status == "FAILED"
    assert run.status == StageRunState.FAILED.value


def test_dispatch_is_idempotent_once_sent(session):
    org, user, jc, stage, run, call = _setup(session)
    fake = FakeHunar()
    svc = HunarDispatchService(session, client=fake, actor_user_id=user.id)
    svc.dispatch(call.id)
    fake.last_payload = None
    svc.dispatch(call.id)  # already has hunar_call_id → no second POST
    assert fake.last_payload is None


def test_dispatch_cancels_queued_call_when_role_becomes_inactive(session):
    org, user, jc, stage, run, call = _setup(session)
    JobService(session, user.id).archive_job(session.get(Job, jc.job_id))
    fake = FakeHunar()

    with pytest.raises(HunarDispatchError, match="inactive"):
        HunarDispatchService(session, client=fake, actor_user_id=user.id).dispatch(call.id)

    assert fake.last_payload is None
    assert call.normalized_status == "CANCELLED"
    assert run.status == StageRunState.CANCELLED.value
    actions = [a.action for a in session.scalars(select(AuditEvent)).all()]
    assert "interview.dispatch_cancelled_inactive_job" in actions


# --- rejected / unanswered call handling ---
def test_no_answer_marks_run_failed_with_reason(session):
    from app.modules.audit.models import AuditEvent
    from app.modules.webhooks.service import WebhookService

    org, user, jc, stage, run, call = _setup(session)
    HunarDispatchService(session, client=FakeHunar(), actor_user_id=user.id).dispatch(call.id)
    # Candidate rejected → Hunar reports NOT_CONNECTED, no retries left.
    WebhookService(session, user.id).sync_call(call, {"id": call.hunar_call_id, "status": "NOT_CONNECTED"})

    assert call.normalized_status == "NO_ANSWER"
    assert run.status == StageRunState.FAILED.value  # not stuck in AWAITING_RESULT
    actions = [a.action for a in session.scalars(select(AuditEvent)).all()]
    assert "interview.call_not_connected" in actions


def test_retry_scheduled_keeps_run_awaiting(session):
    from app.modules.webhooks.service import WebhookService

    org, user, jc, stage, run, call = _setup(session)
    HunarDispatchService(session, client=FakeHunar(), actor_user_id=user.id).dispatch(call.id)
    # NOT_CONNECTED but retries remain → RETRY_SCHEDULED; run keeps waiting.
    WebhookService(session, user.id).sync_call(
        call, {"id": call.hunar_call_id, "status": "NOT_CONNECTED", "retries_left": 2}
    )
    assert call.normalized_status == "RETRY_SCHEDULED"
    assert run.status == StageRunState.AWAITING_RESULT.value


def test_retry_after_failure_creates_fresh_run(session):
    from app.modules.webhooks.service import WebhookService
    from app.workflow_execution import WorkflowExecutionService

    org, user, jc, stage, run, call = _setup(session)
    HunarDispatchService(session, client=FakeHunar(), actor_user_id=user.id).dispatch(call.id)
    WebhookService(session, user.id).sync_call(call, {"id": call.hunar_call_id, "status": "NOT_CONNECTED"})
    assert run.status == StageRunState.FAILED.value

    # Retry: fresh run for the same stage, then launch again.
    new_run = WorkflowExecutionService(session, user.id).create_stage_run(
        jc, stage, initial=StageRunState.READY
    )
    call2, _ = InterviewService(session, user.id).launch_ai_stage(jc, stage, new_run)
    assert new_run.id != run.id
    assert new_run.status == StageRunState.AWAITING_RESULT.value
    assert call2.id != call.id
