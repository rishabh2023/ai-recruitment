# Architecture

## Shape: modular monolith

One FastAPI application, internally partitioned into modules with clear boundaries. Not
microservices. Modules communicate through in-process service interfaces, share one
PostgreSQL database, and enqueue durable work to Celery via Redis.

```
Next.js (Recruiter UI)
        ↓
FastAPI Modular Monolith
  ├── Auth
  ├── Jobs
  ├── Workflows            (templates, versions, stages)
  ├── Candidates
  ├── Pipeline
  ├── Sourcing             (people search + outreach; Apollo/PDL/Proxycurl/Coresignal)
  ├── Interviews
  ├── Evaluation
  ├── Calling Policy
  ├── Settings             (org config: provider keys, default, live-calling, team invites)
  ├── Webhook
  ├── WorkflowExecutionService  (owns candidate stage progression)
  ├── Integrations
  │     ├── Hunar Adapter
  │     ├── People-search Adapters   (4 providers, real; search + enrich)
  │     └── LLM Adapter    (platform-side product intelligence only)
  ├── Workers (Celery tasks)
  └── Observability
        ↓
PostgreSQL  •  Redis + Celery
        ↓
Hunar API   •   People-search APIs   •   LLM
```

An **MCP server** (`apps/mcp`) wraps the same HTTP API as ~31 tools so the platform can be
driven conversationally from Claude Code / ChatGPT (stdio + streamable-http). It is a client of
the API, not part of the monolith — all gates/auth/audit still apply.

### Realized backend layout (`apps/api`)

The monolith is organized Django-app style — each domain module owns its models **and** its
migrations; cross-cutting services and adapters sit alongside:

```
apps/api/
├── alembic.ini · alembic/            # one Alembic runtime; version_locations = each module's migrations/
└── app/
    ├── Dockerfile · docker-entrypoint.sh  # containerised API (migrates then serves); `api` service in compose.yaml
    ├── main.py                       # FastAPI app (create_app, routers, CORS, error handlers)
    ├── config.py                     # env-driven settings
    ├── api/                          # HTTP layer: routers/, deps.py (principal), errors.py, schemas.py
    ├── db/base.py                    # shared SQLAlchemy Base / MetaData + column helpers
    ├── db/session.py                 # engine + request-scoped session (commit/rollback)
    ├── modules/                      # one package per domain "app": models.py (+ service.py) + migrations/
    │   ├── organizations · jobs · workflows · candidates
    │   ├── interviews · webhooks · audit · sourcing
    │   ├── jobs/service.py           # JobService: create/JD-version/confirm/activate (gated)
    │   ├── workflows/service.py      # WorkflowService: draft/adopt/approve (unapproved until human)
    │   ├── candidates/service.py     # CandidateService: import + facts/provenance + starting stage
    │   ├── interviews/service.py     # InterviewService: launch AI stage → Hunar call intent
    │   ├── webhooks/service.py       # WebhookService: idempotent ingest → result → facts → review
    │   ├── audit/log.py              # shared write_audit()
    │   └── registry.py               # module order + migration paths
    ├── workflow_execution/           # WorkflowExecutionService + state machine + effective_info (carry-forward)
    └── integrations/                 # thin vendor adapters
        ├── hunar/                    # single voice provider (verified surface, webhook verifier, status map + payload builder)
        ├── people_search/            # 4 real providers (apollo, pdl, proxycurl, coresignal) + base/registry; sample only for tests
        └── llm/                      # platform product-intelligence only (offline stub; real Claude Haiku provider)
```

`modules/organizations/` also holds `settings_service.py` (org config: provider keys, default
provider, live-calling) and `invites.py` (team invites); `modules/sourcing/service.py` is
`SourcingService` (search / add-to-pipeline / enrich — real providers only, no fabrication).
Sibling app `apps/mcp/` is the MCP server (client of the API, own venv).

The frontend lives in `apps/web` (Next.js App Router + TypeScript): `app/` pages (dashboard,
guided job creation), `lib/api.ts` typed client. It renders state and calls the API — never the
source of truth (docs/experience.md).

Not every package owns tables: `workflow_execution` and `integrations` are logic-only.
Migrations form one linear Alembic history across the per-module folders (dependency order:
organizations → jobs → workflows → candidates → interviews → webhooks → audit → sourcing).

## Component responsibilities

| Component        | Owns                                                                 |
| ---------------- | ------------------------------------------------------------------- |
| **Next.js**      | Recruiter experience (built with shadcn/ui components); renders state, never the source of truth. |
| **FastAPI**      | Typed API contracts, authorization, domain/application services, workflow execution, webhook intake. |
| **PostgreSQL**   | Durable business source of truth (jobs, workflows, candidates, calls, results, audit). |
| **Redis**        | Ephemeral coordination only: Celery broker/backend, distributed locks, rate limiting, short-lived cache, dedup coordination. Never the sole store of hiring state. |
| **Celery**       | Durable async execution: call launches, bulk work, webhook processing, scheduled retries, agent/config provisioning. Survives request completion and restarts. |
| **Hunar adapter**| Thin, vendor-specific boundary. Centralizes auth, timeouts, retries, request/response shapes. No generic multi-provider framework. |
| **People-search adapters**| Thin per-provider boundary (Apollo/PDL/Proxycurl/Coresignal), `search()` + `enrich()`. Real data only — preserves provenance; unconfigured/plan-gated providers surface honest errors, never fabricated results. |
| **Settings / invites**| Per-org config (provider API keys [write-only], default provider, live-calling toggle) and team invitations (one-time accept link → set password → join). |
| **LLM adapter**  | Platform-side product intelligence only: JD understanding, role classification, structured skill extraction, draft workflow/rubric generation. Never candidate conversation, never duplicating Hunar evaluation. |
| **OpenTelemetry**| Distributed tracing across UI → API → DB → Redis → Celery → Hunar/Apollo → webhook processing. |
| **Sentry**       | Frontend errors, backend exceptions, Celery task failures, release correlation. |

## Why these choices (defense)

- **FastAPI, not Django** — the backend is API-first, integration- and webhook-heavy,
  orchestration-heavy, with a separate Next.js frontend and Celery for durable work.
  Django's batteries are not requirements here. The important decision is the
  modular-monolith boundary and reliable workflow execution, not the framework.
- **Celery, not FastAPI async alone** — async gives request-level I/O concurrency; it does
  not give durable background jobs, retries/backoff, crash recovery, worker isolation,
  scheduling, or operational visibility for queued work. Bulk call orchestration must
  survive request completion and restarts.
- **Redis for coordination, Postgres for truth** — hiring state is relational,
  transactional, durable, and auditable; Redis is ephemeral infrastructure.
- **Thin Hunar adapter, not a provider abstraction** — there is one required voice provider.
  Abstracting hypothetical providers is premature.
- **No deep-agent framework** — the workflow is deterministic orchestration; Hunar already
  owns the conversational agents.
- **One voice agent per stage intent, not one global agent** — each AI funnel stage binds to a
  Hunar agent that understands that stage's intent (role + purpose + fields to collect). A
  matching account agent is reused, or one is created at funnel setup; the generated result
  schema mirrors the stage's `information_requirements`. `HUNAR_DEFAULT_AGENT_ID` is a
  last-resort fallback only. See [F-009](features/F-009-per-stage-voice-agent-provisioning.md).
- **Small platform LLM** — only for product intelligence Hunar does not provide.

## Canonical execution model: stage-driven

The candidate-facing AI behavior is **computed per stage execution**, never a static
per-job agent:

```
Organization / Job context
+ Confirmed JD / Job Version
+ Approved Job Workflow Version
+ Current Stage Definition
+ Stage Success Criteria
+ Stage Information Requirements
+ Candidate Known Information
+ Unresolved Prior Requirements
+ Calling / Language Policy
= Effective Hunar Execution Context
```

Flow: `JD → resolve/draft job workflow → configure stages → candidate enters stage →
build effective stage context → Hunar executes conversation → structured result → validate
→ persist → evaluate transition → advance / review / reject / retry`.

Each stage declares an **execution type**: `AI` (Hunar executes), `HUMAN` (platform creates
a review/decision task), or `SYSTEM/OPERATIONAL` (deterministic/integration step). The
workflow engine orchestrates **work**, not only AI calls.

**Effective information requirement** carries unresolved fields forward:

```
Current Stage Requirements
+ Unresolved Required Information from Prior Stages
− Information Already Known with Acceptable Provenance
= Effective Information to Collect
```

This requires field-level provenance (`candidate_facts`), not a boolean
`screening_completed`. See `docs/domain.md`.

### Ownership boundaries within execution

- **WorkflowExecutionService** owns business progression and stage lifecycle.
- **Celery** owns durable asynchronous execution.
- **Hunar** owns candidate-facing conversation execution.

The **WorkflowExecutionService** is realized at `apps/api/app/workflow_execution/`:

- `state_machine.py` — a pure, I/O-free definition of the `candidate_stage_run` lifecycle
  (`PENDING → BLOCKED → READY → SCHEDULED → IN_PROGRESS → AWAITING_RESULT → NEEDS_REVIEW →
  COMPLETED | FAILED | CANCELLED | SKIPPED`) and the allowed transitions. It is the single
  source of truth for which moves are legal, and raises `InvalidTransition` otherwise. It also
  maps a `StageOutcome` (PASS/REVIEW/REJECT/RETRY/FAIL) to the resulting run state.
- `service.py` — `WorkflowExecutionService(session, actor_user_id)`: creates stage runs,
  performs **enforced** transitions (delegating legality to the state machine), evaluates
  outcomes, advances a candidate to the next configured stage (by `stage_order` within the
  approved workflow version), and writes an **audit event for every consequential move**.
  Overrides are explicit (`override_transition`, reason required) — they may bypass the normal
  path but are always audited with any unresolved requirements. The service never commits; the
  caller owns the transaction. Celery tasks and API handlers call this service — they do not
  mutate stage-run status directly.

The DB stores state (`TEXT` + `CHECK`); valid *transitions* live in code here. See
`docs/domain.md`.

### Hunar provisioning boundary (contract-dependent)

Do not assume every stage needs a separately persisted Hunar agent. Behavior depends on the
**verified** Hunar contract:

- If Hunar supports sufficient runtime/custom context → reuse a configured agent/template and
  pass stage/candidate context at execution time.
- If Hunar requires persistent configuration for materially different behavior → provision/
  update, then version and persist a mapping `job_workflow_stage_id → hunar_configuration_reference → configuration_version`.

This mapping is never exposed to recruiters.

## Conflicts resolved (source-of-truth rule)

The architecture reference contains historical reasoning (§1–44) and later refinements
(§45–70). Where they conflict, the **later stage-driven model is canonical**:

| Older statement | Canonical resolution |
| --------------- | -------------------- |
| "One job = one fixed Hunar agent" (§6.2) | Superseded by stage-driven effective context (§64). A per-stage config reference may exist, contract-dependent. |
| Single job-level success rubric (§5, §24) | Generalized: criteria belong primarily to the **stage** (§60). Job-level criteria may still exist as context. |
| Hardcoded pipeline `SOURCED…SHORTLISTED` (§23) | Kept only as a default/example. The core model is **configurable per-job workflow stages** (§45). Do not hardcode a universal funnel. |
| Screening Agent vs Structured Interview Agent as fixed rounds (§7) | Kept as internal template families only. Recruiter-facing stages are configurable; a single stage may combine screening + assessment (§50, §63). |
| `screening_completed` boolean implied | Replaced by field-level `candidate_facts` provenance (§62). |

## Security, authorization, audit, observability principles

- **Secrets** server-side only (Hunar/Apollo/DB/Redis/LLM keys). Never `NEXT_PUBLIC_*`. Any
  key seen in a screenshot, commit, or shared artifact is considered exposed and must be
  rotated.
- **Authorization** — organization-scoped, role-based capabilities (recruiter / hiring
  manager / admin). Candidate data is sensitive: authorization checks, minimal logging,
  encrypted transport, managed DB encryption, sensible retention.
- **Audit** — every consequential action (approvals, overrides, stage transitions, launches,
  decisions) writes an audit event.
- **Observability** — OpenTelemetry traces carry request/org/job/candidate/call/Celery-task
  IDs, operation, duration, status. Never put secrets or unnecessary sensitive candidate
  content into telemetry.

## Explicitly excluded infrastructure

Kubernetes · Kafka · microservices · custom voice/SIP/STT/TTS infrastructure · generic
multi-vendor voice abstraction · deep-agent / multi-agent frameworks · complex event
sourcing · BPMN/Temporal workflow engines · sophisticated enterprise RBAC · full ATS ·
unnecessary LLM chains. Introduce any of these only when a concrete production problem
requires it and it is explicitly requested.
