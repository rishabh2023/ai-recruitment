# Feature Index

Status of every feature. New features get a brief from `FEATURE_TEMPLATE.md` and a row here.

| ID | Feature | Status | Risk tier | Phase | Affected areas | Evidence |
| -- | ------- | ------ | --------- | ----- | -------------- | -------- |
| [F-001](F-001-hunar-contract-verification.md) | Hunar & People-Search Contract Verification | Done (contract) — live smokes gated on key/number | High Risk | Phase 0 | `apps/api/app/integrations/{hunar,people_search}`, capability matrix, ADR-0001/0002 | Hunar: docs+OpenAPI+read-only live (200), webhook verifier unit-checked. Apollo: docs-verified, `search()` wired + mapping unit-checked |
| [F-002](F-002-core-data-model.md) | Core Data Model & State Transitions | Done | High Risk | Phase 1 | `apps/api/app/modules/*/{models,migrations}`, `apps/api/app/workflow_execution/`, `apps/api/alembic*`, `docs/{domain,architecture}.md` | 25 tables via Alembic (reversible round-trip); 10 CHECKs; WorkflowExecutionService enforced transitions + audit; 23 tests pass |
| [F-003](F-003-job-creation-flow.md) | Job Creation Flow (service slice) | Done | Standard | Phase 2 | `apps/api/app/modules/{jobs,workflows}/service.py`, `apps/api/app/integrations/llm/`, `docs/architecture.md` | JobService + WorkflowService with confirm/approve gates; LLM adapter (offline stub); 29 tests pass |
| [F-004](F-004-interview-execution-flow.md) | Interview Execution Flow (service slice) | Done | High Risk | Phase 3 | `apps/api/app/modules/{candidates,interviews,webhooks}/service.py`, `apps/api/app/integrations/hunar/mapping.py`, `apps/api/app/workflow_execution/effective_info.py` | Import→launch→idempotent webhook→result→facts→review; carry-forward; 38 tests pass |
| [F-005](F-005-app-scaffold.md) | App Scaffold (FastAPI + Next.js) | Done | Standard | Phase 2–3 exposure | `apps/api/app/{main,config,api,db/session}`, `apps/web/` | FastAPI HTTP e2e incl. calling policy and dispatch mapping; Next.js dashboard/job hub; **78 API/Python tests pass**, web builds+typechecks + browser policy-save check |
| F-006 | Sourcing — People Search & Outreach (real multi-provider: search → add → enrich → outreach) | Done | Standard | Phase 5 | `apps/api/app/modules/sourcing/`, `apps/api/app/integrations/people_search/{apollo,pdl,proxycurl,coresignal,base}.py`, `apps/web/app/sourcing/`, `apps/web/app/job-candidates/[id]/` | Real providers only (Apollo/PDL/Proxycurl/Coresignal), provider selector, honest 502 on unconfigured/plan-gated (no fabricated data); add (SOURCED, deduped) → enrich → outreach (CONTACTED). Browser-verified |
| F-007 | Settings — org config (provider API keys, default provider, live-calling, team) | Done (invites next) | Standard | Phase 6 | `apps/api/app/modules/organizations/{models,settings_service}.py` (migration `c2d3e4f5a6b7`), `apps/api/app/api/routers/settings.py`, `apps/web/app/settings/` | `org_settings` table; admin-only `GET/PUT /settings`; write-only provider keys (never returned); org-first key resolution feeds sourcing; live-calling toggle gates real dialing. **91 API/Python tests pass**; web typechecks; browser-verified |
| F-008 | MCP server — conversational access (Claude Code / ChatGPT) | Done | Standard | Phase 6 | `apps/mcp/` (`server.py`, `requirements.txt`, `README.md`), root `.mcp.json` | 27 MCP tools wrapping the backend (jobs, workflow, candidates, sourcing, outreach, settings); stdio + streamable-http; cookie auth w/ auto-relogin. Verified live: whoami/dashboard/create-job/JD-extract and a real PDL search → add-to-pipeline all through MCP tools; HTTP transport boots at `/mcp` |

## Conventions

- **Status:** Proposed → Ready → In progress → Blocked → Done.
- **Risk tier / Phase:** from `docs/task-intake.md` and `docs/roadmap.md`.
- **Evidence:** link to the proof captured for Definition of Done, or "Pending".
