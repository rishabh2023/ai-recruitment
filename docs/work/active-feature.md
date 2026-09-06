# Active Feature — Handoff

This file is the resume point for any agent. Keep it current.

- **Active feature:** Auth (login + signup), candidate import + timeline UI, dashboard shell,
  **JD-from-PDF upload**, and **real Claude Haiku JD extraction** all done. Next: Phase 4
  (Apollo) or live Hunar, transition-policy auto PASS/REJECT, per-role widgets.
- **Current agent:** Claude Code
- **Branch / worktree:** repository root (`main`); commits `6dffa77` (baseline), `7640f2c`
  (auth), `cdd8190` (candidate/timeline UI), `62fa2b2` (signup/dashboard), + this session's
  PDF + Haiku commit.
- **Status:** Phases 0–3 + auth + candidate/timeline UI + dashboard + JD PDF + Claude LLM
  done. **66 API/py tests pass**; web builds + typechecks. Verified in-browser end to end.

## Sourcing — People Search & Outreach (Flow B), done this session

- **Backend:** new `app/modules/sourcing/` (`SourcingService`) + router
  `app/api/routers/sourcing.py`, exposing per-job endpoints:
  `GET /jobs/{id}/sourcing/suggested-query` (JD-derived starting query — title/location/
  skills/seniority from the latest extracted JD), `POST /jobs/{id}/sourcing/search`, and
  `POST /jobs/{id}/sourcing/add` (add selected external candidates to the pipeline as
  SOURCED, deduped by (source, source_id) within the job, reusing `CandidateService`).
- **Provider strategy (Apollo 403 handled):** Apollo Search is plan-gated (403 on the Free
  plan), so a new **offline `sample` provider** (`app/integrations/people_search/sample.py`)
  returns deterministic, clearly-labelled sample profiles so Flow B is demonstrable without a
  paid key. `SourcingService.search` uses the configured provider (`PEOPLE_SEARCH_PROVIDER`,
  default `sample`) and, if a real provider is unreachable/plan-gated/unconfigured, **falls
  back to sample and flags `is_sample=true` with a plain notice** — never silently. Config:
  `people_search_provider`, `apollo_api_key` added to `app/config.py`. Registry now knows the
  `sample` (no-key) provider.
- **Frontend:** Sourcing nav item enabled; new `/sourcing` page (`apps/web/app/sourcing/`).
  Role picker (JD-prefilled filters), comma-separated title/location/seniority/skills/keyword
  filters, results with select-all + per-row checkboxes, "Add N to pipeline", sample-data
  banner, empty/loading/error/pager states. Sourced search results have no contact details
  ("contact via enrichment" — mirrors real providers; enrichment is Phase 4). `lib/api.ts`
  gains `suggestedQuery`/`peopleSearch`/`addSourced` + types.
- **Verification:** `tests/test_sourcing.py` (5) — suggested query, sample search+filtering,
  Apollo-requested→sample fallback (monkeypatched, network-free), add + dedup, empty-selection
  422. **Full suite 83 passed.** Web typecheck + production build pass. Browser-verified end
  to end on localhost:3000: login → Sourcing → JD-prefill → search (sample notice) → empty
  state → broaden → 9 results → select all → "7 added · 2 skipped (already in pipeline)".
## Sourcing Phase 4 — enrichment + outreach, done this session

- **Enrichment:** `POST /job-candidates/{id}/enrich` (`SourcingService.enrich`) reveals a
  sourced candidate's phone/email so an outreach call can be placed. Provider boundary gained
  `EnrichmentResult` + `enrich()`. The `sample` provider returns a deterministic, reserved
  test number (`+1-555-01xx`, `example.com` email) — never a real person. Apollo's `enrich`
  raises (its phone reveal is async via `/people/match` webhook + paid plan), so the service
  **degrades to the flagged sample contact** rather than failing. Writes phone/email to the
  Candidate + facts (provenance), moves `SOURCED → OUTREACH_PENDING`, audited. Idempotent.
- **Outreach:** reuses the existing `POST /job-candidates/{id}/launch` (Hunar dispatch); the
  launch endpoint now moves a `SOURCED`/`OUTREACH_PENDING` candidate to `CONTACTED` (audited).
- **Web:** candidate detail page shows **Enrich contact** when no phone, then **Start outreach
  call** (disabled until enriched); notice shows the revealed number and sample flag.
  `lib/api.ts` gains `enrichCandidate` + `EnrichResult`.
- **Verification:** `tests/test_sourcing.py` now 7 (enrich→outreach→CONTACTED, idempotent
  enrich, provider-unavailable→sample fallback). **Full suite 85 passed.** Web typecheck +
  build pass. Browser-verified end to end: SOURCED → enrich (`+1-555-1001`, OUTREACH_PENDING)
  → outreach (CONTACTED, call attempt, FAILED on the non-routable sample number → Retry).
- **Next (Phase 4b):** real Apollo enrichment via the async `/people/match` webhook once a
  paid/scoped key exists; until then the sample fallback keeps outreach demonstrable.

## Job hub — workflow + pipeline UI (done this session)

- `GET /jobs/{id}/workflow` returns the effective workflow (approved else latest draft) with
  full stage detail (purpose, execution_type, information_requirements, requires_human_approval,
  weighted criteria). New page `/jobs/[id]`: the **hiring workflow** as a connected stage flow
  (exec-type badges, "collects" chips, criteria + weights) and a **pipeline board** (columns =
  stages, cards = candidates in their current stage). Jobs list + dashboard link to this hub.
- Still POC-ish / next for "full product": in-UI stage & criteria **editing** (currently the
  draft is auto-generated then read-only), calling-window/language config UI, and
  decision/approval actions on NEEDS_REVIEW candidates (advance/reject with audited outcome).

## Calling policy — done this session

- `GET/PUT /jobs/{id}/calling-policy` persists the job's allowed days, calling window, IANA
  timezone, attempts, retry interval, and preferred Hunar-agent language. It validates the
  verified Hunar constraints (a complete guardrail: timezone, start/end, at least three days,
  at least a three-hour window; supported retry intervals/languages; 1–10 total attempts).
  It audits each save, and `HunarDispatchService` maps the policy into `guardrails` and
  `retry_config` when making a live call.
- The job hub renders a saved calling-policy card. It explicitly says that language is
  agent-level and is only a stored preference pending a future agent-configuration update; it
  is not a per-call override. Browser verified through signup → job creation → save policy;
  the workflow 404 was intentionally rendered as the empty-workflow state. Full test suite:
  **78 passed**; web typecheck and production build pass.
- Local demo caveat: the full test suite truncates the dev DB. It removed the prefilled demo
  user in this session; restored via `POST /dev/bootstrap` with
  `recruiter@demo.test` / `demo-password`.

## Create-job workflow UI refresh — done this session

- `/jobs/new` now presents the original server-backed create → extract → confirm → draft →
  edit → approve → activate journey as a four-step, responsive hiring-workflow wizard. It has
  visible progress/status states, constrained content cards, extraction-review context, and a
  clear approval/activation handoff; no job or workflow API/state transition changed.
- `WorkflowEditor` now uses labelled, responsive stage cards with execution type, purpose,
  collected information, human-approval guidance, weighted criteria, and accessible stage
  reorder controls. Native select controls receive the same dark field treatment as inputs.
- Verified after the change: `npm run typecheck`, `npm run build`, and browser flow through
  job creation, JD confirmation, and workflow drafting, including a 360px-wide visual check.

## Job workspace UI refresh — done this session

- `/jobs/{id}` is now an operational workspace with Overview, Workflow, Pipeline, and Calling
  policy tabs. A recruiter can reopen an unapproved draft, edit and save its stages, then
  approve it; approved versions are clearly read-only and activation remains server-gated.
- Browser verified the overview, tab navigation, draft editor, and a successful workflow save.

## JD PDF upload + Claude Haiku extraction — done this session

- **JD from PDF:** `POST /jobs/{job_id}/versions/upload` (multipart) extracts text with `pypdf`
  and runs the **same** JD-version path as pasting. Rejects non-PDF, >10 MB, and scanned/
  image-only PDFs (no extractable text) with clear 422s. Helper `app/api/pdf.py`. Web: the
  Create-Job "Job description" step now has a **Paste text / Upload PDF** toggle with a
  dropzone (`api.addVersionFromPdf`). Tests: `test_jd_pdf.py` (5).
- **Claude Haiku LLM:** `app/integrations/llm/anthropic_provider.py` (`AnthropicLLMProvider`)
  uses Claude (`claude-haiku-4-5`) for JD extraction when `PLATFORM_LLM_API_KEY` is set;
  otherwise the deterministic stub. Registry selects it; any API/parse error falls back to the
  stub so the flow never breaks. `.env`: `PLATFORM_LLM_API_KEY` (Anthropic sk-ant-… key) +
  `PLATFORM_LLM_MODEL` (default claude-haiku-4-5). Deps added: `pypdf`, `python-multipart`,
  `anthropic`. Tests: `test_llm_anthropic.py` (5, network-free via monkeypatch).

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
- **Hunar live calls WIRED INTO THE PRODUCT (2026-09-06):** the launch endpoint now places a
  real call. `HunarClient` has real HTTP; `HunarDispatchService` (`app/modules/interviews/
  dispatch.py`) resolves the agent (stage `HunarAgentConfig` → else `HUNAR_DEFAULT_AGENT_ID`),
  fills the agent's `required_variables` into `custom_data`, POSTs `/calls/`, and records the
  outcome on the Call; a Celery task (`app/tasks.py`, eager in dev) runs it. Verified live
  end-to-end via `POST /job-candidates/{id}/launch` → `dispatched:true` + real `hunar_call_id`,
  status synced SCHEDULED→CALLING→NO_ANSWER (a rejected call).
- **Automatic results via webhook (wired):** when `PUBLIC_BASE_URL` is set, each dispatched
  call registers Hunar `callback_config` (status/result/recording/summary → our
  `POST /webhooks/hunar`), so results/recordings post back automatically and ingest via the
  existing `WebhookService` (facts + run→NEEDS_REVIEW). Verified end-to-end in the UI: a
  COMPLETED call populated Evidence & Results (interested/expected_ctc/notice_period) and moved
  the stage to NEEDS_REVIEW. In local dev a public URL needs a tunnel (`cloudflared tunnel
  --url http://localhost:8000`); the free quick-tunnel is flaky, so `POST /calls/{id}/sync`
  ("Sync from Hunar" button) is the reliable on-demand fallback (same ingestion code). In prod,
  set `PUBLIC_BASE_URL` to the deployed https domain — no tunnel, fully automatic.
- **Rejected / unanswered handling:** a terminal not-connected call (NO_ANSWER/FAILED/CANCELLED)
  with no result moves the run AWAITING_RESULT→FAILED with a reason + audit (never stuck);
  RETRY_SCHEDULED (retries left) keeps it AWAITING_RESULT. Re-launching a FAILED/CANCELLED run
  starts a **fresh** run (UI shows "Retry call"). Results/recordings still arrive async via the
  webhook; `POST /calls/{id}/sync` pulls status on demand when no public webhook URL is set.
- **Safety:** live calls fire ONLY when `HUNAR_LIVE_CALLS_ENABLED=1` AND a key is set (default
  off); tests force these off in conftest so the suite never dials. Celery eager by default (no
  worker needed); set `CELERY_TASK_ALWAYS_EAGER=0` + run `celery -A app.tasks worker` in prod.
- **Test suite truncates the dev DB:** the HTTP test fixtures run `TRUNCATE organizations …
  CASCADE`, so running `pytest` against the same `DATABASE_URL` used for a live demo wipes
  demo data (incl. the demo account). Re-seed the demo account after a full test run, or use a
  separate test database. Worth fixing later (dedicated test DB / transactional client).
- **Local Postgres:** this session Docker Desktop was down, so a local `postgresql@14` (brew)
  was started and a `recruitment` role/db provisioned + migrated. The compose Postgres path
  still works when Docker is running.

## Exact next action

Ask which to do next: (a) implement the Sourcing and Settings product flows, (b) adopt
shadcn/ui + per-role dashboard widgets, (c) Phase 4 people-search outreach (needs a working
provider key), or (d) wire live Hunar via Celery (needs a provisioned number). Current changes
are uncommitted on `main`; preserve the existing calling-policy work when integrating.

## How to run (demo)

```
docker compose up -d postgres
cd apps/api && . .venv/bin/activate && export DATABASE_URL=postgresql://recruitment:recruitment@localhost:5432/recruitment
alembic upgrade head && uvicorn app.main:app --reload      # :8000
cd ../web && cp .env.local.example .env.local && npm install && npm run dev   # :3000
```
