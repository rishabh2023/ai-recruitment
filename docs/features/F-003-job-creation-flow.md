# F-003: Job Creation Flow (JD → confirm → draft/approve workflow → activate)

- **Status:** Done (service-layer slice) — 29 tests pass; API/UI slice deferred until the app
  is scaffolded
- **Risk tier:** Standard (multi-file, state + external LLM boundary)
- **Documentation-impact level:** 2
- **Affected areas:** `apps/api/app/modules/jobs`, `apps/api/app/modules/workflows`,
  `apps/api/app/integrations/llm`, `apps/api/app/modules/audit`
- **Depends on:** F-002 (data model + WorkflowExecutionService)
- **Owner / current agent:** Claude Code

## Problem / intent

Phase 2: a recruiter creates a job, provides a JD, the platform extracts/normalizes details,
the **recruiter confirms** them, the platform resolves an existing workflow or **drafts one**,
the recruiter **approves**, and only then is the job activated. Human-approval gates are
enforced: imperfect extraction is never authoritative, and nothing is activated before the
workflow is approved.

## Scope

**In scope (this slice)**

- `LLMProvider` boundary (product intelligence only) + an offline deterministic stub so the
  flow is testable without a key.
- `JobService`: create job, add JD version (with extraction), confirm JD version, activate job
  (gated).
- `WorkflowService`: draft a workflow for a job (unapproved), adopt an org template, approve a
  workflow version.
- Audit on every consequential step; tests.

**Out of scope**

- FastAPI routes / Next.js UI (later slice once the app is scaffolded).
- Real LLM provider implementation; Hunar provisioning.

## Acceptance criteria

- [x] Create job (draft) → add JD version (extracted, `confirmed=False`).
- [x] Confirm JD version sets `confirmed=True`.
- [x] Draft workflow creates an **unapproved** version with stages (+criteria); role-family
      drives stages (engineering vs sales).
- [x] `activate_job` is blocked unless the latest JD is confirmed **and** a workflow version is
      approved; succeeds once both hold.
- [x] Approving a workflow sets `approved`, `approved_by`, `approved_at`.
- [x] Every step writes an audit event; tests cover gates + happy path.

## Evidence

`apps/api/tests/test_job_creation.py` — 6 tests; full suite **29 passed** (2026-09-06).
Services: `app/modules/jobs/service.py` (`JobService`), `app/modules/workflows/service.py`
(`WorkflowService`); LLM boundary `app/integrations/llm/` (deterministic stub).

## Remaining limitations / open questions

- Workflow/JD extraction uses a deterministic stub; a real LLM provider plugs in behind
  `LLMProvider` when `PLATFORM_LLM_API_KEY` is available.
- Rubric/criteria editing UI and transition-policy authoring come with the UI slice.
