"""Phase 2 job-creation flow tests (DB-backed; transaction rolled back per test)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.integrations.llm import StubLLMProvider
from app.modules.audit.models import AuditEvent
from app.modules.jobs.models import Job, JobVersion
from app.modules.jobs.service import JobActivationError, JobService
from app.modules.organizations.models import Organization, User
from app.modules.workflows.models import JobWorkflowStage, JobWorkflowVersion, StageCriteria
from app.workflow_execution import StageRunState  # noqa: F401  (ensures package imports)


ENG_JD = "Senior Backend Engineer\nPython, FastAPI, Postgres, system design, LLM."
SALES_JD = "Account Executive\nQuota-carrying sales role, discovery and objection handling."


def _org_user(session):
    org = Organization(name="Acme")
    session.add(org)
    session.flush()
    user = User(org_id=org.id, email="r@acme.com", role="recruiter")
    session.add(user)
    session.flush()
    return org, user


def test_extract_confirm_draft_approve_activate(session):
    org, user = _org_user(session)
    from app.modules.workflows.service import WorkflowService

    jobs = JobService(session, actor_user_id=user.id)
    wf = WorkflowService(session, actor_user_id=user.id)

    job = jobs.create_job(org.id, "Senior Backend Engineer")
    assert job.status == "draft"

    jv = jobs.add_job_version(job, ENG_JD)
    assert jv.confirmed is False
    assert jv.extracted["role_family"] == "engineering"
    assert "fastapi" in jv.extracted["skills"]

    # Cannot activate before confirming JD.
    with pytest.raises(JobActivationError):
        jobs.activate_job(job)

    jobs.confirm_job_version(jv)
    assert jv.confirmed is True

    # Draft workflow: unapproved, with stages + criteria.
    from app.integrations.llm import ExtractedJob
    version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
    assert version.approved is False
    stages = session.scalars(
        select(JobWorkflowStage).where(JobWorkflowStage.job_workflow_version_id == version.id)
    ).all()
    assert [s.stage_order for s in sorted(stages, key=lambda s: s.stage_order)] == [1, 2, 3, 4]
    tech = next(s for s in stages if s.name == "Technical Assessment")
    crit = session.scalars(
        select(StageCriteria).where(StageCriteria.job_workflow_stage_id == tech.id)
    ).all()
    assert len(crit) == 5

    # Still cannot activate until workflow approved.
    with pytest.raises(JobActivationError):
        jobs.activate_job(job)

    wf.approve_workflow_version(version, approver_user_id=user.id)
    assert version.approved and version.approved_at is not None

    jobs.activate_job(job)
    assert job.status == "active"


def test_activation_blocked_without_confirmed_jd(session):
    org, user = _org_user(session)
    jobs = JobService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, "X")
    jobs.add_job_version(job, ENG_JD)  # not confirmed
    with pytest.raises(JobActivationError):
        jobs.activate_job(job)


def test_sales_jd_drafts_sales_stage(session):
    org, user = _org_user(session)
    from app.integrations.llm import ExtractedJob
    from app.modules.workflows.service import WorkflowService

    jobs = JobService(session, actor_user_id=user.id)
    wf = WorkflowService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, "Account Executive")
    jv = jobs.add_job_version(job, SALES_JD)
    assert jv.extracted["role_family"] == "sales"
    version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
    names = {
        s.name
        for s in session.scalars(
            select(JobWorkflowStage).where(JobWorkflowStage.job_workflow_version_id == version.id)
        )
    }
    assert "Sales Assessment" in names and "Technical Assessment" not in names


def test_job_versions_increment(session):
    org, user = _org_user(session)
    jobs = JobService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, "X")
    v1 = jobs.add_job_version(job, ENG_JD)
    v2 = jobs.add_job_version(job, ENG_JD + " revised")
    assert (v1.version, v2.version) == (1, 2)


def test_steps_are_audited(session):
    org, user = _org_user(session)
    from app.integrations.llm import ExtractedJob
    from app.modules.workflows.service import WorkflowService

    jobs = JobService(session, actor_user_id=user.id)
    wf = WorkflowService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, "X")
    jv = jobs.add_job_version(job, ENG_JD)
    jobs.confirm_job_version(jv)
    version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
    wf.approve_workflow_version(version, approver_user_id=user.id)
    jobs.activate_job(job)
    actions = set(
        session.scalars(select(AuditEvent.action).where(AuditEvent.org_id == org.id)).all()
    )
    assert {
        "job.created", "job.jd_extracted", "job.jd_confirmed",
        "workflow.drafted", "workflow.approved", "job.activated",
    } <= actions


def test_stub_provider_is_deterministic():
    p = StubLLMProvider()
    a = p.extract_job(ENG_JD)
    b = p.extract_job(ENG_JD)
    assert a == b and a.role_family == "engineering"
