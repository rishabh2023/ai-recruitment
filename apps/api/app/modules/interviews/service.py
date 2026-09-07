"""InterviewService — launch an AI stage as a Hunar call intent (dispatch).

Builds the effective stage context (carry-forward), persists a Call + first CallAttempt, and
moves the stage run to AWAITING_RESULT. It returns the exact Hunar `POST /calls/` payload it
*would* send; the actual HTTP call is performed by the Hunar adapter in a Celery task (not
invoked here — and a live call also needs a provisioned Hunar number). Does not commit.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.hunar import build_call_request
from app.modules.audit.log import write_audit
from app.modules.candidates.models import Candidate, CandidateFact, JobCandidate
from app.modules.jobs.models import Job
from app.modules.workflows.models import HunarAgentConfig, JobWorkflowStage
from app.workflow_execution import (
    StageRunState,
    WorkflowExecutionService,
    compute_effective_information,
)

from .models import Call, CallAttempt


class InterviewLaunchError(Exception):
    """Raised when an AI stage cannot be launched (wrong stage type, missing phone, etc.)."""


class InterviewService:
    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id
        self._wes = WorkflowExecutionService(session, actor_user_id)

    def launch_ai_stage(
        self,
        job_candidate: JobCandidate,
        stage: JobWorkflowStage,
        run,
        *,
        unresolved_prior: list[str] | None = None,
    ) -> tuple[Call, dict]:
        if stage.execution_type != "ai":
            raise InterviewLaunchError(f"Stage '{stage.name}' is not an AI stage.")
        candidate = self._s.get(Candidate, job_candidate.candidate_id)
        if not candidate.phone:
            raise InterviewLaunchError("Candidate has no phone number for an outbound call.")

        effective = compute_effective_information(
            stage_requirements=stage.information_requirements or [],
            unresolved_prior=unresolved_prior or [],
            known_field_keys=self._known_keys(job_candidate),
        )

        request_id = uuid4().hex
        call = Call(
            job_candidate_id=job_candidate.id,
            candidate_stage_run_id=run.id,
            request_id=request_id,
            normalized_status="QUEUED",
        )
        self._s.add(call)
        self._s.flush()
        self._s.add(
            CallAttempt(call_id=call.id, attempt_number=1, kind="business", normalized_status="QUEUED")
        )

        # Move the run toward awaiting a result (enforced transitions). A run the candidate was
        # just advanced into is PENDING, so promote it to READY first (PENDING→READY→SCHEDULED→
        # IN_PROGRESS→AWAITING_RESULT); an already-READY run skips the first step.
        if run.status == StageRunState.PENDING.value:
            self._wes.mark_ready(run)
        if run.status == StageRunState.READY.value:
            self._wes.schedule(run)
        self._wes.start(run)
        self._wes.await_result(run)

        payload = build_call_request(
            agent_id=self._agent_id_for_stage(stage),
            callee_name=candidate.full_name or "Candidate",
            mobile_number=candidate.phone,
            request_id=request_id,
            custom_data={
                "job_title": self._job_title(job_candidate),
                "stage": stage.name,
                "collect": ",".join(effective),
            },
        )
        write_audit(
            self._s, org_id=self._org_id(job_candidate), actor_user_id=self._actor,
            action="interview.launched", entity_type="call", entity_id=call.id,
            meta={"effective_information": effective, "request_id": request_id},
        )
        return call, payload

    # --- helpers ----------------------------------------------------------------
    def _known_keys(self, job_candidate: JobCandidate) -> set[str]:
        return set(
            self._s.scalars(
                select(CandidateFact.field_key).where(
                    CandidateFact.job_candidate_id == job_candidate.id
                )
            ).all()
        )

    def _agent_id_for_stage(self, stage: JobWorkflowStage) -> str:
        cfg = self._s.scalars(
            select(HunarAgentConfig).where(HunarAgentConfig.job_workflow_stage_id == stage.id)
        ).first()
        # Until provisioning is wired, use a placeholder so the payload shape is complete.
        return cfg.hunar_agent_id if cfg else "PENDING_AGENT_PROVISIONING"

    def _job_title(self, job_candidate: JobCandidate) -> str:
        job = self._s.get(Job, job_candidate.job_id)
        return job.title

    def _org_id(self, job_candidate: JobCandidate) -> UUID:
        job = self._s.get(Job, job_candidate.job_id)
        return job.org_id
