# AI Recruitment Workflow

A production-oriented AI recruitment and workforce operations platform.

**Hunar** is the voice / conversation execution layer. **This platform** owns the
product workflow, orchestration, state, data, UI, approvals, policies, evidence, and
operational visibility.

> Tell the platform who you need to hire → confirm how you want to evaluate them →
> add or find candidates → let the platform orchestrate the hiring workflow →
> review evidence and make decisions.

## What this repository is

This is an **agent-neutral engineering foundation**. The Git repository — not any
individual agent conversation — is the durable source of truth. Claude Code, Codex,
Antigravity, and future coding agents all read the same documents and follow the same
loop.

The application is **built and working end to end** (`apps/api` FastAPI backend,
`apps/web` Next.js console, `apps/mcp` MCP server). Both core journeys run: existing
candidates → AI interview, and **people search → outreach** across four real providers
(Apollo/PDL/Proxycurl/Coresignal — no sample data; PDL verified live). Plus Settings
(provider keys, live-calling, team invites) and an MCP server exposing the platform to
Claude Code / ChatGPT. See `PROJECT.md` and `docs/features/INDEX.md` for the current status
and evidence. The Git repository — not any agent conversation — remains the source of truth.

## Stack

| Concern            | Choice                                     |
| ------------------ | ------------------------------------------ |
| Frontend           | Next.js + React + TypeScript + shadcn/ui   |
| Backend            | FastAPI + Python (modular monolith)        |
| Database           | PostgreSQL (durable business source of truth) |
| Background work    | Redis + Celery                             |
| Voice execution    | Hunar                                      |
| People search      | Apollo                                     |
| Observability      | OpenTelemetry + Sentry                     |
| Platform LLM       | JD understanding, role classification, draft workflow/rubric generation only |

## Start here

1. [`PROJECT.md`](PROJECT.md) — the canonical one-page orientation.
2. [`docs/intent.md`](docs/intent.md) — who this is for and the problem it solves.
3. [`docs/architecture.md`](docs/architecture.md) — the modular monolith and the canonical stage-driven model.
4. [`docs/agent-handbook.md`](docs/agent-handbook.md) — the required loop every agent follows.
5. [`docs/roadmap.md`](docs/roadmap.md) — the phased plan (Phase 0 → Phase 6).

Agent entry points: [`CLAUDE.md`](CLAUDE.md) (Claude Code),
[`AGENTS.md`](AGENTS.md) (Codex), [`.agents/rules/`](.agents/rules) (Antigravity).

## Ground rules

- No vendor capability is treated as fact unless marked `VERIFIED` in
  [`docs/vendor-capability-matrix.md`](docs/vendor-capability-matrix.md).
- No recruiter-facing UI control is built around an unverified capability.
- Consequential AI-generated configuration (workflows, rubrics, stage criteria) requires
  human approval before it executes.
- The platform stays a modular monolith. No microservices, Kubernetes, Kafka, custom
  telephony, custom speech infra, generic multi-vendor voice abstraction, or deep-agent
  framework unless explicitly requested later.
