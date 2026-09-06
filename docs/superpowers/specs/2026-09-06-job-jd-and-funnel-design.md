# Job page: JD view/edit + stage funnel stats

Date: 2026-09-06
Status: approved (approach A + expose `jd_text`)

## Problem

The job workspace (`apps/web/app/jobs/[id]/page.tsx`) shows workflow, a pipeline
board, and calling policy, but:

1. The recruiter cannot see or edit the **Job Description** from the job page — the
   raw JD text is stored on `JobVersion.jd_text` but is not exposed by the API
   (`JobVersionOut` returns `extracted`, not the raw text) and there is no endpoint
   to fetch the current version.
2. There is no **funnel view** — only per-stage current occupancy on the board.
   The recruiter wants a top-down funnel: total candidates → how many reached each
   stage → conversion %, and how much of the pipeline is complete.

## Decisions

- **Funnel semantics: cumulative reached.** Each stage counts every candidate whose
  furthest-reached stage is at or beyond it (a rejected candidate counts toward the
  furthest stage they got to; a COMPLETED candidate counts toward every stage).
- **JD: view + edit inline.** Editing reuses the existing versioned flow — a new
  `JobVersion` is created (re-extraction runs) and stays unconfirmed until confirmed.
  No new mutation path; the audit/version model is preserved.
- **Funnel is computed server-side (approach A).** Postgres owns stage ordering and
  `pipeline_state`; the UI renders, it does not derive truth (per `apps/web/CLAUDE.md`).

## Backend

### Expose the JD
- Add `jd_text: str` to `JobVersionOut` (`schemas.py`).
- Add `GET /jobs/{job_id}/version` → latest `JobVersion` as `JobVersionOut | None`
  (newest by `version`; `None` when no JD has been added yet).

### Funnel endpoint
- Add `GET /jobs/{job_id}/funnel` → `FunnelOut`.
- Effective workflow version selected exactly like `get_job_workflow`
  (approved if any, else latest draft). Stages ordered by `stage_order`.
- Per candidate, compute `furthest_order`:
  - `pipeline_state == "COMPLETED"` → past the last stage (counts for every stage).
  - `current_stage_id` present and in the effective version → that stage's order.
  - otherwise (e.g. SOURCED with no stage, or a stage from an older version) → 0
    (top of funnel only).
- `reached(stage)` = count of candidates with `furthest_order >= stage.stage_order`
  (COMPLETED always included). `current(stage)` = candidates whose `current_stage_id`
  is that stage and `pipeline_state` not in {REJECTED, COMPLETED}.
- Top-line: `total`, `rejected` (REJECTED), `completed` (COMPLETED),
  `in_progress` (total − rejected − completed).
- `FunnelStageOut`: `stage_id, stage_order, name, execution_type, reached, current,
  reached_pct` (reached/total, 0 when total 0).
- `FunnelOut`: `total, rejected, completed, in_progress, completion_pct`
  (completed/total), `stages: list[FunnelStageOut]`.
- Empty/degenerate cases: no workflow → `stages: []` with top-line still returned;
  no candidates → all zeros, no divide-by-zero.

## Frontend

- `api.ts`: add `jd_text` to the `JobVersion` type; add `getLatestVersion(jobId)` and
  `getJobFunnel(jobId)`; add `Funnel`/`FunnelStage` types.
- `page.tsx` Overview tab:
  - **Job description card** — shows current JD text (from latest version) with a
    confirmed/draft badge. "Edit" reveals a textarea; Save calls `addVersion` then
    the recruiter confirms. Empty state links to job setup. All states: loading,
    empty, saving, error.
  - **Funnel section** — horizontal funnel bars per stage (reached count + % of total
    and step-to-step conversion), plus top-line tiles (total, in progress, rejected,
    completed, completion %). Empty state when no candidates or no workflow.
- `globals.css`: styles for the JD card and funnel bars (light + dark, responsive).

## Testing

- API: `GET /jobs/{id}/version` returns latest with `jd_text`; `None` when absent.
- API: funnel math — cumulative reached across stages, COMPLETED counts everywhere,
  REJECTED counts to its furthest stage, no workflow, no candidates.
- Frontend build/typecheck; manual browser check of the two new sections.

## Out of scope

- Stage-transition history table (funnel derived from current position, not an
  event log). Editing JD does not re-draft or re-approve the workflow.
