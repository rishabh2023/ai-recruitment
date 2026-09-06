"""WebhookService — idempotent Hunar webhook ingestion + result processing.

The HTTP handler stays thin (verify signature, persist raw + dedup, enqueue); this service is
the worker-side processing. A duplicate delivery is a no-op — it never double-advances state
(docs/interfaces.md idempotency). On a result event it stores the structured result, updates
candidate facts (with provenance), and moves the run to NEEDS_REVIEW for a human decision.
Does not commit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.hunar import normalize_call_status, webhook_dedup_key
from app.modules.audit.log import write_audit
from app.modules.candidates.models import JobCandidate
from app.modules.candidates.service import CandidateService
from app.modules.interviews.models import Call, CallAttempt, StageResult
from app.modules.jobs.models import Job
from app.workflow_execution import StageRunState, WorkflowExecutionService

from .models import WebhookEvent

# Result fields we accept into candidate_facts (screening basics).
_FACT_KEYS = (
    "interested", "current_ctc", "expected_ctc", "notice_period",
    "preferred_location", "availability", "reason_for_change",
)

# Terminal call outcomes with no structured result → the run cannot wait forever. Each maps to
# a human-readable reason recorded on the FAILED transition. RETRY_SCHEDULED is intentionally
# absent: a retry is pending, so the run stays AWAITING_RESULT.
_UNCONNECTED_TERMINAL = {
    "NO_ANSWER": "Candidate did not answer / rejected the call (not connected).",
    "FAILED": "Call failed at the provider.",
    "CANCELLED": "Call was cancelled.",
}


class WebhookService:
    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id

    def find_existing(self, payload: dict) -> WebhookEvent | None:
        """Return the already-stored event for this payload, if any (idempotency lookup)."""
        dedup_key = webhook_dedup_key(payload.get("event", ""), str(payload.get("id", "")))
        return self._s.scalars(
            select(WebhookEvent).where(
                WebhookEvent.provider == "hunar", WebhookEvent.dedup_key == dedup_key
            )
        ).first()

    def handle_hunar_event(self, payload: dict, *, signature_valid: bool = True) -> WebhookEvent:
        """Idempotently ingest and process one Hunar webhook event."""
        event_type = payload.get("event", "")
        hunar_call_id = str(payload.get("id", ""))
        dedup_key = webhook_dedup_key(event_type, hunar_call_id)

        existing = self.find_existing(payload)
        if existing is not None:
            return existing  # duplicate: no side effects

        event = WebhookEvent(
            provider="hunar", event_type=event_type, dedup_key=dedup_key,
            raw=payload, signature_valid=signature_valid,
        )
        self._s.add(event)
        self._s.flush()

        call = self._resolve_call(payload)
        if call is not None:
            event.call_id = call.id
            self._update_call_status(call, payload)
            if event_type in ("call_result_done", "call_summary") and payload.get("result"):
                self._apply_result(call, payload)
            else:
                self._advance_run_for_terminal_status(call)

        event.processed_at = datetime.now(timezone.utc)
        self._s.flush()
        return event

    def sync_call(self, call: Call, snapshot: dict) -> Call:
        """Apply a `GET /calls/{id}` snapshot (status + optional result) to a Call.

        Used by the status-sync endpoint when no public webhook URL is registered (dev). Safe to
        call repeatedly — the structured result is ingested at most once per stage run.
        """
        self._update_call_status(call, snapshot)
        if snapshot.get("result") and not self._has_result(call):
            self._apply_result(call, snapshot)
        else:
            self._advance_run_for_terminal_status(call)
        return call

    def _advance_run_for_terminal_status(self, call: Call) -> None:
        """A terminal, not-connected call (no answer / failed / cancelled) must not leave the
        stage run waiting forever. Move it to FAILED with a reason so the recruiter sees why and
        can retry. RETRY_SCHEDULED is left as-is (a retry is pending)."""
        from app.modules.candidates.models import CandidateStageRun

        if call.candidate_stage_run_id is None:
            return
        reason = _UNCONNECTED_TERMINAL.get(call.normalized_status or "")
        if reason is None:
            return
        run = self._s.get(CandidateStageRun, call.candidate_stage_run_id)
        if run is None or run.status != StageRunState.AWAITING_RESULT.value:
            return
        WorkflowExecutionService(self._s, self._actor).fail(run, reason=reason)
        jc = self._s.get(JobCandidate, call.job_candidate_id)
        job = self._s.get(Job, jc.job_id)
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="interview.call_not_connected", entity_type="call", entity_id=call.id,
            to_state="FAILED", reason=reason,
        )
        self._s.flush()

    def _has_result(self, call: Call) -> bool:
        if call.candidate_stage_run_id is None:
            return False
        n = self._s.scalar(
            select(func.count()).select_from(StageResult).where(
                StageResult.candidate_stage_run_id == call.candidate_stage_run_id
            )
        )
        return bool(n and n > 0)

    # --- internals --------------------------------------------------------------
    def _resolve_call(self, payload: dict) -> Call | None:
        request_id = payload.get("request_id")
        call = None
        if request_id:
            call = self._s.scalars(select(Call).where(Call.request_id == request_id)).first()
        if call is None and payload.get("id"):
            call = self._s.scalars(
                select(Call).where(Call.hunar_call_id == str(payload["id"]))
            ).first()
        if call is not None and not call.hunar_call_id and payload.get("id"):
            call.hunar_call_id = str(payload["id"])
        return call

    def _update_call_status(self, call: Call, payload: dict) -> None:
        status = payload.get("status")
        if not status:
            return
        call.vendor_status = status
        call.normalized_status = normalize_call_status(
            status, retries_left=payload.get("retries_left")
        )
        attempt = self._s.scalars(
            select(CallAttempt)
            .where(CallAttempt.call_id == call.id)
            .order_by(CallAttempt.attempt_number.desc())
            .limit(1)
        ).first()
        if attempt is not None:
            attempt.vendor_status = status
            attempt.normalized_status = call.normalized_status
        self._s.flush()

    def _apply_result(self, call: Call, payload: dict) -> None:
        result = payload.get("result") or {}
        run_id = call.candidate_stage_run_id
        self._s.add(
            StageResult(
                candidate_stage_run_id=run_id,
                structured_result=result,
                recording_url=payload.get("recording_url"),
            )
        )
        self._s.flush()

        job_candidate = self._s.get(JobCandidate, call.job_candidate_id)
        candidates = CandidateService(self._s, self._actor)
        for key in _FACT_KEYS:
            if key in result and result[key] is not None:
                candidates.record_fact(
                    job_candidate, key, str(result[key]),
                    source="stage_run", source_stage_run_id=run_id,
                )

        # Result received → human review before a hiring decision.
        from app.modules.candidates.models import CandidateStageRun

        run = self._s.get(CandidateStageRun, run_id)
        if run is not None and run.status == StageRunState.AWAITING_RESULT.value:
            WorkflowExecutionService(self._s, self._actor).request_human_review(
                run, reason="structured result received"
            )
        job = self._s.get(Job, job_candidate.job_id)
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="interview.result_stored", entity_type="call", entity_id=call.id,
        )
