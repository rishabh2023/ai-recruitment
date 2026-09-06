# F-004: Interview Execution Flow (import → launch → webhook → result → review)

- **Status:** Done (service-layer slice) — 38 tests pass; live Hunar call needs a provisioned
  number; API/UI slice deferred
- **Risk tier:** High Risk (external integration, webhooks, candidate data, state)
- **Documentation-impact level:** 2
- **Affected areas:** `apps/api/app/modules/{candidates,interviews,webhooks}/service.py`,
  `apps/api/app/integrations/hunar/mapping.py`, `apps/api/app/workflow_execution/effective_info.py`
- **Depends on:** F-002 (state machine + models), F-003 (active job + approved workflow)

## Problem / intent

Phase 3 — the critical Q1 path: an existing candidate is imported (progressive profile +
provenance), an AI stage is launched as a Hunar call intent (effective context via
carry-forward), Hunar's webhook is ingested idempotently, the structured result is stored,
candidate facts are enriched, and the run moves to human review before a hiring decision.

## Scope

**In scope**

- `CandidateService.import_candidate` (known facts as `candidate_facts`; optional later
  starting stage, explicit + audited).
- Carry-forward `compute_effective_information` (pure) and Hunar status mapping / call-payload
  builder (pure).
- `InterviewService.launch_ai_stage` — persists Call + attempt, moves run to AWAITING_RESULT,
  returns the exact Hunar `POST /calls/` payload (not sent live).
- `WebhookService.handle_hunar_event` — idempotent ingest, status normalization, result
  storage, fact enrichment, run → NEEDS_REVIEW.

**Out of scope**

- Actually POSTing to Hunar / Celery wiring (needs a provisioned number); FastAPI/UI; Apollo
  outreach (Phase 4); transition-policy JSON evaluation.

## Acceptance criteria

- [x] Import creates candidate + participation + first stage run (READY) + facts w/ provenance.
- [x] Starting at a later stage is explicit and audited.
- [x] Launch requires a phone; builds `custom_data.collect` from effective info (known fields
      excluded); run → AWAITING_RESULT.
- [x] Webhook result stores `StageResult`, enriches `candidate_facts`, run → NEEDS_REVIEW.
- [x] Duplicate webhook is a no-op (one event, one result, no double-advance).
- [x] Recruiter review PASS advances to the next stage.

## Evidence

`apps/api/tests/test_effective_info.py` + `tests/test_interview_flow.py`; full suite
**38 passed** (2026-09-06).

## Remaining limitations / open questions

- No live Hunar POST (needs a provisioned number + Celery task); the payload is built and
  persisted as intent.
- Result → outcome is human-reviewed (NEEDS_REVIEW); automatic PASS/REJECT from a stage's
  `transition_policy` JSON is a later slice.
