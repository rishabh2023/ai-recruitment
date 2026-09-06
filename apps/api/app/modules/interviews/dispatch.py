"""HunarDispatchService — the actual outbound call to Hunar (the side that does I/O).

Kept separate from `InterviewService.launch_ai_stage` (which only builds intent + state) so the
network call runs in a Celery task and the launch path stays pure/testable. Resolves the
agent, fills the agent's required custom variables, POSTs `POST /calls/`, and records the
outcome on the Call — never losing state: a failure marks the call + run FAILED with an audit
record and reason.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.hunar import (
    HunarClient,
    HunarError,
    build_call_request,
    normalize_call_status,
)
from app.modules.audit.log import write_audit
from app.modules.candidates.models import Candidate, CandidateFact, CandidateStageRun, JobCandidate
from app.modules.jobs.models import Job
from app.modules.organizations.models import Organization
from app.modules.workflows.models import HunarAgentConfig, JobWorkflowStage
from app.workflow_execution import WorkflowExecutionService, compute_effective_information

from .models import Call, CallAttempt

logger = logging.getLogger(__name__)


class HunarDispatchError(Exception):
    """The call could not be dispatched (no agent configured, etc.)."""


class HunarDispatchService:
    def __init__(self, session: Session, client: HunarClient | None = None, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._client = client or HunarClient.from_settings(settings)
        self._actor = actor_user_id

    def dispatch(self, call_id: UUID) -> Call:
        """Place the outbound call for an already-created (QUEUED) Call. Idempotent-ish: if the
        call already has a hunar_call_id it is not re-sent."""
        call = self._s.get(Call, call_id)
        if call is None:
            raise HunarDispatchError(f"Call {call_id} not found.")
        if call.hunar_call_id:
            return call  # already dispatched

        jc = self._s.get(JobCandidate, call.job_candidate_id)
        candidate = self._s.get(Candidate, jc.candidate_id)
        job = self._s.get(Job, jc.job_id)
        org = self._s.get(Organization, job.org_id)
        run = self._s.get(CandidateStageRun, call.candidate_stage_run_id)
        stage = self._s.get(JobWorkflowStage, run.job_workflow_stage_id) if run else None

        agent_id = self._resolve_agent_id(stage)
        if not agent_id:
            self._fail(call, run, org.id, reason="No Hunar agent configured for this stage.")
            raise HunarDispatchError("No Hunar agent configured (set HUNAR_DEFAULT_AGENT_ID or a stage agent).")

        custom_data = self._build_custom_data(agent_id, candidate, job, org, stage, jc)
        payload = build_call_request(
            agent_id=agent_id,
            callee_name=candidate.full_name or "Candidate",
            mobile_number=candidate.phone,
            request_id=call.request_id,
            custom_data=custom_data,
        )
        try:
            resp = self._client.create_call(payload)
        except HunarError as exc:
            self._fail(call, run, org.id, reason=f"Hunar rejected the call: {exc}", meta={"body": exc.body})
            raise

        call.hunar_call_id = str(resp.get("id") or "")
        status = resp.get("status") or "QUEUED"
        call.vendor_status = status
        call.normalized_status = normalize_call_status(status)
        self._update_latest_attempt(call, status)
        write_audit(
            self._s, org_id=org.id, actor_user_id=self._actor,
            action="interview.dispatched", entity_type="call", entity_id=call.id,
            meta={"hunar_call_id": call.hunar_call_id, "agent_id": agent_id, "status": status},
        )
        self._s.flush()
        return call

    # --- helpers ----------------------------------------------------------------
    def _resolve_agent_id(self, stage: JobWorkflowStage | None) -> str | None:
        if stage is not None:
            cfg = self._s.scalars(
                select(HunarAgentConfig).where(HunarAgentConfig.job_workflow_stage_id == stage.id)
            ).first()
            if cfg and cfg.hunar_agent_id:
                return cfg.hunar_agent_id
        return settings.hunar_default_agent_id or None

    def _build_custom_data(self, agent_id, candidate, job, org, stage, jc) -> dict[str, str]:
        """Base context + every variable the agent requires (missing keys → 422 otherwise)."""
        base = {
            "candidate_name": candidate.full_name or "Candidate",
            "job_role": job.title,
            "job_title": job.title,
            "company": org.name,
            "location": candidate.location or "",
            "stage": stage.name if stage else "",
        }
        effective = compute_effective_information(
            stage_requirements=(stage.information_requirements or []) if stage else [],
            unresolved_prior=[],
            known_field_keys=self._known_keys(jc),
        )
        base["collect"] = ",".join(effective)

        # Ensure all agent-required variables are present (fill unknowns with "").
        for key in self._required_variables(agent_id):
            base.setdefault(key, "")
        return {k: str(v) for k, v in base.items()}

    def _required_variables(self, agent_id: str) -> list[str]:
        try:
            agent = self._client.get_agent(agent_id)
        except HunarError as exc:
            logger.warning("Could not fetch Hunar agent %s (%s); sending base custom_data.", agent_id, exc)
            return []
        req = agent.get("required_variables") or agent.get("custom_variables") or []
        return [str(k) for k in req] if isinstance(req, list) else []

    def _known_keys(self, jc: JobCandidate) -> set[str]:
        return set(
            self._s.scalars(
                select(CandidateFact.field_key).where(CandidateFact.job_candidate_id == jc.id)
            ).all()
        )

    def _update_latest_attempt(self, call: Call, status: str) -> None:
        attempt = self._s.scalars(
            select(CallAttempt).where(CallAttempt.call_id == call.id)
            .order_by(CallAttempt.attempt_number.desc()).limit(1)
        ).first()
        if attempt is not None:
            attempt.vendor_status = status
            attempt.normalized_status = normalize_call_status(status)

    def _fail(self, call: Call, run, org_id, *, reason: str, meta: dict | None = None) -> None:
        call.normalized_status = "FAILED"
        self._update_latest_attempt(call, "FAILED")
        if run is not None and run.status == "AWAITING_RESULT":
            WorkflowExecutionService(self._s, self._actor).fail(run, reason=reason)
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="interview.dispatch_failed", entity_type="call", entity_id=call.id,
            reason=reason, meta=meta or {},
        )
        self._s.flush()
