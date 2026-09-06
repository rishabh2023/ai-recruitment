# Active Feature — Handoff

This file is the resume point for any agent. Keep it current.

- **Active feature:** Auth (login + **signup**), candidate import + timeline UI, and a
  product **dashboard shell with sidebar** all done. Next: Phase 4 (Apollo) or live Hunar,
  transition-policy auto PASS/REJECT, per-role widget/permission differences.
- **Current agent:** Claude Code
- **Branch / worktree:** repository root (`main`); commits `6dffa77` (baseline), `7640f2c`
  (auth), `cdd8190` (candidate/timeline UI), + this session's signup/dashboard commit.
- **Status:** Phases 0–3 + auth + candidate/timeline UI + dashboard shell done. **56 API/py
  tests pass**; web builds + typechecks. Verified in-browser end to end.

## Signup + dashboard shell — done this session

- **Signup:** `POST /auth/signup` (name, email, password, optional org_name) → creates a new
  org + first **admin** user, logs them in (cookie). Email globally unique (409 on dup);
  `auth.create_account` (HTTP-free) + `EmailTakenError`. `/auth/me` and login/signup now
  return name + email. Tests in `test_auth.py` (signup, dup, dashboard summary). 56 pass.
- **Dashboard API:** `GET /dashboard/summary` (org-scoped counts: total/active jobs,
  candidates in pipeline, needs_review, awaiting_result, failed_calls) and
  `GET /dashboard/activity` (last 15 audit events). New router `app/api/routers/dashboard.py`.
- **Web shell:** `lib/auth.tsx` (AuthProvider/useAuth), `components/AppShell.tsx` (sidebar:
  Dashboard, Jobs, Sourcing/Settings=soon; user footer + sign out; mobile-collapsing),
  `components/AuthScreen.tsx` (Sign in / Create account tabs, demo creds pre-filled). Root
  layout wraps everything; unauthenticated → AuthScreen. Pages: `/` = action-oriented
  dashboard (stat widgets + active jobs + recent activity + Create Job CTA), `/jobs` = jobs
  list. Candidate list/detail pages now render inside the shell.
- **Demo creds:** `recruiter@demo.test` / `demo-password` (pre-filled on the sign-in tab).

## Real auth (session cookies) — done this session

- Mechanism: HttpOnly + SameSite=Lax session cookie backed by a `user_sessions` table
  (Postgres, durable + revocable). Endpoints `POST /auth/login`, `POST /auth/logout`,
  `GET /auth/me` (`app/api/routers/auth.py`). `deps.get_principal` now resolves the cookie.
- Passwords: PBKDF2-HMAC-SHA256, stdlib only (`app/security/passwords.py`); `users.password_hash`
  added (nullable). Only a SHA-256 hash of each session token is stored. Login is
  case-insensitive on email and non-enumerating (wrong password == unknown user == no-password).
- `POST /dev/bootstrap` now sets a password so you can then log in; CORS `allow_credentials=True`.
- Config: `SESSION_COOKIE_NAME`, `SESSION_COOKIE_SECURE` (must be 1 in prod), `SESSION_TTL_HOURS`.
- Web: `lib/api.ts` uses `credentials:"include"` + `me/login/logout`; dashboard has a real
  sign-in form (+ "create demo org" dev convenience) and sign-out. shadcn/ui still not added.
- Migration `app/modules/organizations/migrations/b1f2c3d4e5f6_users_password_and_sessions.py`
  (down_revision `4dfb8fbd7911`). Tests: `tests/test_auth.py` (12) + `test_api.py` updated to
  log in.

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

1. **shadcn/ui components** (shell is currently hand-rolled CSS); **per-role** dashboard
   widgets/permissions (owner vs recruiter — arch §30/Q22); invite teammates + password-reset.
2. **Live Hunar:** POST the built payload in a Celery task once a phone number is provisioned.
3. **People search:** enable/upgrade Apollo key (403) or switch provider; then Phase 4 outreach.
4. Transition-policy JSON evaluation (auto PASS/REJECT); calling-window/guardrails scheduling;
   deployment.

## Risks / open questions

- Apollo Search 403 (key lacks API access). Provider choice pending.
- No provisioned Hunar number → no live outbound call; Hunar key time-limited (~3 days from 2026-09-04).
- **Test suite truncates the dev DB:** the HTTP test fixtures run `TRUNCATE organizations …
  CASCADE`, so running `pytest` against the same `DATABASE_URL` used for a live demo wipes
  demo data (incl. the demo account). Re-seed the demo account after a full test run, or use a
  separate test database. Worth fixing later (dedicated test DB / transactional client).
- **Local Postgres:** this session Docker Desktop was down, so a local `postgresql@14` (brew)
  was started and a `recruitment` role/db provisioned + migrated. The compose Postgres path
  still works when Docker is running.

## Exact next action

Ask which to do next: (a) adopt shadcn/ui + per-role dashboard widgets,
(b) Phase 4 people-search outreach (needs a working provider key), or (c) wire live Hunar via
Celery (needs a provisioned number). Default: candidate/timeline UI.

## How to run (demo)

```
docker compose up -d postgres
cd apps/api && . .venv/bin/activate && export DATABASE_URL=postgresql://recruitment:recruitment@localhost:5432/recruitment
alembic upgrade head && uvicorn app.main:app --reload      # :8000
cd ../web && cp .env.local.example .env.local && npm install && npm run dev   # :3000
```
