# Active Feature — Handoff

This file is the resume point for any agent. Keep it current.

- **Active feature:** App scaffold done (F-005) — FastAPI + Next.js now expose Phases 2–3.
  Next: real auth, shadcn/ui + candidate/timeline UI, Phase 4 (Apollo), or live Hunar.
- **Current agent:** Claude Code
- **Branch / worktree:** repository root; `git init` done, no commits yet
- **Status:** Phases 0–3 service layer + HTTP/UI scaffold done. **41 API/py tests pass**; web
  builds + typechecks. No real auth; no live Hunar call (needs provisioned number).

## Completed work

- **F-001 (Phase 0):** Hunar contract VERIFIED (docs+OpenAPI+read-only live). Apollo verified
  from docs; adapter `search()` wired. Live Apollo: key valid but Search endpoint 403 (Free
  plan) — needs paid plan or a different provider (multi-provider by ADR-0001).
- **F-002 (Phase 1) — DONE:**
  - 25 SQLAlchemy models under `apps/api/app/modules/<name>/models.py`, shared `Base`.
  - Per-module Alembic migrations (Django-app style) — one linear history; reversible
    round-trip verified on Postgres 16.
  - `apps/api/app/workflow_execution/`: pure `state_machine.py` (legal transitions + outcome
    mapping) and `WorkflowExecutionService` (enforced transitions, audit on every move,
    candidate advancement, explicit audited overrides).
  - Tests in `apps/api/tests/` — **23 passing** (pure unit + DB-backed service).
  - Docs updated to match: `architecture.md` (realized layout + WorkflowExecutionService),
    `domain.md` (enforced transitions + outcomes), `apps/api/README.md`, roadmap, INDEX.

## Verification

- `python -m pytest -q` → **38 passed** (Postgres up, `DATABASE_URL` set).
- `alembic upgrade head` → 25 tables; `downgrade base`→0→`upgrade head`→25. 10 CHECKs enforce.
- Toolchain in `apps/api/.venv` (git-ignored): SQLAlchemy 2.0.52, Alembic 1.19.2,
  psycopg 3.3.5, pytest 9.1.1 (pinned in `requirements.txt`).

## Phase 2 (F-003) — done this session

- LLM boundary `app/integrations/llm/` (protocol + deterministic offline stub + registry).
- `JobService` (create → add JD version w/ extraction → confirm → activate, gated) and
  `WorkflowService` (draft/adopt/approve; unapproved until human). Shared `audit/log.py`.
- Gates enforced: activation blocked unless latest JD confirmed AND a workflow version approved.
- `tests/test_job_creation.py` (6 tests). Full suite **29 passed**. Docs updated
  (architecture realized layout, interfaces LLM boundary, roadmap, INDEX, F-003).

## Phase 3 (F-004) — done this session

- `CandidateService.import_candidate` (facts+provenance; later starting stage audited),
  `InterviewService.launch_ai_stage` (Call + attempt, run→AWAITING_RESULT, Hunar payload with
  effective-info `custom_data.collect`), `WebhookService.handle_hunar_event` (idempotent,
  status normalize, StageResult, fact enrichment, run→NEEDS_REVIEW).
- Pure `compute_effective_information` (carry-forward) + Hunar status map + payload builder.
- Tests `test_effective_info.py` + `test_interview_flow.py`. Full suite **38 passed**.

## App scaffold (F-005) — done this session

- FastAPI: `app/main.py`, `app/config.py`, `app/db/session.py`, `app/api/` (routers, deps,
  errors, schemas). Routers: jobs, candidates, interviews, webhooks, system (`/health`,
  `/dev/bootstrap`). Dev-stub auth via `X-Org-Id`/`X-User-Id`. `tests/test_api.py` (HTTP e2e).
- Next.js (`apps/web`): dashboard + guided job-creation flow + typed `lib/api.ts`. Plain CSS
  (shadcn/ui intended next; no Tailwind). `npm run build` + `npm run typecheck` pass.

## Docker (this session)

- `apps/api/Dockerfile` + `docker-entrypoint.sh` (runs `alembic upgrade head` when
  `RUN_MIGRATIONS=1`, then uvicorn). `compose.yaml` `api` service imports root `.env`
  (`env_file`) and overrides `DATABASE_URL`/`REDIS_URL` to the compose services; healthcheck
  on `/health`. Fixed `requirements.txt` → `psycopg[binary]` (slim image had no libpq).
- Verified: `docker compose up -d --build api` → healthy; `/health` 200; bootstrap + create
  job work; `.env` keys present in container.

## Remaining work

1. **Real auth** (replace header stub); **shadcn/ui components**; candidate import + timeline
   **UI** (backend endpoints already exist).
2. **Live Hunar:** POST the built payload in a Celery task once a phone number is provisioned.
3. **People search:** enable/upgrade Apollo key (403) or switch provider; then Phase 4 outreach.
4. Transition-policy JSON evaluation (auto PASS/REJECT); calling-window/guardrails scheduling;
   deployment.

## Risks / open questions

- Apollo Search 403 (key lacks API access). Provider choice pending.
- No provisioned Hunar number → no live outbound call; Hunar key time-limited (~3 days from 2026-09-04).
- No HTTP app yet — Phases 2–3 are service-layer only.

## Exact next action

Ask which to do next: (a) polish the UI (shadcn/ui + candidate import/timeline screens),
(b) real auth, (c) Phase 4 people-search outreach (needs a working provider key), or (d) wire
live Hunar via Celery (needs a provisioned number). Default: candidate/timeline UI.

## How to run (demo)

```
docker compose up -d postgres
cd apps/api && . .venv/bin/activate && export DATABASE_URL=postgresql://recruitment:recruitment@localhost:5432/recruitment
alembic upgrade head && uvicorn app.main:app --reload      # :8000
cd ../web && cp .env.local.example .env.local && npm install && npm run dev   # :3000
```
