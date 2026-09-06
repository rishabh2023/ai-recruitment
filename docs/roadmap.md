# Roadmap

Every intended product capability from the architecture reference is **preserved** and
phased safely. Features are separated into milestones, not dropped. Each phase should be
solid before the next begins.

## Phase 0 — Verify Hunar contract  *(DONE — Hunar VERIFIED; Apollo VERIFIED by docs; live smokes gated on key/number — F-001)*

Verify, with evidence, before anything depends on them: authentication · agent create/update
· runtime/custom variables · outbound single call · bulk call · retry behavior · webhook
payloads/signatures · call/result retrieval · structured result/evaluation schema · language
support · documented recording behavior · call statuses · BYO telephony. Also verify the
Apollo contract (auth, search params, returned fields, contact availability, limits).
Outcome: `docs/vendor-capability-matrix.md` updated with `VERIFIED`/`UNKNOWN`/`UNSUPPORTED`
and evidence. **Feature:** `docs/features/F-001-hunar-contract-verification.md`.

## Phase 1 — Core data model and state transitions  *(DONE — models + per-module Alembic + WorkflowExecutionService, 23 tests; F-002)*

Lock the entities and state machines in `docs/domain.md`: Organization, User, Job, Job
Version, Job Workflow + Workflow Version + Workflow Stage, Candidate, Job Candidate,
Candidate Stage Run, Rubric/Stage Criteria, Candidate Fact (field-level provenance), Call,
Call Attempt, Interview, Result/Evidence, Webhook Event, Audit Event, Calling Policy,
Workflow Templates. Persisted, auditable transitions for stage-run and call lifecycles.

## Phase 2 — Job creation → confirmed JD → approved workflow/rubric  *(service slice DONE — JobService/WorkflowService + LLM adapter, 29 tests; API/UI pending app scaffold; F-003)*

Create job → provide/upload JD → extract & normalize → **recruiter confirms details** →
resolve existing workflow **or** AI-draft one (bootstrap) → review/customize stages and
stage criteria → **recruiter approves** → activate. Human approval gate before any provisioning.
Includes the organization workflow-template library and per-job versioned workflow snapshot.

## Phase 3 — Existing candidate → interview → webhook → evidence → review  *(service slice DONE — import→launch→idempotent webhook→result→review + carry-forward, 38 tests; live call + API/UI pending; F-004)*

Import/add existing candidates (progressive profile, completeness indicator) → choose
starting stage where justified (audited) → pre-launch review → calling-policy check → Celery
→ Hunar AI stage → webhook → validate → persist structured result + evidence → stage
transition → recruiter review → pipeline decision. Completes the Journey-1 critical path.
Includes candidate detail (profile / hiring journey / evidence) and the pipeline board as a
view over persisted state.

## Phase 4 — People search → outreach → progressive profile enrichment  *(DONE — real multi-provider sourcing + enrich + outreach; F-006)*

Build search criteria (JD-derived) → provider search → recruiter selects a provider and
candidates → add to job at `SOURCED` (deduped) → enrich contact (reveal phone/email via the
source provider) → outreach call → `CONTACTED`. **Real data only** across four implemented
providers (Apollo/PDL/Proxycurl/Coresignal); no sample fabrication — unconfigured/plan-gated
providers surface honest errors. **PDL verified live.** Deeper enrichment (resume request via a
verified follow-up mechanism) stays gated on verified support.

**App scaffold (F-005):** FastAPI routers + Next.js recruiter console expose the flow over
HTTP; real session-cookie auth, candidate/timeline UI, job hub, Sourcing, and Settings are all
built. Remaining: shadcn/ui component styling and deployment.

**Settings + team invites (F-007):** per-org provider API keys (write-only), default provider,
live-calling toggle, team roster, and invitations (one-time link → set password → join).

**MCP server (F-008):** the platform is exposed as ~31 MCP tools (incl. Flow A/B one-shot
macros) for conversational use from Claude Code / ChatGPT.

## Phase 5 — Production hardening

Redis/Celery robustness · webhook idempotency at scale · calling windows & timezone
resolution · retry UX (business vs infrastructure) · centralized retry engine with
configurable policy · manual overrides/skips with consequence preview and audit ·
carry-forward of unresolved information across stages · OpenTelemetry · Sentry · metrics ·
audit timeline · authorization hardening · rollback/recovery. Also: combined single-call
stages and human/system stage execution types.

## Phase 6 — Attendance / workforce module

The separate workforce/attendance module (assignment Question 3), built only after Journeys
1 and 2 are solid.

## Preservation note

Capabilities deferred but preserved: multilingual conversations (verified-only), call
recording/transcript display (documented fields only), BYO telephony (only if Hunar supports
it), LangSmith LLM tracing (only if platform-side LLM workflows become substantial),
Prometheus/Grafana metrics (optional), resume acquisition via SMS/email/upload (only with
verified communication support), semantic candidate ranking. None are dropped; each is gated
on verification or on an earlier phase being stable.
