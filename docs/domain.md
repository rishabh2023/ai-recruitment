# Domain

Core entities, state machines, and the rules that govern transitions, permissions, audit,
retries, duplicate events, partial results, and manual overrides.

> Everything here is the intended model. Exact column names and simplifications are settled
> during implementation, but **state transitions must be persisted and auditable**.

## Entities

| Entity | Purpose |
| ------ | ------- |
| **Organization** | Tenant boundary. Owns users, workflow templates, jobs, defaults. |
| **User** | Belongs to an organization; has a role (recruiter / hiring manager / admin). |
| **Job** | A role to hire for, within an organization. |
| **Job Version** | Immutable snapshot of confirmed JD / job details at a point in time. |
| **Job Workflow** | The hiring workflow attached to a job (resolved from a template or AI-drafted). |
| **Workflow Version** | Versioned snapshot of a workflow so running processes are stable when templates change. |
| **Workflow Stage** | One configured step of a workflow. Declares execution type, criteria, information requirements, transition policy, approval requirement. |
| **Candidate** | A person, progressively enriched. Resume not assumed present. |
| **Job Candidate** | A candidate's participation in a specific job; holds current stage and pipeline state. |
| **Candidate Stage Run** | One execution of one stage for one job-candidate; has its own lifecycle. |
| **Rubric / Stage Criteria** | Evaluation criteria (numeric weights and/or rule-based) belonging primarily to a stage. |
| **Candidate Fact** | Field-level known information with provenance (value, source, source stage run, confidence, collected_at). |
| **Call** | A logical intent to reach a candidate for a stage. |
| **Call Attempt** | One actual attempt against a Call (distinguishes business vs infrastructure retries). |
| **Interview** | An AI conversation execution mapped to a stage run (subset of Call semantics for interview stages). |
| **Result / Evidence** | Structured output, criteria-level scores, supporting evidence for a stage run. |
| **Webhook Event** | Raw + normalized inbound vendor event, with dedup key. |
| **Audit Event** | Immutable record of a consequential action. |
| **Calling Policy** | Per-org/job (optionally per-stage) calling window, timezone behavior, attempt limits, retry interval, language. |
| **Workflow Template / Template Version / Stage Template** | Organization-owned reusable library that jobs resolve from. |
| **External Search / External Candidate** | Apollo search records and sourced profiles with provenance. |

## Relationships

```
Organization
├── Users
├── Workflow Templates → Template Versions → Stage Templates
└── Jobs
      ├── Job Versions (confirmed JD)
      ├── Job Workflow → Workflow Versions → Workflow Stages
      ├── Calling Policy
      ├── Hunar configuration reference(s)   (contract-dependent, hidden from recruiters)
      └── Job Candidates
            ├── Candidate (progressive profile) → Candidate Facts
            ├── Current Stage
            ├── Candidate Stage Runs → Results / Evidence
            ├── Calls → Call Attempts
            └── Pipeline state / Decisions / Audit
```

## State machines

### Candidate Stage Run lifecycle

```
PENDING → BLOCKED → READY → SCHEDULED → IN_PROGRESS → AWAITING_RESULT
        → NEEDS_REVIEW → COMPLETED
        (any active state) → FAILED | CANCELLED | SKIPPED
```

- `BLOCKED` when required inputs / effective information cannot yet be satisfied.
- `SCHEDULED` when a valid calling window is in the future.
- `AWAITING_RESULT` after Hunar is invoked, before webhook/result arrives.
- `NEEDS_REVIEW` when transition policy or validation requires a human.
- Transitions are persisted; each writes an audit event.
- **Enforced in code** by `apps/api/app/workflow_execution/state_machine.py` (the single
  source of truth for legal moves; raises `InvalidTransition`). `WorkflowExecutionService`
  performs transitions, sets `started_at`/`ended_at`, advances the candidate, and audits every
  move. Terminal states (`COMPLETED`/`FAILED`/`CANCELLED`/`SKIPPED`) have no normal outgoing
  transition — only an explicit, audited `override_transition` may leave them.
- **Stage outcomes** map to run states: `PASS`→`COMPLETED` (+advance), `REVIEW`→`NEEDS_REVIEW`,
  `REJECT`→`COMPLETED` (candidate pipeline `REJECTED`), `RETRY`→`SCHEDULED`, `FAIL`→`FAILED`.

### Call / Call Attempt normalized status

Maintain both the vendor status and a normalized business status:

```
QUEUED · SCHEDULED · CALLING · CONNECTED · COMPLETED
NO_ANSWER · RETRY_SCHEDULED · FAILED · CANCELLED
```

Mapping derived from Hunar's **verified** statuses (F-001). Hunar `CallStatus` →
normalized business status:

| Hunar status | Normalized |
| ------------ | ---------- |
| `NOT_STARTED` | `QUEUED` |
| `SCHEDULED` | `SCHEDULED` |
| `INITIATED`, `RINGING` | `CALLING` |
| `IN_PROGRESS` | `CONNECTED` |
| `COMPLETED` | `COMPLETED` |
| `NOT_CONNECTED` | `NO_ANSWER` → `RETRY_SCHEDULED` if `retries_left > 0` (see `next_retry_scheduled_at`) |
| `FAILED` | `FAILED` |
| `CANCELLED` | `CANCELLED` |

Hunar also exposes `lifecycle_status`, `engagement_status` (ENGAGED/NOT_ENGAGED),
`answered_by` (HUMAN/MACHINE/UNKNOWN), and `call_ended_by` — persist these alongside status.
Do not invent a UI state machine disconnected from Hunar.

### Candidate pipeline (default example — not hardcoded)

`SOURCED · OUTREACH_PENDING · CONTACTED · INTERESTED · SCREENING_COMPLETE ·
INTERVIEW_PENDING · INTERVIEWED · NEEDS_REVIEW · SHORTLISTED · REJECTED`

This is a **default illustration**. The authoritative progression is the job's configured
workflow stages. Existing candidates may enter at a later stage (e.g. `INTERVIEW_PENDING`).
Pipeline state is persisted, never derived solely from UI (dragging a card is not truth).

### Stage transition policy

After a stage run completes: `validate required output → evaluate configured transition rule
→ PASS (advance, auto only where explicitly allowed) | REVIEW (needs recruiter review) |
REJECT (stop) | RETRY/RESCHEDULE`. Human approval remains available for consequential
decisions.

## Actor permissions (summary)

| Action | Recruiter | Hiring Manager | Admin |
| ------ | :---: | :---: | :---: |
| Create/manage jobs, workflows, criteria | ✓ | review | ✓ |
| Import/source candidates | ✓ | | ✓ |
| Launch outreach/interview | ✓ | | ✓ |
| Review evidence / decide at review stages | ✓ | ✓ | ✓ |
| Manual override / skip / start at later stage | ✓ (audited) | ✓ (audited) | ✓ (audited) |
| Org settings / templates / users | | | ✓ |

Full authorization conventions live in `docs/interfaces.md`.

## Audit requirements

Every consequential action records: `actor, action, from_state, to_state, reason,
timestamp, unresolved_requirements` where applicable. Overrides, stage transitions,
approvals, launches, and decisions are always audited.

## Behavior rules

- **Retry** — distinguish **business retry** (no answer, "call me later", allowed additional
  attempt) from **infrastructure retry** (timeout, temporary API/worker failure).
  Infrastructure retries must not consume a candidate-contact attempt unless a call was
  actually initiated per verified vendor behavior. Calling-window checks apply before every
  business attempt. Use Hunar native retry where it satisfies the verified requirement;
  otherwise the platform coordinates the missing business policy — never two competing
  engines. Retry execution is centralized; retry policy is configuration (org default → job
  override → stage override only when genuinely needed).
- **Duplicate events** — webhook delivery may be duplicated. Persist a vendor event ID (or
  derive a stable dedup key from documented identifiers). A duplicate must never create
  duplicate candidates, advance the pipeline twice, duplicate evaluations, or trigger
  duplicate calls.
- **Partial results** — a call may succeed while returning incomplete structured output.
  Persist what arrived, mark the stage run `NEEDS_REVIEW` (or collect the missing fields in
  a later stage via carry-forward), and never treat imperfect extraction as authoritative.
- **Manual override** — starting at a later stage, moving forward despite incomplete stages,
  sending back, marking external evidence, or skipping are explicit, audited product actions
  that show consequences before confirmation — never invisible mutations or DB admin.
- **User-visible recovery** — every failure surfaces: current state, reason, retryability,
  next action, and an audit record. Never lose state silently.
