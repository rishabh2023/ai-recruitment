"""Bulk 'launch AI stage for all candidates' — eligibility + skip rules (network-free).

Live Hunar dialing is off in tests (conftest blanks the key), so launches take the non-live
path: a QUEUED call is created but nothing is dialed. We assert WHICH candidates get launched
vs skipped, which is the whole point of the feature.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.integrations.llm import ExtractedJob
from app.main import app
from app.modules.candidates.models import CandidateStageRun
from app.modules.candidates.service import CandidateService
from app.modules.jobs.service import JobService
from app.modules.workflows.models import JobWorkflowStage
from app.modules.workflows.service import WorkflowService
from app.workflow_execution import StageRunState, WorkflowExecutionService


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE webhook_events RESTART IDENTITY CASCADE"))


def _signup(client, email="admin@acme.test"):
    r = client.post("/auth/signup", json={"name": "Admin", "email": email, "password": "pw-123456", "org_name": "Acme"})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _build_pipeline(org_id, user_id):
    """Create an active job with an AI first stage and three candidates in that stage:
    one fresh (launchable), one already awaiting a result, one rejected. Returns ids."""
    s = Session(bind=engine, expire_on_commit=False)
    try:
        import uuid
        jobs = JobService(s, actor_user_id=uuid.UUID(user_id))
        wf = WorkflowService(s, actor_user_id=uuid.UUID(user_id))
        job = jobs.create_job(uuid.UUID(org_id), "Backend Engineer")
        jv = jobs.add_job_version(job, "Backend Engineer\nPython, FastAPI, system design.")
        jobs.confirm_job_version(jv)
        version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
        wf.approve_workflow_version(version, approver_user_id=uuid.UUID(user_id))
        jobs.activate_job(job)
        stages = s.scalars(
            select(JobWorkflowStage)
            .where(JobWorkflowStage.job_workflow_version_id == version.id)
            .order_by(JobWorkflowStage.stage_order.asc())
        ).all()
        ai_stage = next((st for st in stages if st.execution_type == "ai"), None)
        assert ai_stage is not None, "expected an AI stage in the drafted workflow"

        cands = CandidateService(s, actor_user_id=uuid.UUID(user_id))
        # import_candidate lands the candidate in stages[0]; ensure that's the AI stage.
        assert stages[0].id == ai_stage.id, "first stage is expected to be the AI screen"
        jc_fresh = cands.import_candidate(job, full_name="Fresh Cand", phone="+919000000001")
        jc_awaiting = cands.import_candidate(job, full_name="Awaiting Cand", phone="+919000000002")
        jc_rejected = cands.import_candidate(job, full_name="Rejected Cand", phone="+919000000003")

        # Push the "awaiting" candidate's run to AWAITING_RESULT (already dialed).
        run = s.scalars(
            select(CandidateStageRun).where(CandidateStageRun.job_candidate_id == jc_awaiting.id)
        ).first()
        wes = WorkflowExecutionService(s, uuid.UUID(user_id))
        wes.schedule(run)
        wes.start(run)
        wes.await_result(run)

        jc_rejected.pipeline_state = "REJECTED"
        s.commit()
        return {
            "job_id": str(job.id),
            "stage_id": str(ai_stage.id),
            "fresh": str(jc_fresh.id),
            "awaiting": str(jc_awaiting.id),
            "rejected": str(jc_rejected.id),
        }
    finally:
        s.close()


def test_bulk_launch_launches_fresh_and_skips_handled(client):
    me = _signup(client)
    ids = _build_pipeline(me["org_id"], me["user_id"])

    r = client.post(f"/jobs/{ids['job_id']}/stages/{ids['stage_id']}/launch-all")
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["launched"] == 1
    assert body["skipped"] == 2
    assert body["failed"] == 0

    by_id = {item["job_candidate_id"]: item for item in body["results"]}
    assert by_id[ids["fresh"]]["outcome"] == "launched"
    assert by_id[ids["awaiting"]]["outcome"] == "skipped"
    assert "awaiting" in by_id[ids["awaiting"]]["reason"]
    assert by_id[ids["rejected"]]["outcome"] == "skipped"
    assert by_id[ids["rejected"]]["reason"] == "already rejected"


def test_bulk_launch_unknown_stage_is_404(client):
    me = _signup(client)
    ids = _build_pipeline(me["org_id"], me["user_id"])
    import uuid
    r = client.post(f"/jobs/{ids['job_id']}/stages/{uuid.uuid4()}/launch-all")
    assert r.status_code == 404, r.text


def test_bulk_launch_other_org_job_is_404(client):
    me = _signup(client)
    ids = _build_pipeline(me["org_id"], me["user_id"])
    # A second org's admin cannot launch the first org's job.
    client.post("/auth/logout")
    other = _signup(client, email="other@beta.test")
    assert other["org_id"] != me["org_id"]
    r = client.post(f"/jobs/{ids['job_id']}/stages/{ids['stage_id']}/launch-all")
    assert r.status_code == 404, r.text
