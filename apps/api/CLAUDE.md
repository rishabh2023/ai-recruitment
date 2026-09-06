# Claude Code — `apps/api` (FastAPI backend)

The FastAPI + Python modular monolith lives here (scaffolded F-005; app at `app/main.py`,
routers under `app/api/`, services per module, migrations per module). See `apps/api/README.md`.

## Before working here

Read the root `CLAUDE.md` first, then:

- `PROJECT.md`, `docs/agent-handbook.md`, `docs/quality.md`, `docs/task-intake.md`
- `docs/architecture.md` — modular-monolith boundaries, the canonical stage-driven execution
  model, and ownership split (WorkflowExecutionService / Celery / Hunar).
- `docs/domain.md` — entities and state machines (persisted, auditable transitions).
- `docs/interfaces.md` — API, auth, error, webhook/idempotency, and background-job contracts.
- `docs/vendor-capability-matrix.md` — before touching the Hunar or Apollo adapters.

## Backend-specific expectations

- Modular monolith, not microservices. Modules talk through in-process service interfaces.
- PostgreSQL is the durable source of truth; Redis is ephemeral coordination; Celery owns
  durable async execution; Hunar owns candidate-facing conversation.
- Thin Hunar/Apollo adapters — no generic multi-provider framework. Adapter methods must
  match `VERIFIED` endpoints; never invent vendor behavior.
- Webhooks: lightweight handler, persist raw + dedup, enqueue processing; duplicates never
  double-advance state.
- Distinguish business vs infrastructure retries. Enforce calling windows before business
  attempts. Never lose state silently — every failure has state/reason/retryability/next
  action/audit.
- Secrets server-side only. Add OpenTelemetry spans and Sentry reporting for external calls,
  background work, and state transitions.
