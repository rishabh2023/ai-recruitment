# Experience

Recruiter-facing UX principles and the states every meaningful flow must support.

## Principles

- **Component system: shadcn/ui.** Recruiter UI is built from shadcn/ui components on
  Next.js + React + TypeScript, for a consistent, accessible design language.
- Recruiters think in **jobs, workflows, stages, candidates, evidence, and decisions** —
  never Hunar agent IDs, prompts, queues, telephony, or retry internals.
- The first authenticated screen is the **Dashboard**, and it is action-oriented: it answers
  "what is happening in hiring right now, and what needs my attention?" Primary CTA:
  **Create Job**.
- **One dashboard shell, role-aware content** — same product shell, different
  widgets/permissions per role. Not separate apps.
- Consequential AI-generated configuration is always **drafted → reviewed/edited → approved**
  before it executes. The AI output is a draft, never authoritative.
- Consequential external actions (bulk outreach/interview) go through an explicit
  **pre-launch review** screen, not an immediate fire.
- The pipeline board is a **view over persisted state**. Dragging a card is never the source
  of truth.
- Manual overrides (start at later stage, move despite incomplete stage, skip) always **show
  the consequence** before confirmation and are audited.

## Key flows and their surfaces

- **Jobs** — create, upload/enter JD, confirm extracted details, resolve/draft workflow,
  review/customize stages and criteria, activate.
- **Workflows** — organization template library; per-job snapshot; AI-drafted workflow for
  bootstrap when no template matches.
- **Stages** — configure purpose, execution type (AI/Human/System), information to collect,
  criteria, transition policy, approval requirement, calling/language for voice stages.
- **Candidates** — import existing or find via Apollo; progressive profile with a
  completeness indicator (Known / Missing / Source); choose starting stage where justified.
- **Evidence** — structured result, criteria-level scores, supporting evidence, and only
  the transcript/summary/recording fields Hunar actually returns.
- **Calling policy** — allowed days, window, timezone behavior, attempt limits, retry
  interval, language (only where a `VERIFIED` Hunar capability backs it).
- **Retry status** — attempt history, next scheduled attempt, final status, all visible to
  recruiters.
- **Exceptions & manual overrides** — clear operator next action for every failure.

## Required states for every meaningful flow

Each flow must explicitly handle:

- **Loading**
- **Empty** (no jobs, no candidates, no workflow configured — including the bootstrap case)
- **Success**
- **Validation error**
- **External API failure** (Hunar/Apollo timeout or error, with retryability + next action)
- **Partial data** (incomplete profile, incomplete structured result)
- **Permission denied**
- **Retry / recovery** (visible next scheduled attempt, manual retry where allowed)
- **Desktop and mobile behavior**
- **Basic accessibility** (keyboard navigation, focus states, semantic markup, sufficient
  contrast, labelled controls)

## Candidate detail

Three conceptual areas: **Profile** (identity/contact/source/experience/documents/known
fields, with missing clearly marked), **Hiring Journey** (timeline over the job's configured
stages and call attempts), and **Evidence & Results** (per completed AI stage). It is a
workflow/timeline, not a flat CRUD record.

## Empty / bootstrap emphasis

A new organization may create its first job before any workflow exists. The UI must not
block on configuration: draft a suggested workflow, let the recruiter review/edit/approve,
use it for the job, and optionally save it as a reusable template.
