# Funnels — reusable hiring-funnel (workflow template) library

Date: 2026-09-06
Status: approved

## Problem

`docs/experience.md` calls for an "organization template library" of reusable workflows
(funnels) that jobs resolve from, and "optionally save it as a reusable template". The data
model already exists (`WorkflowTemplate` → `WorkflowTemplateVersion` → `WorkflowStageTemplate`
+ `WorkflowService.adopt_template`) but has **no API endpoints and no UI**. Recruiters have no
way to create, edit, or apply reusable funnels — every job workflow is drafted from scratch.

## Decisions

- Recruiter-facing name is **Funnels**; internally these remain workflow templates.
- Editing a funnel's stages **creates a new template version** (never mutates an existing
  version), so a job that already adopted an older version stays stable (domain.md §Workflow
  Version).
- Funnels are **archived, not deleted** (matches jobs; jobs referencing a template keep
  working via `source_template_id ON DELETE SET NULL`).
- Rich stage data (purpose, information_requirements, requires_human_approval, criteria) is
  stored in the existing `WorkflowStageTemplate.config` JSONB — no stage schema change.
- Writes (create/edit/rename/archive/use) are **admin-only** (org config, mirroring Settings);
  list/view are available to any member.

## Backend

### Migration (workflows module)
- Add nullable `archived_at TIMESTAMPTZ` to `workflow_templates`.

### `WorkflowTemplateService` (workflows module)
- `list_templates(org_id, include_archived=False)` → [(template, latest_version, stage_count)].
- `create_template(org_id, name, stages)` → template + version 1 + stage templates (config
  carries purpose/info/criteria/approval).
- `get_template(template_id)` → template + latest version + full stages.
- `edit_stages(template_id, stages)` → **new version** with the given stages; returns it.
- `rename(template_id, name)`; `archive(template_id)` (sets archived_at).
- Enhance `WorkflowService.adopt_template` to copy stage config (purpose, info requirements,
  requires_human_approval, criteria) into the job workflow stages — not just name + type.

### Router `/funnels` (org-scoped)
- `GET /funnels` (list; `?include_archived=`), `POST /funnels`, `GET /funnels/{id}`,
  `PUT /funnels/{id}/stages` (→ new version), `PATCH /funnels/{id}` (rename),
  `POST /funnels/{id}/archive`, `POST /funnels/{id}/use` (`{job_id}` → adopt; admin).
- Validation mirrors the job-workflow stage editor (≥1 stage, valid execution_type, criterion
  kinds, names non-empty). 404 for cross-org / missing. 403 for non-admin writes.
- Register in `app/main.py`.

### Schemas
- `FunnelStageIn`/`FunnelStageOut` (same shape as job StageEdit/StageDetail),
  `FunnelSummaryOut` (id, name, stage_count, version, updated_at, archived),
  `FunnelDetailOut` (id, name, version, archived, stages), `FunnelCreateIn`,
  `FunnelRenameIn`, `FunnelStagesIn`, `FunnelUseIn` (job_id).

## Frontend

- `components/WorkflowEditor.tsx`: refactor to generic props `initialStages: StageEdit[]`,
  `onSave: (stages) => Promise<StageEdit[]>`, optional `saveLabel`. Update both existing call
  sites (`app/jobs/new`, `app/jobs/[id]`) — no behavior change for jobs.
- `components/AppShell.tsx`: add **Funnels** nav item (`/funnels`).
- `app/funnels/page.tsx`: library list (name, stage count, version, updated), Create funnel
  (name → editor with a sensible default stage), archived toggle. Loading/empty/error states.
- `app/funnels/[id]/page.tsx`: view stages; Edit (WorkflowEditor → new version); rename;
  archive; "Use in a job" (choose a job → adopt → link to `/jobs/{id}` Workflow tab). All
  states incl. permission-denied for non-admins (writes hidden/blocked).
- `lib/api.ts`: Funnel types + methods (listFunnels, createFunnel, getFunnel,
  editFunnelStages, renameFunnel, archiveFunnel, useFunnel).
- `app/globals.css`: styles for the funnel library list.

## Testing (API)

- create → list → get roundtrip; stage config persisted (criteria, purpose, approval).
- edit stages creates a new version (old version untouched).
- adopt (`/use`) copies full config into the job's workflow stages (unapproved).
- admin-only writes: non-admin create/edit/use → 403.
- archive hides from default list; `?include_archived=true` shows it.
- cross-org / missing → 404.
- Web: tsc clean; WorkflowEditor refactor keeps job flows working (manual/browser check).

## Out of scope

- Funnel version history browsing UI (only latest version is editable/viewable this slice).
- Duplicating/cloning a funnel; importing a job's workflow back into a funnel.
