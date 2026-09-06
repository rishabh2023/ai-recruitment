"""WorkflowExecutionService — owns candidate stage progression (architecture §65).

Responsibilities: create stage runs, enforce valid lifecycle transitions (via the pure
state machine), evaluate stage outcomes into the next state, advance a candidate to the next
configured stage, and record an audit event for every consequential move — including explicit
overrides. Celery owns *durable async execution*; Hunar owns the *conversation*; this service
owns *business progression*.

It operates on the SQLAlchemy models and a Session. It does not commit — the caller controls
the transaction boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.candidates.models import CandidateStageRun, JobCandidate
from app.modules.jobs.models import Job
from app.modules.workflows.models import JobWorkflowStage

from .state_machine import (
    OUTCOME_TARGET,
    StageOutcome,
    StageRunState,
    assert_transition,
    is_terminal,
)


class WorkflowExecutionService:
    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id

    # --- Stage run creation -----------------------------------------------------
    def create_stage_run(
        self,
        job_candidate: JobCandidate,
        stage: JobWorkflowStage,
        initial: StageRunState = StageRunState.PENDING,
    ) -> CandidateStageRun:
        run = CandidateStageRun(
            job_candidate_id=job_candidate.id,
            job_workflow_stage_id=stage.id,
            status=initial.value,
        )
        self._s.add(run)
        self._s.flush()
        self._audit(
            job_candidate,
            action="stage_run.created",
            entity_id=run.id,
            to_state=initial.value,
        )
        return run

    # --- Enforced transitions ---------------------------------------------------
    def transition(
        self,
        run: CandidateStageRun,
        target: StageRunState,
        *,
        reason: str | None = None,
    ) -> CandidateStageRun:
        """Move a run to `target`, enforcing the state machine. Raises InvalidTransition."""
        assert_transition(run.status, target)
        return self._apply(run, target, reason=reason, action="stage_run.transition")

    # Convenience wrappers (all enforced).
    def mark_ready(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.READY, reason=reason)

    def schedule(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.SCHEDULED, reason=reason)

    def start(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.IN_PROGRESS, reason=reason)

    def await_result(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.AWAITING_RESULT, reason=reason)

    def request_human_review(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.NEEDS_REVIEW, reason=reason)

    def cancel(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.CANCELLED, reason=reason)

    def fail(self, run: CandidateStageRun, *, reason: str | None = None) -> CandidateStageRun:
        return self.transition(run, StageRunState.FAILED, reason=reason)

    # --- Outcome evaluation -----------------------------------------------------
    def complete_with_outcome(
        self,
        run: CandidateStageRun,
        outcome: StageOutcome,
        *,
        reason: str | None = None,
    ) -> CandidateStageRun | None:
        """Apply a stage outcome. Returns the next stage run when the candidate advances
        (PASS), otherwise None."""
        target = OUTCOME_TARGET[outcome]
        self.transition(run, target, reason=reason or f"outcome={outcome.value}")

        job_candidate = self._s.get(JobCandidate, run.job_candidate_id)
        if outcome is StageOutcome.PASS:
            return self.advance_candidate(job_candidate, run.job_workflow_stage_id)
        if outcome is StageOutcome.REJECT:
            job_candidate.pipeline_state = "REJECTED"
            self._audit(job_candidate, action="candidate.rejected", entity_id=job_candidate.id)
            self._s.flush()
        return None

    # --- Overrides (explicit, audited, may bypass the normal path) ---------------
    def override_transition(
        self,
        run: CandidateStageRun,
        target: StageRunState,
        *,
        reason: str,
        unresolved_requirements: list[str] | None = None,
    ) -> CandidateStageRun:
        if not reason:
            raise ValueError("override_transition requires a reason")
        return self._apply(
            run,
            target,
            reason=reason,
            action="stage_run.override",
            meta={"unresolved_requirements": unresolved_requirements or []},
        )

    # --- Candidate progression --------------------------------------------------
    def advance_candidate(
        self,
        job_candidate: JobCandidate,
        current_stage_id: UUID,
    ) -> CandidateStageRun | None:
        """Move the candidate to the next stage (by order) and create its PENDING run.
        Returns None at end of workflow (pipeline marked COMPLETED)."""
        current = self._s.get(JobWorkflowStage, current_stage_id)
        next_stage = self._s.scalars(
            select(JobWorkflowStage)
            .where(
                JobWorkflowStage.job_workflow_version_id == current.job_workflow_version_id,
                JobWorkflowStage.stage_order > current.stage_order,
            )
            .order_by(JobWorkflowStage.stage_order.asc())
            .limit(1)
        ).first()

        if next_stage is None:
            job_candidate.pipeline_state = "COMPLETED"
            self._audit(job_candidate, action="candidate.workflow_completed", entity_id=job_candidate.id)
            self._s.flush()
            return None

        job_candidate.current_stage_id = next_stage.id
        self._audit(
            job_candidate,
            action="candidate.advanced",
            entity_id=job_candidate.id,
            from_state=str(current.stage_order),
            to_state=str(next_stage.stage_order),
        )
        return self.create_stage_run(job_candidate, next_stage)

    # --- internals --------------------------------------------------------------
    def _apply(
        self,
        run: CandidateStageRun,
        target: StageRunState,
        *,
        reason: str | None,
        action: str,
        meta: dict | None = None,
    ) -> CandidateStageRun:
        from_state = run.status
        now = datetime.now(timezone.utc)
        if target is StageRunState.IN_PROGRESS and run.started_at is None:
            run.started_at = now
        if is_terminal(target):
            run.ended_at = now
        run.status = target.value
        job_candidate = self._s.get(JobCandidate, run.job_candidate_id)
        self._audit(
            job_candidate,
            action=action,
            entity_id=run.id,
            from_state=from_state,
            to_state=target.value,
            reason=reason,
            meta=meta,
        )
        self._s.flush()
        return run

    def _audit(
        self,
        job_candidate: JobCandidate,
        *,
        action: str,
        entity_id: UUID,
        from_state: str | None = None,
        to_state: str | None = None,
        reason: str | None = None,
        meta: dict | None = None,
        entity_type: str = "candidate_stage_run",
    ) -> None:
        job = self._s.get(Job, job_candidate.job_id)
        self._s.add(
            AuditEvent(
                org_id=job.org_id,
                actor_user_id=self._actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                meta=meta or {},
            )
        )
