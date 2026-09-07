"""F-009 provisioning service: resolve-or-create per stage, idempotent, intent-matched.

Uses a fake Hunar client (no network). Verifies the bound → matched → created ladder, that a
role mismatch never binds the wrong agent, that re-provisioning creates no duplicates, and that a
create failure is a typed per-stage error the sweep records without aborting.
"""

from __future__ import annotations

from sqlalchemy import select

from app.integrations.hunar.client import HunarError
from app.integrations.llm import ExtractedJob
from app.modules.interviews.agent_provisioning import (
    AgentProvisioningService,
    provision_version_agents,
)
from app.modules.jobs.service import JobService
from app.modules.organizations.models import Organization, User
from app.modules.workflows.models import HunarAgentConfig, JobWorkflowStage
from app.modules.workflows.service import WorkflowService


class FakeHunar:
    """Records create calls; can return a scripted account-agent list for intent matching."""

    def __init__(self, *, agents=None, raise_on_create=False, schemas=None):
        self._agents = agents or []
        self._raise_on_create = raise_on_create
        # agent_id -> result_schema keys; default covers everything so matches aren't blocked.
        self._schemas = schemas or {}
        self.created: list[dict] = []
        self._next = 0

    def list_agents(self, *, page: int = 1):
        return {"results": self._agents}

    def get_agent(self, agent_id):
        # Default: a schema covering common fields so coverage checks pass unless overridden.
        keys = self._schemas.get(
            agent_id,
            ["interest", "current_ctc", "expected_ctc", "notice_period", "location", "summary"],
        )
        return {"result_schema": {k: "string" for k in keys}}

    def create_agent(self, payload):
        if self._raise_on_create:
            raise HunarError("rate limited", status_code=429)
        self.created.append(payload)
        self._next += 1
        return {"id": f"created-{self._next}", "status": "ACTIVE"}


def _setup(session, title="Backend Engineer"):
    org = Organization(name="Acme"); session.add(org); session.flush()
    user = User(org_id=org.id, email="r@acme.com", role="recruiter"); session.add(user); session.flush()
    jobs = JobService(session, actor_user_id=user.id)
    wf = WorkflowService(session, actor_user_id=user.id)
    job = jobs.create_job(org.id, title)
    jv = jobs.add_job_version(job, f"{title}\nPython, FastAPI")
    jobs.confirm_job_version(jv)
    version = wf.draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
    return org, user, job, version


def _ai_stage(session, version):
    return session.scalars(
        select(JobWorkflowStage)
        .where(JobWorkflowStage.job_workflow_version_id == version.id, JobWorkflowStage.execution_type == "ai")
        .order_by(JobWorkflowStage.stage_order.asc())
    ).first()


class FakeLLM:
    """A scripted LLM matcher: returns a fixed agent id (or None) regardless of input."""

    key = "fake"

    def __init__(self, returns):
        self._returns = returns
        self.seen = None

    def match_agent(self, *, role, stage_purpose, company, collect, candidates):
        self.seen = {"role": role, "candidates": candidates}
        return self._returns


def test_llm_match_is_used_when_it_returns_a_valid_agent(session):
    org, user, job, version = _setup(session, title="Java Backend Developer")
    stage = _ai_stage(session, version)
    # Two agents whose NAMES don't contain the role — deterministic match would create; the LLM
    # semantically recognises the right one for reuse.
    fake = FakeHunar(agents=[
        {"id": "a-sales", "name": "Outbound Caller", "status": "ACTIVE"},
        {"id": "a-backend", "name": "Server Engineering Screen", "status": "ACTIVE"},
    ])
    llm = FakeLLM(returns="a-backend")
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id, llm=llm)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert (agent_id, source) == ("a-backend", "matched")
    assert fake.created == []
    assert {c["id"] for c in llm.seen["candidates"]} == {"a-sales", "a-backend"}


def test_llm_hallucinated_id_is_rejected_and_agent_created(session):
    org, user, job, version = _setup(session)
    stage = _ai_stage(session, version)
    fake = FakeHunar(agents=[{"id": "real-1", "name": "Some Agent", "status": "ACTIVE"}])
    # The LLM returns an id that is not in the candidate set → must be ignored, not bound.
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id, llm=FakeLLM(returns="ghost-99"))
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert source == "created"
    assert agent_id != "ghost-99"


def test_match_declined_when_agent_schema_misses_required_fields(session):
    org, user, job, version = _setup(session, title="Full Stack Developer")
    stage = _ai_stage(session, version)  # requires interest, current_ctc, expected_ctc, notice_period, location
    # A same-role agent exists BUT its result schema lacks current_ctc/expected_ctc/location —
    # so it can't populate evidence. Must be declined in favour of a generated (covering) agent.
    fake = FakeHunar(
        agents=[{"id": "screener-1", "name": "Screener - Full Stack Developer", "status": "ACTIVE"}],
        schemas={"screener-1": ["interested", "notice_period", "years_experience", "summary"]},
    )
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert source == "created"
    assert agent_id != "screener-1"
    # And the created agent DOES cover the required fields.
    assert set(fake.created[0]["result_schema"]) >= set(stage.information_requirements or [])


def test_screener_not_reused_for_technical_stage_with_criteria(session):
    from app.modules.workflows.models import StageCriteria
    org, user, job, version = _setup(session, title="Fullstack Engineer")
    stage = _ai_stage(session, version)
    # Make this an interview stage: no info-requirements, but success criteria to assess.
    stage.name = "Technical Assessment"
    stage.purpose = "Evaluate engineering competencies"
    stage.information_requirements = []
    for name in ("Backend / API engineering", "System design"):
        session.add(StageCriteria(job_workflow_stage_id=stage.id, name=name, kind="numeric"))
    session.flush()
    # A same-role SCREENING agent exists whose schema only covers interest/logistics.
    fake = FakeHunar(
        agents=[{"id": "screen-1", "name": "Fullstack Engineer — Initial Screening", "status": "ACTIVE"}],
        schemas={"screen-1": ["interest", "current_ctc", "notice_period", "summary"]},
    )
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    # The screener lacks the technical criteria → must NOT be reused; a technical agent is created.
    assert source == "created" and agent_id != "screen-1"
    assert {"backend_api_engineering", "system_design"} <= set(fake.created[0]["result_schema"])


def test_creates_agent_when_no_match(session):
    org, user, job, version = _setup(session)
    stage = _ai_stage(session, version)
    fake = FakeHunar(agents=[])  # empty account → must create
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert source == "created"
    assert agent_id == "created-1"
    assert len(fake.created) == 1
    # result_schema keys mirror the stage's information_requirements → evidence populates.
    assert set(fake.created[0]["result_schema"]) >= set(stage.information_requirements or [])


def test_matches_existing_agent_by_role_no_duplicate(session):
    org, user, job, version = _setup(session, title="Sales Executive")
    stage = _ai_stage(session, version)
    fake = FakeHunar(agents=[{"id": "acct-9", "name": "Sales Executive Screener", "status": "ACTIVE"}])
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert source == "matched"
    assert agent_id == "acct-9"
    assert fake.created == []  # reused, never created a duplicate


def test_role_mismatch_never_binds_wrong_agent(session):
    org, user, job, version = _setup(session, title="Java Backend Developer")
    stage = _ai_stage(session, version)
    # A Sales agent exists but the role differs → must NOT bind it; creates a correct one.
    fake = FakeHunar(agents=[{"id": "sales-1", "name": "Sales Executive Screener", "status": "ACTIVE"}])
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert source == "created"
    assert agent_id != "sales-1"


def test_idempotent_bound_stage_is_reused(session):
    org, user, job, version = _setup(session)
    stage = _ai_stage(session, version)
    session.add(HunarAgentConfig(job_workflow_stage_id=stage.id, hunar_agent_id="pinned-1"))
    session.flush()
    fake = FakeHunar(agents=[])
    svc = AgentProvisioningService(session, fake, actor_user_id=user.id)
    agent_id, source = svc.ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
    assert (agent_id, source) == ("pinned-1", "bound")
    assert fake.created == []


def test_version_sweep_binds_every_ai_stage_once(session):
    org, user, job, version = _setup(session)
    fake = FakeHunar(agents=[])
    results = provision_version_agents(session, version, fake, actor_user_id=user.id)
    ai_stages = session.scalars(
        select(JobWorkflowStage).where(
            JobWorkflowStage.job_workflow_version_id == version.id,
            JobWorkflowStage.execution_type == "ai",
        )
    ).all()
    assert len(results) == len(ai_stages)
    assert all(r.source == "created" and r.hunar_agent_id for r in results)
    # Re-running the sweep must not create duplicates — every stage is now bound.
    again = provision_version_agents(session, version, fake, actor_user_id=user.id)
    assert all(r.source == "bound" for r in again)
    bindings = session.scalars(select(HunarAgentConfig)).all()
    assert len(bindings) == len(ai_stages)  # exactly one per AI stage, no dups


def test_create_failure_is_recorded_not_raised_in_sweep(session):
    org, user, job, version = _setup(session)
    fake = FakeHunar(agents=[], raise_on_create=True)
    results = provision_version_agents(session, version, fake, actor_user_id=user.id)
    assert results  # sweep completed
    assert all(r.error and r.hunar_agent_id is None for r in results)
    # No half-written bindings for the failed stages.
    assert session.scalars(select(HunarAgentConfig)).all() == []
