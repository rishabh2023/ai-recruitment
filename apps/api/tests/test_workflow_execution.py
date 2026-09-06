"""DB-backed tests for WorkflowExecutionService (transaction rolled back per test)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.candidates.models import Candidate, JobCandidate
from app.modules.jobs.models import Job
from app.modules.organizations.models import Organization
from app.modules.workflows.models import (
    JobWorkflow,
    JobWorkflowStage,
    JobWorkflowVersion,
)
from app.workflow_execution import (
    InvalidTransition,
    StageOutcome,
    StageRunState,
    WorkflowExecutionService,
)


def _build_graph(session, n_stages=2):
    org = Organization(name="Acme")
    session.add(org)
    session.flush()
    job = Job(org_id=org.id, title="FDE")
    session.add(job)
    session.flush()
    jw = JobWorkflow(job_id=job.id)
    session.add(jw)
    session.flush()
    jwv = JobWorkflowVersion(job_workflow_id=jw.id, version=1, approved=True)
    session.add(jwv)
    session.flush()
    stages = []
    for i in range(1, n_stages + 1):
        st = JobWorkflowStage(
            job_workflow_version_id=jwv.id, stage_order=i, name=f"Stage {i}", execution_type="ai"
        )
        session.add(st)
        stages.append(st)
    session.flush()
    cand = Candidate(org_id=org.id, full_name="Asha")
    session.add(cand)
    session.flush()
    jc = JobCandidate(job_id=job.id, candidate_id=cand.id, current_stage_id=stages[0].id)
    session.add(jc)
    session.flush()
    return org, job, jc, stages


def test_happy_path_advances_to_next_stage(session):
    org, job, jc, stages = _build_graph(session, n_stages=2)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])
    assert run.status == "PENDING"
    svc.mark_ready(run)
    svc.schedule(run)
    svc.start(run)
    assert run.started_at is not None
    svc.await_result(run)
    next_run = svc.complete_with_outcome(run, StageOutcome.PASS)
    assert run.status == "COMPLETED" and run.ended_at is not None
    assert next_run is not None and next_run.job_workflow_stage_id == stages[1].id
    session.refresh(jc)
    assert jc.current_stage_id == stages[1].id


def test_invalid_transition_is_rejected(session):
    org, job, jc, stages = _build_graph(session, n_stages=1)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])
    with pytest.raises(InvalidTransition):
        svc.start(run)  # PENDING -> IN_PROGRESS not allowed
    assert run.status == "PENDING"


def test_override_bypasses_state_machine_and_audits(session):
    org, job, jc, stages = _build_graph(session, n_stages=1)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])
    svc.mark_ready(run)
    svc.transition(run, StageRunState.IN_PROGRESS)
    svc.transition(run, StageRunState.COMPLETED)
    # Normal path can't leave COMPLETED; override can, with a reason.
    with pytest.raises(InvalidTransition):
        svc.transition(run, StageRunState.IN_PROGRESS)
    svc.override_transition(
        run, StageRunState.IN_PROGRESS, reason="reopened by recruiter",
        unresolved_requirements=["expected_ctc"],
    )
    assert run.status == "IN_PROGRESS"
    overrides = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "stage_run.override")
    ).all()
    assert len(overrides) == 1
    assert overrides[0].meta["unresolved_requirements"] == ["expected_ctc"]


def test_override_requires_reason(session):
    org, job, jc, stages = _build_graph(session, n_stages=1)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])
    with pytest.raises(ValueError):
        svc.override_transition(run, StageRunState.READY, reason="")


def test_reject_marks_candidate_rejected(session):
    org, job, jc, stages = _build_graph(session, n_stages=2)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])
    svc.mark_ready(run); svc.start(run)
    nxt = svc.complete_with_outcome(run, StageOutcome.REJECT)
    assert nxt is None
    session.refresh(jc)
    assert jc.pipeline_state == "REJECTED"


def test_advance_at_last_stage_completes_workflow(session):
    org, job, jc, stages = _build_graph(session, n_stages=1)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])
    svc.mark_ready(run); svc.start(run)
    nxt = svc.complete_with_outcome(run, StageOutcome.PASS)
    assert nxt is None
    session.refresh(jc)
    assert jc.pipeline_state == "COMPLETED"


def test_every_transition_writes_audit(session):
    org, job, jc, stages = _build_graph(session, n_stages=1)
    svc = WorkflowExecutionService(session)
    run = svc.create_stage_run(jc, stages[0])          # +1 created
    svc.mark_ready(run)                                  # +1
    svc.schedule(run)                                    # +1
    count = session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == run.id)
    )
    assert count == 3
