# PROJECT — Canonical Orientation

This is the one-page source of truth every agent reads first. If any statement here
conflicts with a longer document, this file and `docs/architecture.md` win.

## Product in one sentence

A configurable AI hiring operations platform: an organization defines how it hires, a
recruiter creates a job from a JD, the platform resolves or drafts the appropriate hiring
workflow, candidates are imported or sourced (Apollo), and AI-powered candidate
interactions (Hunar) execute the configured stages while the platform maintains state,
evidence, approvals, and progression.

## Responsibility split (non-negotiable)

- **Hunar** — candidate-facing voice/conversation execution.
- **This platform** — workflow progression, state, data, UI, approvals, policies, evidence, observability.
- **Celery** — durable asynchronous execution.
- **PostgreSQL** — durable business source of truth.
- **Redis** — ephemeral coordination only (broker, locks, rate limiting, cache, dedup).
- **Platform LLM** — only product-intelligence Hunar does not provide: JD understanding, role classification, draft workflow/rubric generation.

## Canonical model: stage-driven execution

The effective Hunar execution context is computed, never static:

```
Organization and job context
+ approved job workflow version
+ current stage definition
+ stage criteria and information requirements
+ candidate known information
+ unresolved prior requirements
+ calling/language policy
= effective Hunar execution context
```

The older "one job = one fixed agent" model is **superseded**. Where the older document
conflicts with the stage-driven model (§45–70 of the architecture reference), the
stage-driven model is canonical. See `docs/architecture.md` §"Conflicts resolved".

## Two connected core journeys + one future module

1. **Existing candidates** — imported, interviewed (may enter at a later stage).
2. **People search & outreach** — Apollo → outreach → progressive enrichment → interview.
3. **Attendance / workforce module** — separate, built only after the recruitment core is stable.

## Hard rules

- Verify vendor capabilities before depending on them (`VERIFIED` / `UNKNOWN` / `UNSUPPORTED`).
- Human approval for consequential AI-generated configuration.
- Recruiters work in product concepts (jobs, workflows, stages, candidates, evidence,
  decisions) — never Hunar agent IDs, prompts, queues, or telephony.
- Small, reversible changes. Implement failure, recovery, authorization, and edge states —
  not only happy paths.
- Never lose state silently. Every failure has: current state, reason, retryability, next
  action, audit record.

## Where things live

- Canonical docs: `docs/`
- Decisions: `docs/decisions/` (ADRs)
- Features: `docs/features/` (INDEX + briefs)
- Active work / handoff: `docs/work/active-feature.md`
- Agent adapters: `CLAUDE.md`, `AGENTS.md`, `.agents/rules/`
- Shared agent workflows: `.agents/workflows/`
- Backend code: `apps/api/` (Django-app-style modules with per-module models + migrations;
  `app/workflow_execution/` owns stage progression; `app/integrations/` holds vendor adapters).
  See `apps/api/README.md` and `docs/architecture.md` §"Realized backend layout".

## Current status

**Both core journeys are built and working end to end.** Realized (see `docs/features/INDEX.md`):

- **Backend** (`apps/api`, FastAPI modular monolith): auth (session cookies) + org/user model;
  job creation (paste or PDF JD → Claude Haiku extraction → confirm → draft workflow → approve →
  activate); in-UI workflow/criteria editing; calling policy; candidate import + timeline;
  interview launch via a real Hunar call (Celery, gated) with webhook + on-demand sync; recruiter
  advance/reject decisions.
- **Journey 2 — People Search & Outreach (real):** search across **four real providers**
  (Apollo, People Data Labs, Proxycurl, Coresignal) with a recruiter-chosen provider; no sample
  data — an unconfigured/plan-gated provider returns an honest error, never fabricated results.
  Add results to the pipeline (SOURCED, deduped) → enrich contact → outreach call (CONTACTED).
  **PDL verified live** (real profiles). Apollo Search is Free-plan gated (403, confirmed live).
- **Settings** (admin): per-org people-search API keys (write-only), default provider,
  live-calling toggle, team roster, and **team invites** (one-time link → set password → join).
- **Frontend** (`apps/web`, Next.js): dashboard, jobs, job hub (workflow + pipeline board),
  candidate timeline, Sourcing, Settings, accept-invite.
- **MCP server** (`apps/mcp`): 31 tools exposing the platform to Claude Code / ChatGPT, incl.
  one-shot journey macros (`source_and_outreach`, `import_and_interview`).

**Verification:** 94 API/Python tests pass (against a dedicated `*_test` DB); web typechecks;
flows browser-verified. Remaining: deployment, OpenTelemetry/Sentry, role-based capability
enforcement, and the attendance module (Question 3). Deferred vendor capabilities stay gated on
`VERIFIED` status.
