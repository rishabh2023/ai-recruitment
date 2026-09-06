# API (FastAPI modular monolith)

Backend for the AI Recruitment Workflow platform. Phase 1 delivers the data layer; the
FastAPI app, services, and routes come in later phases.

## Layout (Django-app style)

```
apps/api/
├── requirements.txt
├── alembic.ini                 # version_locations = each module's migrations/ folder
├── alembic/                    # env.py + script template (shared Alembic runtime)
├── tests/                      # pytest (pure state-machine + DB-backed service tests)
└── app/
    ├── db/base.py              # shared SQLAlchemy Base + column helpers (one MetaData)
    ├── integrations/           # thin vendor adapters (hunar, people_search)
    ├── workflow_execution/     # WorkflowExecutionService + pure state machine (no models)
    └── modules/                # one package per domain "app"
        ├── registry.py         # module order + migration paths
        ├── organizations/  (models.py + migrations/)
        ├── jobs/           (models.py + migrations/)
        ├── workflows/      (models.py + migrations/)
        ├── candidates/     (models.py + migrations/)
        ├── interviews/     (models.py + migrations/)
        ├── webhooks/       (models.py + migrations/)
        ├── audit/          (models.py + migrations/)
        └── sourcing/       (models.py + migrations/)
```

Each module keeps its **own models and its own migrations folder**, like a Django app. All
models share one `Base`/`MetaData` (in `app/db/base.py`) so cross-module foreign keys resolve
and Alembic sees the whole schema. Alembic manages a single linear history across the
per-module folders (dependency order: organizations → jobs → workflows → candidates →
interviews → webhooks → audit → sourcing).

## Setup

```bash
cd apps/api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Migrations

Bring up the database and apply everything:

```bash
docker compose up -d postgres            # from repo root
cd apps/api && . .venv/bin/activate
export DATABASE_URL="postgresql://recruitment:recruitment@localhost:5432/recruitment"
alembic upgrade head
```

Create a new migration for a module (goes into that module's folder):

```bash
alembic revision --autogenerate -m "add X" --version-path app/modules/<module>/migrations
```

`DATABASE_URL` is read by `alembic/env.py` (a bare `postgresql://` is upgraded to
`postgresql+psycopg://`). The `ALEMBIC_MODULES` env var is only used to scaffold the initial
per-module migrations incrementally; leave it unset for normal work.

## Run the API

```bash
docker compose up -d postgres           # from repo root
cd apps/api && . .venv/bin/activate
export DATABASE_URL="postgresql://recruitment:recruitment@localhost:5432/recruitment"
alembic upgrade head                     # first time
uvicorn app.main:app --reload            # http://localhost:8000  (docs at /docs)
```

Dev auth is a stub: `POST /dev/bootstrap` returns an org + recruiter id; send them as
`X-Org-Id` / `X-User-Id` headers. Endpoints (Phase 2–3): `POST /jobs`, `GET /jobs`,
`POST /jobs/{id}/versions`, `.../confirm`, `POST /jobs/{id}/workflow/draft`,
`.../approve`, `POST /jobs/{id}/activate`, `POST /jobs/{id}/candidates`,
`POST /job-candidates/{id}/launch`, `GET /job-candidates/{id}/timeline`,
`POST /webhooks/hunar`. Errors follow `{ error: { code, message, request_id } }`.

## Docker

The backend is containerised (`apps/api/Dockerfile`) and wired into the root `compose.yaml`
as the `api` service (with `postgres` + `redis`).

```bash
docker compose up -d --build api          # from repo root
curl localhost:8000/health                # {"status":"ok"}
```

- The image installs `requirements.txt`, copies `app/` + `alembic/`, and runs
  `docker-entrypoint.sh`, which applies migrations when `RUN_MIGRATIONS=1` (set by compose)
  then starts uvicorn on `0.0.0.0:8000`.
- Configuration: compose imports the root **`.env`** directly (`env_file: .env`) so vendor
  keys (Hunar/Apollo/LLM) flow in, and overrides `DATABASE_URL` / `REDIS_URL` so the
  container reaches the `postgres` / `redis` services instead of localhost.
- A container healthcheck polls `/health`. Rebuild after dependency changes with
  `docker compose up -d --build api`.

## Tests

```bash
docker compose up -d postgres            # from repo root (DB-backed tests need it)
cd apps/api && . .venv/bin/activate
export DATABASE_URL="postgresql://recruitment:recruitment@localhost:5432/recruitment"
PYTHONPATH=. python -m pytest -q
```

Pure state-machine tests run without a DB; service tests use a transaction rolled back per
test (no pollution) and skip cleanly if Postgres is unreachable.

## Verified (Phase 1, 2026-09-06)

`alembic upgrade head` builds 25 tables on Postgres 16; `downgrade base` → 0 tables and
`upgrade head` → 25 again (reversible). 10 named CHECK constraints present; invalid enum
values rejected. `WorkflowExecutionService` enforces stage-run transitions (raises
`InvalidTransition`), audits every move, and advances candidates — **23 tests pass**. See
`docs/features/F-002-core-data-model.md`.
