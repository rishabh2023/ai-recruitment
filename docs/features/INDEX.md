# Feature Index

Status of every feature. New features get a brief from `FEATURE_TEMPLATE.md` and a row here.

| ID | Feature | Status | Risk tier | Phase | Affected areas | Evidence |
| -- | ------- | ------ | --------- | ----- | -------------- | -------- |
| [F-001](F-001-hunar-contract-verification.md) | Hunar & People-Search Contract Verification | Done (contract) — live smokes gated on key/number | High Risk | Phase 0 | `apps/api/app/integrations/{hunar,people_search}`, capability matrix, ADR-0001/0002 | Hunar: docs+OpenAPI+read-only live (200), webhook verifier unit-checked. Apollo: docs-verified, `search()` wired + mapping unit-checked |
| [F-002](F-002-core-data-model.md) | Core Data Model & State Transitions | Done | High Risk | Phase 1 | `apps/api/app/modules/*/{models,migrations}`, `apps/api/app/workflow_execution/`, `apps/api/alembic*`, `docs/{domain,architecture}.md` | 25 tables via Alembic (reversible round-trip); 10 CHECKs; WorkflowExecutionService enforced transitions + audit; 23 tests pass |
| [F-003](F-003-job-creation-flow.md) | Job Creation Flow (service slice) | Done | Standard | Phase 2 | `apps/api/app/modules/{jobs,workflows}/service.py`, `apps/api/app/integrations/llm/`, `docs/architecture.md` | JobService + WorkflowService with confirm/approve gates; LLM adapter (offline stub); 29 tests pass |
| [F-004](F-004-interview-execution-flow.md) | Interview Execution Flow (service slice) | Done | High Risk | Phase 3 | `apps/api/app/modules/{candidates,interviews,webhooks}/service.py`, `apps/api/app/integrations/hunar/mapping.py`, `apps/api/app/workflow_execution/effective_info.py` | Import→launch→idempotent webhook→result→facts→review; carry-forward; 38 tests pass |
| [F-005](F-005-app-scaffold.md) | App Scaffold (FastAPI + Next.js) | Done | Standard | Phase 2–3 exposure | `apps/api/app/{main,config,api,db/session}`, `apps/web/` | FastAPI routers wired to services (HTTP e2e); Next.js dashboard + guided job flow; **41 API tests pass**, web builds+typechecks |

## Conventions

- **Status:** Proposed → Ready → In progress → Blocked → Done.
- **Risk tier / Phase:** from `docs/task-intake.md` and `docs/roadmap.md`.
- **Evidence:** link to the proof captured for Definition of Done, or "Pending".
