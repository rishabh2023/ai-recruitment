# F-002: Core Data Model & State Transitions

- **Status:** Done — SQLAlchemy models + per-module Alembic (round-trip verified) and the
  WorkflowExecutionService with enforced state transitions + audit (23 tests passing)
- **Risk tier:** High Risk (data model + migrations)
- **Documentation-impact level:** 3 (data model)
- **Affected areas:** `apps/api/migrations/`, `docs/domain.md`
- **Depends on:** F-001 (verified vendor contract informs call/result/status fields)
- **Owner / current agent:** Claude Code

## Problem / intent

Phase 1: establish the durable business source of truth — the entities and state fields for
the stage-driven hiring model in `docs/domain.md` (§57 hierarchy), so later phases build on a
stable, auditable schema.

## Scope

**In scope**

- SQLAlchemy models for the full core entity set (25 tables), organized per module
  (Django-app style) under `app/modules/<name>/models.py`, sharing one `Base`/`MetaData`.
- Alembic with per-module `migrations/` folders (each app owns its migrations); one linear
  history across them.
- State fields as `TEXT` + `CHECK`; idempotency and provenance modeled.

**Out of scope (next slices)**

- Application-level state-transition enforcement (WorkflowExecutionService).
- Seed/fixture data and repository/service layers; the FastAPI app itself.

## Acceptance criteria

- [x] SQLAlchemy models mirror the domain (25 tables register in one metadata).
- [x] Per-module Alembic migrations generated into each app's `migrations/` folder.
- [x] `alembic upgrade head` builds 25 tables on Postgres 16.
- [x] `downgrade base` → 0 tables, `upgrade head` → 25 (reversible round-trip).
- [x] Named CHECK constraints present (10) and reject invalid values (e.g. stage-run status).
- [x] Linear history in dependency order (organizations → … → sourcing).
- [x] Application-level valid-transition enforcement (`WorkflowExecutionService` + pure state
      machine) with audit on every move; overrides explicit/audited.
- [x] Tests: 23 passing (pure state-machine unit tests + DB-backed service tests).

## Evidence

See `apps/api/README.md` → "Verified" and `docs/work/active-feature.md`. Migrations:
`app/modules/<module>/migrations/*_initial.py`. Round-trip + constraint checks captured
2026-09-06 against compose Postgres 16.

## Remaining limitations / open questions

- Transition *policy evaluation* (deriving PASS/REVIEW/REJECT from a stage's
  `transition_policy` + result) is stubbed to an explicit `StageOutcome` argument; parsing the
  policy JSON belongs to a later slice (Phase 2/3).
- Effective-information/carry-forward computation (`candidate_facts`) is modeled but not yet
  implemented as a service.
- Future migrations go through
  `alembic revision --autogenerate --version-path app/modules/<module>/migrations`.
