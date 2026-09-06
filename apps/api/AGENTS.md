# Codex / Antigravity — `apps/api` (FastAPI backend)

The FastAPI + Python modular monolith lives here (scaffolded F-005; app at `app/main.py`,
routers under `app/api/`, services per module, migrations per module). See `apps/api/README.md`.

## Before working here

Read the root `AGENTS.md` (Codex) or `.agents/rules/project-context.md` (Antigravity) first,
then:

- `PROJECT.md`, `docs/agent-handbook.md`, `docs/quality.md`, `docs/task-intake.md`
- `docs/architecture.md` — modular-monolith boundaries, canonical stage-driven model,
  ownership split (WorkflowExecutionService / Celery / Hunar).
- `docs/domain.md` — entities and state machines (persisted, auditable transitions).
- `docs/interfaces.md` — API, auth, error, webhook/idempotency, background-job contracts.
- `docs/vendor-capability-matrix.md` — before touching the Hunar or Apollo adapters.

## Backend-specific expectations

- Modular monolith, not microservices. PostgreSQL = truth; Redis = ephemeral; Celery =
  durable async; Hunar = candidate conversation.
- Thin Hunar/Apollo adapters; methods match `VERIFIED` endpoints only; never invent vendor
  behavior.
- Webhooks: lightweight handler, persist raw + dedup, enqueue; duplicates never
  double-advance state.
- Distinguish business vs infrastructure retries; enforce calling windows before business
  attempts; never lose state silently.
- Secrets server-side only; add OpenTelemetry + Sentry for external calls, background work,
  and state transitions.
