"""CandidateService — import/add candidates with progressive profile + provenance.

Supports the two entry paths (import existing, or sourced) and lets an authorized recruiter
start a candidate at a later stage where business context justifies it — an explicit, audited
action, never a silent inference (docs/domain.md, architecture §47/§51). Known information is
stored as field-level `candidate_facts` with provenance. Does not commit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.log import write_audit
from app.modules.jobs.models import Job
from app.modules.workflows.models import JobWorkflowStage
from app.workflow_execution import StageRunState, WorkflowExecutionService

from .models import Candidate, CandidateFact, JobCandidate


class CandidateService:
    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id

    def import_candidate(
        self,
        job: Job,
        *,
        full_name: str,
        phone: str | None = None,
        email: str | None = None,
        location: str | None = None,
        source: str = "import",
        source_id: str | None = None,
        known_facts: dict[str, str] | None = None,
        starting_stage: JobWorkflowStage | None = None,
    ) -> JobCandidate:
        """Create a candidate + participation, record known facts, and create the first stage
        run at the (optionally later) starting stage."""
        candidate = Candidate(
            org_id=job.org_id, full_name=full_name, phone=phone, email=email,
            location=location, source=source, source_id=source_id,
        )
        self._s.add(candidate)
        self._s.flush()

        stage = starting_stage or self._first_stage(job)
        jc = JobCandidate(
            job_id=job.id, candidate_id=candidate.id,
            current_stage_id=stage.id if stage else None,
            pipeline_state="SOURCED" if source != "import" else "INTERVIEW_PENDING",
        )
        self._s.add(jc)
        self._s.flush()

        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="candidate.imported", entity_type="job_candidate", entity_id=jc.id,
            meta={"source": source, "starting_stage": stage.name if stage else None},
        )

        for key, value in (known_facts or {}).items():
            self.record_fact(jc, key, value, source=source)

        if stage is not None:
            wes = WorkflowExecutionService(self._s, self._actor)
            wes.create_stage_run(jc, stage, initial=StageRunState.READY)
            if starting_stage is not None and self._is_later_stage(job, stage):
                write_audit(
                    self._s, org_id=job.org_id, actor_user_id=self._actor,
                    action="candidate.started_at_later_stage",
                    entity_type="job_candidate", entity_id=jc.id,
                    to_state=stage.name, reason="explicit recruiter starting-stage selection",
                )
        return jc

    def record_fact(
        self, job_candidate: JobCandidate, field_key: str, value: str, *,
        source: str, source_stage_run_id: UUID | None = None, confidence: str | None = None,
    ) -> CandidateFact:
        fact = CandidateFact(
            job_candidate_id=job_candidate.id, field_key=field_key, value=value,
            source=source, source_stage_run_id=source_stage_run_id, confidence=confidence,
        )
        self._s.add(fact)
        self._s.flush()
        return fact

    def known_field_keys(self, job_candidate: JobCandidate) -> set[str]:
        return set(
            self._s.scalars(
                select(CandidateFact.field_key).where(
                    CandidateFact.job_candidate_id == job_candidate.id
                )
            ).all()
        )

    # --- helpers ----------------------------------------------------------------
    def _approved_version_id(self, job: Job) -> UUID | None:
        from app.modules.workflows.models import JobWorkflow, JobWorkflowVersion

        return self._s.scalar(
            select(JobWorkflowVersion.id)
            .join(JobWorkflow, JobWorkflow.id == JobWorkflowVersion.job_workflow_id)
            .where(JobWorkflow.job_id == job.id, JobWorkflowVersion.approved.is_(True))
            .order_by(JobWorkflowVersion.version.desc())
            .limit(1)
        )

    def _first_stage(self, job: Job) -> JobWorkflowStage | None:
        ver_id = self._approved_version_id(job)
        if ver_id is None:
            return None
        return self._s.scalars(
            select(JobWorkflowStage)
            .where(JobWorkflowStage.job_workflow_version_id == ver_id)
            .order_by(JobWorkflowStage.stage_order.asc())
            .limit(1)
        ).first()

    def _is_later_stage(self, job: Job, stage: JobWorkflowStage) -> bool:
        first = self._first_stage(job)
        return bool(first and stage.stage_order > first.stage_order)
