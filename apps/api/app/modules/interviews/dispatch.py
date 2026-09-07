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
from app.modules.workflows.models import CallingPolicy, HunarAgentConfig, JobWorkflowStage
from app.workflow_execution import WorkflowExecutionService, compute_effective_information

from .models import Call, CallAttempt

logger = logging.getLogger(__name__)

# Sent for a required agent variable the candidate doesn't have on file, so a missing optional
# detail (location, email, …) never causes a Hunar 422 that blocks the call.
_NOT_PROVIDED = "Not provided"

# The interviewer name injected for agents whose script self-introduces via a persona placeholder
# (e.g. "this is {persona_name} calling"). Matches the default voice persona used by generated
# agents (agent_spec.build_agent_spec voice_persona="NEHA").
_DEFAULT_PERSONA_NAME = "Neha"


class HunarDispatchError(Exception):
    """The call could not be dispatched (no agent configured, etc.)."""


def _summarize_hunar_error(exc: HunarError) -> str:
    """Human-readable reason from a Hunar error, surfacing the validation detail (e.g. which
    required variable was missing) so a 422 is diagnosable in the UI/audit, not opaque."""
    body = exc.body
    parts: list[str] = []
    if isinstance(body, dict):
        for key in ("detail", "message", "error", "errors", "non_field_errors"):
            val = body.get(key)
            if val:
                parts.append(val if isinstance(val, str) else str(val))
        # Field-level validation maps (e.g. {"custom_data": ["location is required"]}).
        if not parts:
            for k, v in body.items():
                parts.append(f"{k}: {v if isinstance(v, str) else ', '.join(map(str, v)) if isinstance(v, list) else v}")
    elif isinstance(body, str) and body.strip():
        parts.append(body.strip())
    summary = "; ".join(parts)[:300]
    return f"{exc} — {summary}" if summary else str(exc)


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

        if job.status == "archived":
            self._cancel_inactive_job(call, run, org.id)
            raise HunarDispatchError("Role is inactive; queued call was cancelled before dispatch.")

        agent_id, agent_source = self._resolve_agent(stage, job, org)
        if not agent_id:
            self._fail(call, run, org.id, reason="No Hunar agent configured for this stage.")
            raise HunarDispatchError("No Hunar agent configured (set HUNAR_DEFAULT_AGENT_ID or a stage agent).")
        if agent_source == "default":
            # F-009: the global default is a last-resort fallback, never the normal path — surface
            # it so a wrong-intent call is visible, not silent.
            write_audit(
                self._s, org_id=org.id, actor_user_id=self._actor,
                action="interview.agent_fallback_default", entity_type="call", entity_id=call.id,
                meta={"agent_id": agent_id, "stage_id": str(stage.id) if stage else None,
                      "warning": "Stage has no bound voice agent; used the global default agent."},
            )

        custom_data = self._build_custom_data(agent_id, candidate, job, org, stage, jc)
        guardrails, retry_config, timezone = self._calling_policy(job.id)
        payload = build_call_request(
            agent_id=agent_id,
            callee_name=candidate.full_name or "Candidate",
            mobile_number=candidate.phone,
            request_id=call.request_id,
            custom_data=custom_data,
            callback_config=self._callback_config(),
            guardrails=guardrails,
            retry_config=retry_config,
            timezone=timezone,
        )
        try:
            resp = self._client.create_call(payload)
        except HunarError as exc:
            detail = _summarize_hunar_error(exc)
            self._fail(call, run, org.id, reason=f"Hunar rejected the call: {detail}", meta={"body": exc.body})
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

    def _calling_policy(self, job_id):
        """Map the job's CallingPolicy → Hunar (guardrails, retry_config, timezone). Guardrails
        are only sent when complete (Hunar requires ≥3 days + a start/end window), else omitted."""
        p = self._s.scalars(select(CallingPolicy).where(CallingPolicy.job_id == job_id)).first()
        if p is None:
            return None, None, None
        guardrails = None
        if p.allowed_days and p.earliest_call_time and p.last_call_time:
            guardrails = {
                "allowed_days": list(p.allowed_days),
                "earliest_call_time": p.earliest_call_time.strftime("%H:%M"),
                "last_call_time": p.last_call_time.strftime("%H:%M"),
            }
            if p.timezone:
                guardrails["timezone"] = p.timezone
        retry_config = {"max_retry_count": max(0, p.max_attempts - 1), "retry_interval_hours": p.retry_interval_hours}
        return guardrails, retry_config, p.timezone

    def _callback_config(self) -> dict[str, str] | None:
        """Register all Hunar event callbacks at our webhook endpoint so status/result/
        recording/summary come back automatically. None when no public URL is configured."""
        base = settings.public_base_url.rstrip("/")
        if not base:
            return None
        url = f"{base}/webhooks/hunar"
        return {
            "call_status_callback_url": url,
            "call_result_callback_url": url,
            "call_recording_callback_url": url,
            "call_summary_callback_url": url,
        }

    # --- helpers ----------------------------------------------------------------
    def _resolve_agent(self, stage: JobWorkflowStage | None, job, org) -> tuple[str | None, str]:
        """Resolve the agent for this stage, returning (agent_id, source).

        Prefers the per-stage binding (``bound``). If none exists, a lazy safety net tries to
        provision one now (``created``/``matched``) — the eager path at approval should have done
        this, but a stage can be unbound (approved before F-009, provisioning failed, etc.).
        Only if that cannot bind an agent does it fall back to the global default (``default``).
        """
        if stage is not None:
            cfg = self._s.scalars(
                select(HunarAgentConfig)
                .where(HunarAgentConfig.job_workflow_stage_id == stage.id)
                .order_by(HunarAgentConfig.created_at.desc())
            ).first()
            if cfg and cfg.hunar_agent_id:
                return cfg.hunar_agent_id, "bound"
            lazy = self._lazy_provision(stage, job, org)
            if lazy:
                return lazy
        return (settings.hunar_default_agent_id or None), "default"

    def _lazy_provision(self, stage: JobWorkflowStage, job, org) -> tuple[str, str] | None:
        """Best-effort bind at dispatch time. A failure here is swallowed so we fall back to the
        default rather than dropping the call — provisioning is a convenience, dialing is the job.
        """
        if (stage.execution_type or "").lower() != "ai":
            return None
        from .agent_provisioning import AgentProvisioningError, AgentProvisioningService

        try:
            agent_id, source = AgentProvisioningService(
                self._s, self._client, actor_user_id=self._actor
            ).ensure_stage_agent(stage, job_title=job.title, company=org.name, org_id=org.id)
        except (AgentProvisioningError, HunarError):
            logger.warning("Lazy agent provisioning failed for stage %s; using default", stage.id)
            return None
        return agent_id, source

    def _build_custom_data(self, agent_id, candidate, job, org, stage, jc) -> dict[str, str]:
        """Base context + every variable the agent requires (missing keys → 422 otherwise)."""
        name = candidate.full_name or "Candidate"
        # Provide the context under every common alias an agent's script might reference. Hunar
        # derives required custom-data keys from the placeholders in the agent prompt (e.g.
        # ``{role}``, ``{persona_name}``), and those are not always listed in ``required_variables``
        # — so sending the aliases up front prevents a 422 whichever naming the agent chose.
        base = {
            "candidate_name": name,
            "callee_name": name,
            "job_role": job.title,
            "job_title": job.title,
            "role": job.title,
            "position": job.title,
            "company": org.name,
            "company_name": org.name,
            "persona_name": _DEFAULT_PERSONA_NAME,
            "location": candidate.location or "",
            "stage": stage.name if stage else "",
        }
        effective = compute_effective_information(
            stage_requirements=(stage.information_requirements or []) if stage else [],
            unresolved_prior=[],
            known_field_keys=self._known_keys(jc),
        )
        base["collect"] = ",".join(effective)

        # Hunar returns 422 when an agent-required variable is missing OR empty. A candidate can
        # legitimately lack optional details (location, email, …), and that must never block the
        # call — so every required variable is present and any blank is filled with a neutral
        # placeholder the agent can handle gracefully ("the caller didn't have this on file").
        required = set(self._required_variables(agent_id))
        for key in required:
            base.setdefault(key, "")
        out: dict[str, str] = {}
        for key, value in base.items():
            text = str(value).strip()
            if not text and key in required:
                text = _NOT_PROVIDED
            out[key] = text
        return out

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

    def _cancel_inactive_job(self, call: Call, run, org_id) -> None:
        """Stop a queued call if its role was made inactive before the worker dispatched it."""
        reason = "Role was marked inactive before this queued call could be dispatched."
        call.normalized_status = "CANCELLED"
        self._update_latest_attempt(call, "CANCELLED")
        if run is not None and run.status == "AWAITING_RESULT":
            WorkflowExecutionService(self._s, self._actor).cancel(run, reason=reason)
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="interview.dispatch_cancelled_inactive_job", entity_type="call", entity_id=call.id,
            reason=reason,
        )
        self._s.flush()
