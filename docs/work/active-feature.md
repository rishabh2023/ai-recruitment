# Active Feature — Handoff

This file is the resume point for any agent. Keep it current.

## F-009 — Per-stage intent-matched voice-agent provisioning — in progress this session

**Branch:** `feat/per-stage-agent-provisioning`. All backend automated checks green
(`apps/api`: 174 passed via `.venv/bin/python -m pytest`); web typechecks + `npm run build` clean.

**What now works (each AI funnel stage gets its own on-intent agent):**
- **Generators** (`apps/api/app/integrations/hunar/agent_spec.py`) — pure. `stage_intent(...)` →
  descriptor (role, company, stage name, purpose, collect fields). `classify_purpose()` picks a
  base family (screening / technical / sales / manager / compensation); `build_agent_spec()`
  emits a `POST /agents/` body whose `result_schema` keys **equal** the stage's
  `information_requirements` (fixes the Evidence mismatch by construction). Single-brace
  placeholders (pinned in the vendor matrix).
- **Provisioning service** (`apps/api/app/modules/interviews/agent_provisioning.py`) —
  `ensure_stage_agent()` runs bound → match-existing → create-and-bind. **Matching is
  LLM-driven** (`LLMProvider.match_agent` — semantic role + stage-purpose + collect-fields match
  over the ACTIVE account agents; strict: only returns a candidate id, confidence ≥ 0.7, else
  None). Deterministic name match (role must appear in the agent's name) is the offline/fallback
  path when no LLM key is set or the LLM declines. Idempotent.
  `provision_version_agents()` sweeps all AI stages best-effort (per-stage typed errors, no abort).
  `maybe_provision_version_agents()` / `provisioning_ready()` gate on the live-calls guard.
- **Triggers** — eager at funnel approval (`apps/api/app/api/routers/jobs.py` `approve_workflow`,
  best-effort, never blocks approval); lazy safety-net at dispatch
  (`apps/api/app/modules/interviews/dispatch.py` `_resolve_agent` / `_lazy_provision`).
- **Fallback surfaced** — dispatch writes audit `interview.agent_fallback_default` when it uses
  the global default; no silent wrong-agent calls.
- **View / override / EDIT API** — `GET /jobs/{id}/workflow/versions/{vid}/agents` now returns a
  product-safe **profile per stage** (`objective`, `collects`, `collect_keys`, `purpose_family`,
  `stage_purpose`, `editable`) so recruiters see *what each agent does*; `POST …/agents/provision`
  (409 unless calling configured); `PUT …/workflow/stages/{sid}/agent` (override which agent);
  **`PUT …/workflow/stages/{sid}/agent/spec`** (edit objective + collect fields → stored on the
  binding's new `spec` JSONB and pushed to Hunar via `update_agent`, best-effort). Editable profile
  persisted via migration `a1b2c3d4e5f6` (`hunar_agent_configs.spec`), stored on create/override
  and by `AgentProvisioningService.update_stage_agent`.
- **Web** — recruiter-safe `StageVoiceAgents` panel in `apps/web/app/jobs/[id]/page.tsx`
  (approved-funnel view): a `VoiceAgentCard` per AI stage showing readiness, purpose family, the
  **objective**, and the **fields it asks about** (chips); an inline **edit** form (objective +
  comma-separated collect fields) for stages with their own agent. **Never shows Hunar ids**
  (`stageAgentStatus` / `editStageAgentSpec` in `apps/web/lib/api.ts`).

**Tests added:** `apps/api/tests/test_agent_spec.py` (+purpose classification/technical script),
`test_agent_provisioning.py` (match/create/mismatch/idempotent/sweep/failure),
`test_agent_provisioning_api.py` (view/override/guard), plus `test_hunar_dispatch.py` updated for
the lazy net.

**Migration to apply before running the app** (test DB already migrated this session):
`cd apps/api && alembic upgrade head` (adds `hunar_agent_configs.spec`, rev `a1b2c3d4e5f6`).

**Remaining / next action (in order):**
1. Override UX: add a `GET` that lists account agents by **name** (recruiter picks a name, not an
   id) and swap the web panel's provision-only affordance for a per-stage picker.
2. Staging: one real Hunar sandbox call from a generated agent to confirm Evidence populates
   end-to-end (acceptance item still `[x]` by construction but unverified live).
3. Migration note: existing hand-made agents (e.g. "Screener - Full Stack Developer") whose keys
   differ — re-bind to generated agents or add a per-binding key map.
4. Docs: `architecture.md` (agent ownership) + `domain.md` (`HunarAgentConfig` lifecycle) still to
   receive a short section (matrix + feature brief already updated).

**Risks:** provisioning creates real vendor resources — gated behind the live-calls guard; keep it
that way. Re-provision must not orphan in-flight calls (current binding is additive/newest-wins;
dispatch reads newest — verify before enabling frequent re-provision).

---


## Hunar voice-AI key health check + in-app admin re-key — done this session

- **Global durable key override:** new `app_config` DB table (migration `f8a1c2d3e4b5`,
  down_revision `e7c1d2f3a4b5`) holds a global (non-org-scoped) Hunar API key override. Key
  resolution is DB override → `.env` (`app/integrations/hunar/keystore.py`).
- **Health probe:** `GET /numbers/` (already `VERIFIED` in the vendor matrix) doubles as the
  key-validity/health probe — 2xx → valid, 401/403 → invalid, transport error → unreachable.
  Result cached ~60s in Redis (`app/redis_client.py`); cache is disposable, the key override is
  durable in Postgres.
- **Endpoints:** `GET /hunar/health` (any authenticated user) → `{status, source, checked_at}`,
  `?refresh=1` forces a live probe, never returns the key. `PUT /hunar/key` (admin only) —
  validates the key against Hunar **before** saving, audit-logs `hunar.key.updated` (never the
  key value), and busts the health cache on success. See `docs/interfaces.md` (Voice-AI (Hunar)
  health & key) and `docs/vendor-capability-matrix.md` for the endpoint/probe contract.
- **Web:** sidebar `HunarHealthBadge` (product language "Voice AI") + an admin-only re-key modal,
  wired into `apps/web/components/AppShell.tsx`; web API client gained the corresponding methods.
- **Verification:** backend `pytest tests/test_hunar_keystore.py tests/test_hunar_health_api.py`
  → **15 passed**; full backend suite **154 passed**. Web `tsc --noEmit` + `npm run build` clean.
  Browser-verified on localhost:3000: badge shows "Voice AI connected" (green) for an admin,
  after rebuilding the Docker API (`docker compose up -d --build api`, which ran the new
  migration).
- **Remaining / risks:** Redis holds only the disposable health cache — the key override itself
  is durable in the DB. A valid Hunar account key in `.env` (or an in-app override) is required
  to actually see "healthy" live. The live-calls toggle (`HUNAR_LIVE_CALLS_ENABLED`) is
  independent of key health — a healthy key does not by itself enable live dialing.
- **Branch:** `feat/hunar-key-health`. **Exact next action:** final whole-branch code review of
  `feat/hunar-key-health`, then open a PR / merge.

## Pipeline scale, CSV import, JD polish, sourcing recall, dedup — done this session

Backend (`apps/api`, all green — 143 tests):
- **JD from PDF**: `tidy_jd_text` reflows ragged pypdf output into readable prose (bullets/headings
  kept); scanned/image-only PDFs fall back to the LLM's native PDF reading (`read_pdf_text`,
  bounded 2 MB / 4 pages). New `POST /jobs/{id}/versions/tidy` for in-place cleanup.
- **Pipeline at scale**: `GET /jobs/{id}/pipeline` — server-paginated + filterable (stage/state/q).
- **CSV bulk import**: `POST /jobs/{id}/candidates/import-csv` — name+mobile mandatory, optional
  `country_code`, per-row errors, per-phone de-dupe. Phones normalized to E.164 (`_to_e164`).
- **Candidate edit**: `PATCH /job-candidates/{id}` (name/phone/email/location).
- **Per-role de-duplication**: manual add + CSV reject a phone/email already in that job (409),
  country-code tolerant (suffix match).
- **Audit log**: `GET /dashboard/audit` now paginated + search (`?page=&page_size=&q=`).
- **Sourcing recall fix** (`people_search/pdl.py`): title `match_phrase` on a cleaned title (was
  exact `terms` → zero results), skills as `should` boosts (not AND-ed), invalid seniority levels
  dropped, no `minimum_should_match` (PDL rejects it). JD query now returns ~63k instead of 0.
- New job ops: `POST /jobs/{id}/archive`, `DELETE /jobs/{id}`; `GET /jobs/{id}/funnel`,
  `GET /jobs/{id}/version`.

Web (`apps/web`, typechecks clean):
- **"Workflow" → "Funnel"** in all recruiter-facing copy (code identifiers unchanged). Existing
  jobs **draft the funnel in place** (no wizard restart); `?tab=` deep-links the workspace tabs.
- **Pipeline redesign**: paginated table with stage filter chips + search + Edit per row; empty
  state shows the two entry paths. Old `/jobs/{id}/candidates` page redirects to `?tab=pipeline`.
- **Add candidate modal** (in place, manual + CSV tabs) with a required **country-code selector**;
  "Add candidates"/"Manage candidates" open the Pipeline tab.
- **Success criteria** listed on funnel stage cards; **Clean up formatting** button on the JD editor.
- Shared `Modal` focus fix (was stealing focus from inputs each keystroke).

Docs updated: `interfaces.md`, `experience.md`, `vendor-capability-matrix.md` (PDL query + Hunar
E.164/scheduling notes). Hunar learning: callee number must be E.164; a dispatched call sits at
`SCHEDULED` and dials during acceptable calling hours (won't cold-dial at night).

## Dashboard premium redesign + icon system, done this session

- New inline SVG icon set (`components/Icon.tsx`) replacing the unicode-glyph sidebar icons;
  icons now on sidebar nav and dashboard stat cards.
- First-run **launch pad**: when the org has no jobs, the dashboard shows a gradient hero
  ("From job description to hired — in one place") + a 3-step guided path (Add your JD →
  Shape the funnel → Add candidates & hire with confidence) instead of an all-zero stat wall.
  Populated orgs still get the stats + attention + jobs sections.
- **Audit Trail removed from the dashboard** (it lives in the Audit logs tab now).
- Assistant **FAB is animated** (gradient + gentle attention pulse) with a hover tooltip
  ("Ask the hiring assistant"); pulse/glow respect prefers-reduced-motion.
- Verified in-browser (empty org): launch pad + steps render, sidebar icons correct, FAB
  tooltip shows on hover. Web tsc clean.

## Conversational assistant — Claude tool-use agent, done this session

- Floating **✦ chat launcher** (bottom-right, `components/AssistantWidget.tsx`) on every
  signed-in page; opens a chat panel (greeting, quick-action chips, message input, reply
  bubbles + clickable action links).
- Backend `POST /assistant/chat` (`app/api/routers/assistant.py`): a bounded (≤5 rounds)
  Claude tool-use loop using `settings.platform_llm_api_key` + `platform_llm_model`
  (claude-haiku-4-5). Tools are the same product ops the MCP server wraps, hosted in-process
  and **org-scoped via the request principal/session**: `dashboard_summary`, `list_jobs`,
  `list_candidates`, `list_funnels` (reads), and `create_job` (creates a draft — reversible).
- Safety posture: destructive/consequential ops (delete, archive, launch calls, decisions)
  are deliberately NOT exposed to the model; the system prompt tells it to direct users to the
  UI for those. No `session.commit()` in tools — the get_session request boundary commits.
- Verified live (key present in root .env): "how many jobs/candidates" → correct grounded
  answer via tools; "create a job for a Senior Frontend Engineer" → created a draft + returned
  an Open link; follow-up "what should I do next" → listed the draft with next steps. Hermetic
  test `test_assistant_chat_without_key_is_graceful` covers the no-key path.
- **Step-by-step copilot + human-in-the-loop (this session):** the agent now drives the full
  new-role flow conversationally — create_job → add_job_description (paste in chat OR upload a
  **PDF via the 📎 button** in the widget) → get_job → confirm_job_description → draft_workflow.
  It leads one step at a time and uses tasteful emojis.
  - **Guardrail — human-in-the-loop:** `confirm_job_description` and `draft_workflow` are
    consequential; the model proposing them returns a `pending` action instead of executing.
    The widget shows a **⚠️ Confirm / Cancel** card; on Confirm the client re-POSTs
    `approve:{tool,args}` and the backend runs that exact action **deterministically** (no LLM
    re-planning), so approvals can't be misfired. `_needs_confirmation` skips gating an
    already-satisfied confirm (idempotent) so the flow doesn't loop.
  - Every job tool is org-scoped + ownership-checked; the model never gets a raw id it can act
    on without a `list_jobs`/lookup. Approve/activate/delete/archive/launch/decisions remain
    UI-only. Since the chat is stateless per call, the system prompt tells the model to
    `list_jobs` to resolve a job by title before acting.
  - Verified live: gate returns `pending: confirm_job_description`; approving it persists
    `jd_confirmed=true`; PDF upload path wired via `/jobs/{id}/versions/upload`. Hermetic test
    `test_assistant_tools_jd_flow_hermetic` covers create→JD→get→confirm→draft + ownership guard.
  - Follow-ups: streaming responses; confirm gate for any future mutating tools (apply-funnel,
    add-candidate).

## Audit logs tab + job/candidate delete, done this session

- New **Audit logs** sidebar tab (`/audit`): full org audit trail table (action, entity,
  from→to change, actor email, timestamp) with search. Backend `GET /dashboard/audit?limit=`
  → `AuditLogItem[]` (joins actor email). Dashboard "Recent activity" now links to it.
  Test: `test_audit_log_endpoint`.
- **Delete a job**: `DELETE /jobs/{id}` (204) — only non-active roles (active must be archived
  first → 409); cascades JD/workflow/candidates/history; audit row written before delete and
  survives. Jobs-list Delete uses a **type-to-confirm** dialog (type the job title).
  `JobService.delete_job`; test `test_delete_job_only_when_not_active`.
- **Remove a candidate from a job**: `DELETE /job-candidates/{id}` (204) — deletes the
  participation (cascades stage runs/facts/calls); the candidate person record survives.
  Candidates-row Delete uses a confirm dialog; test `test_delete_job_candidate_removes_participation`.
- **Candidate name is now a link** to `/job-candidates/{id}` (the profile/timeline).
- `ConfirmDialog` gained an optional `requireText` (type-to-confirm) prop.
- NOTE: mid-session the running server's Demo Org data was wiped (0 jobs/candidates) — the
  demo job + 7 candidates that existed earlier are gone (audit shows "job deleted"), which is
  why the candidate profile 404'd on those stale ids. Verified with fresh data that the
  profile + name-link work (timeline 200). If the demo data is needed, reseed it.
- Verification: API **118 passed**; web tsc clean; browser-verified the Audit tab, and the
  candidate profile/name-link/delete with fresh data.

## Funnel presets — predefined starter workflows, done this session

- The Funnels page now shows a **Predefined funnels** section above the org's library: three
  code-defined starter blueprints (engineering, sales, general). "Use this template" (admin)
  instantiates a preset into a real, editable funnel via `POST /funnels`, then opens it.
- Backend: `GET /funnels/presets` → `FunnelPresetOut[]`, sourced from
  `app/modules/workflows/presets.py` (read-only; presets are never stored/mutated). Registered
  BEFORE `GET /funnels/{funnel_id}` so the literal path isn't captured by the UUID param.
- Test: `test_presets_listed_and_usable`. Verification: API **115 passed**; web tsc clean;
  browser-verified the preset cards render and "Use this template" created a 4-stage funnel.

## Candidates directory — org-wide list, done this session

- New **Candidates** sidebar tab (`/candidates`) listing every candidate participation across
  all jobs (a person in N jobs appears N times, once per job). Full-width data table: name +
  contact, job (linked), current stage, pipeline state, added date, Open → (drills to the
  existing `/job-candidates/{id}` timeline). Client-side search + pipeline-state filter chips.
- Backend: `GET /candidates` (org-scoped) → `OrgCandidateListItem[]` — joins JobCandidate ↔
  Job ↔ Candidate, newest first. Test: `test_org_wide_candidate_directory`.
- New shared `.data-table` styles (responsive: stacks on mobile).
- Verification: API suite **114 passed**; web `tsc` clean; browser-verified the tab + table
  render with all candidates and working filters.

## UI polish — archive-anywhere, wider layout, real modals, done this session

- **Archive from any state**: a role can now be archived from `draft` or `active` (was
  active-only). `JobService.archive_job` allows any non-archived state and is idempotent;
  `activate_job` gates still apply to reactivation. Test renamed →
  `test_draft_role_can_be_archived`. Archive action added to each Jobs-list row and kept in
  the job workspace ("Mark inactive").
- **Reusable modal + confirmation dialog**: new `components/Modal.tsx` (accessible overlay —
  role=dialog, Escape/backdrop close, scroll lock, focus) and `components/ConfirmDialog.tsx`
  (async onConfirm with busy + inline error, `danger` variant). Replaced all `window.confirm`
  archive prompts (jobs list, job workspace, funnel detail) with `ConfirmDialog`.
- **Full-width layout**: `.container` widened 960→1400px with larger gutters
  (`40px 48px`, responsive down to `28px 20px` under 900px); `.jobs-page`/`.dashboard-page`
  bumped 1240→1400px. Buttons no longer wrap (`white-space: nowrap`; page-head actions
  `flex-shrink:0`). Verified full-width on Dashboard, Jobs, Funnels.
- **Hydration error fix**: added `suppressHydrationWarning` to `<body>` in `app/layout.tsx`
  — a browser extension (ColorZilla `cz-shortcut-listen`) mutates `<body>` before hydration;
  console now clean. Not an app bug.
- Verification: API suite **113 passed**; web `tsc --noEmit` clean; browser-verified the
  archive confirm modal, archived-state transition, wide layouts, and a clean error console.

## Funnels — reusable workflow-template library, done this session

- New **Funnels** sidebar section (`/funnels`) — the org's reusable hiring-funnel library
  (backed by the pre-existing `WorkflowTemplate` model, which had no API/UI until now).
  Design: `docs/superpowers/specs/2026-09-06-funnels-library-design.md`.
- One funnel → many jobs. "Use in a job" copies the funnel's stages into that job's own
  versioned workflow snapshot (unapproved draft), so jobs stay independent; editing a funnel
  creates a **new template version** and never disturbs jobs already using it.
- Endpoints (`app/api/routers/funnels.py`, writes admin-only): `GET/POST /funnels`,
  `GET /funnels/{id}`, `PUT /funnels/{id}/stages` (→ new version), `PATCH /funnels/{id}`
  (rename), `POST /funnels/{id}/archive`, `POST /funnels/{id}/use` ({job_id}).
- Rich stage data (purpose/info/criteria/approval) is stored in `WorkflowStageTemplate.config`
  JSONB; `WorkflowService.adopt_template` now copies all of it into job stages. Migration
  `e7c1d2f3a4b5` adds nullable `workflow_templates.archived_at` (funnels archive, not delete).
- `WorkflowEditor` was refactored to generic props (`initialStages` + `onSave` callback +
  `saveLabel`); both job call sites (`app/jobs/new`, `app/jobs/[id]`) updated — no behavior
  change for jobs. The same editor now drives job workflows and funnels.
- Verification: `tests/test_funnels.py` **6 passed**; full API suite **113 passed**; web
  `tsc --noEmit` clean. Browser-verified signed in as admin: created a funnel, applied it to
  the "Backend Engineer (via MCP)" job (job went to "Workflow v1 · draft", AI stages 1, and
  the hiring-funnel section charted the adopted stage).
- Note: migration applied to BOTH the dev DB and `recruitment_test` (the test DB persists, so
  `create_all` alone would not add the new column). Ran `next dev` (never `next build`) to
  compile/verify — do not run `next build` against a live dev server.

## Job workspace — JD view/edit + hiring funnel, done this session

- The job Overview tab now shows a **Job description** card (the latest version's raw
  `jd_text`, with a version/confirmed badge). Recruiters can **edit** it — Save creates a new
  `JobVersion` via the existing `POST /jobs/{id}/versions` flow (re-extraction runs, stays a
  draft until confirmed), and unconfirmed versions offer a Confirm action inline.
- A **Hiring funnel** section shows cumulative-reached counts per stage with conversion %
  and top-line tiles (total / in progress / rejected / completed / completion %).
- New endpoints (design: `docs/superpowers/specs/2026-09-06-job-jd-and-funnel-design.md`):
  - `GET /jobs/{id}/version` → latest `JobVersion` (now includes `jd_text`) or `null`.
  - `GET /jobs/{id}/funnel` → `FunnelOut`; funnel math is server-side (Postgres is the source
    of truth). COMPLETED counts toward every stage; a candidate's furthest-reached stage is
    their `current_stage_id` order (sourced/no-stage candidates sit at the top only).
- Verification: `tests/test_api.py` **9 passed** (incl. new funnel + latest-version tests);
  web `tsc --noEmit` clean; `next build` green; signed-in browser check confirmed both
  sections render (JD text + confirm bar; funnel tiles; per-stage bars show their empty state
  on a job with no drafted workflow).
- Note: running `next build` clobbered the live `next dev` server's `.next` dir mid-session
  (caused a `Cannot find module './294.js'` runtime error); fixed by clearing `.next` and
  restarting `next dev`. Don't run `next build` against a repo with a running dev server.

## Jobs — inactive roles, done this session

- Active roles can now be marked **Inactive** (`archived`) from their job workspace and later
  reactivated. No job, workflow, candidate, call, or audit history is deleted.
- Inactive roles are filterable on the Jobs page and clearly labeled. They reject new sourcing
  and new outreach/interview launches with an actionable HTTP 409 until reactivated.
- Verification: archive/reactivate audit test plus inactive sourcing/launch gate tests pass;
  full API suite **107 passed**, web typecheck and `git diff --check` passed. Signed-in browser
  verification remains pending a valid local authenticated session.

## Sourcing — PDL Auto mode, done this session

- The Sourcing UI now defaults to **Auto (recommended)** when People Data Labs is configured;
  manual provider selection is still available.
- Auto uses only configured PDL. It runs the exact JD-derived
  query first and, only after zero results, retries once without seniority (or without
  location when seniority is absent). The UI identifies Auto/PDL and displays the relaxation;
  it never silently fans out to other vendors.
- A missing PDL configuration returns an actionable error instead of fabricated results.
- Verification: `tests/test_sourcing.py` **11 passed**; web typecheck and `git diff --check`
  passed. Signed-in browser verification remains pending a valid local authenticated session.

## Settings — organization rename, done this session

- Admins can now rename their organization in Settings. `PUT /settings` accepts `org_name`,
  trims and validates it (non-empty, ≤120 characters), persists it without a migration, and
  records `organization.renamed` in the audit log. Non-admins retain the existing 403 gate.
- The Settings UI includes an Organization profile card with a save action for admins and a
  read-only value for other users. The screen now uses responsive Organization, Providers,
  Outreach, and Team tabs to replace the former long stacked layout.
- Verification: `tests/test_settings.py` **11 passed**; web typecheck and `git diff --check`
  passed. Browser verification remains pending a valid local authenticated session.

- **Active feature:** Auth (login + signup), candidate import + timeline UI, dashboard shell,
  **JD-from-PDF upload**, and **real Claude Haiku JD extraction** all done. Next: Phase 4
  (Apollo) or live Hunar, transition-policy auto PASS/REJECT, per-role widgets.
- **Current agent:** Claude Code
- **Branch / worktree:** repository root (`main`); commits `6dffa77` (baseline), `7640f2c`
  (auth), `cdd8190` (candidate/timeline UI), `62fa2b2` (signup/dashboard), + this session's
  PDF + Haiku commit.
- **Status:** Phases 0–3 + auth + candidate/timeline UI + dashboard + JD PDF + Claude LLM
  done. **66 API/py tests pass**; web builds + typechecks. Verified in-browser end to end.

## Sourcing — People Search & Outreach (Flow B), done this session

- **Backend:** new `app/modules/sourcing/` (`SourcingService`) + router
  `app/api/routers/sourcing.py`, exposing per-job endpoints:
  `GET /jobs/{id}/sourcing/suggested-query` (JD-derived starting query — title/location/
  skills/seniority from the latest extracted JD), `POST /jobs/{id}/sourcing/search`, and
  `POST /jobs/{id}/sourcing/add` (add selected external candidates to the pipeline as
  SOURCED, deduped by (source, source_id) within the job, reusing `CandidateService`).
- **Provider strategy (current):** Sourcing uses only the selected real provider; an
  unconfigured, plan-gated, or failed real provider returns an honest error and is never
  replaced with fabricated results. The offline `sample` provider remains available only for
  explicit test/local-development requests. Auto is PDL-only because PDL is the configured,
  configured provider, and performs a single transparent zero-result broadening retry.
- **Frontend:** Sourcing nav item enabled; new `/sourcing` page (`apps/web/app/sourcing/`).
  Role picker (JD-prefilled filters), comma-separated title/location/seniority/skills/keyword
  filters, results with select-all + per-row checkboxes, "Add N to pipeline", sample-data
  banner, empty/loading/error/pager states. Sourced search results have no contact details
  ("contact via enrichment" — mirrors real providers; enrichment is Phase 4). `lib/api.ts`
  gains `suggestedQuery`/`peopleSearch`/`addSourced` + types.
- **Verification:** `tests/test_sourcing.py` (5) — suggested query, sample search+filtering,
  Apollo-requested→sample fallback (monkeypatched, network-free), add + dedup, empty-selection
  422. **Full suite 83 passed.** Web typecheck + production build pass. Browser-verified end
  to end on localhost:3000: login → Sourcing → JD-prefill → search (sample notice) → empty
  state → broaden → 9 results → select all → "7 added · 2 skipped (already in pipeline)".
## Team invites (Settings), done this session

- **Invite flow:** new `user_invites` table (migration `d3e4f5a6b7c8`) + `invites.py` service.
  Admin creates an invite (email + role) → gets a **one-time accept link** (token shown once,
  stored only as a hash); the invitee opens it, sets a password, and joins — no email sending
  (admin shares the link), matching assignment scope. Endpoints: `POST /settings/invites`
  (admin), `DELETE /settings/invites/{id}` (admin, revoke), `GET /auth/invite?token=` (public
  preview), `POST /auth/accept-invite` (public → creates user + logs in). `GET /settings` now
  includes pending invites. Roles: recruiter | hiring_manager | admin.
- **Web:** Settings → Team shows the roster + an invite form + copyable one-time link +
  pending-invite list with Revoke. New public `/accept-invite` page (bypasses the auth shell)
  previews the invite and lets the invitee set a password to join. `config.web_base_url` builds
  the link.
- **MCP:** `invite_teammate` + `revoke_invite` tools (31 tools total).
- **Verified:** `tests/test_settings.py` +3 (create/list/revoke/accept, admin-gate + validation,
  invalid token). **Full suite 94 passed.** Browser-verified end to end: created an invite,
  accept page renders "invited to Demo Org as recruiter", accepted teammate appears on the team
  as hiring_manager, pending invite shows with Revoke.

## MCP server (conversational access), done this session

- **`apps/mcp/`** — a Model Context Protocol server exposing the platform as **27 tools** so it
  can be driven from Claude Code / ChatGPT / any MCP client. Thin wrappers over the FastAPI
  backend (business rules, gates, auth, audit preserved); assistant works in product concepts
  only. Tools cover context/dashboard, jobs+workflow (create → JD → confirm → draft → approve →
  activate, calling policy), candidates+pipeline (import, timeline, decide, launch, sync),
  sourcing (providers, suggested query, people_search, add, enrich), and admin settings.
- **Auth:** signs in once with `RECRUIT_EMAIL`/`RECRUIT_PASSWORD`, reuses the session cookie,
  auto-relogin on 401. **Transports:** stdio (default; Claude Code) and streamable-http
  (`MCP_TRANSPORT=streamable-http`, endpoint `/mcp`; ChatGPT connectors, needs a tunnel).
- **SDK note:** built on `mcp` **2.x** (`from mcp.server.mcpserver import MCPServer` — FastMCP
  was renamed). Its own venv `apps/mcp/.venv` (git-ignored). Root **`.mcp.json`** registers it
  for Claude Code in this repo. See `apps/mcp/README.md`.
- **Macro tools (one-shot journeys):** `source_and_outreach` (Flow B: search → add top N →
  enrich → launch outreach) and `import_and_interview` (Flow A: import existing candidates →
  launch interview). Both are resilient (per-candidate failure captured, others continue) and
  never bypass gates. **29 tools total.**
- **Verified live** (backend on :8000, demo admin): `whoami`, `dashboard_summary`,
  `create_job` + `add_job_description` (JD extracted), `list_people_search_providers`
  (apollo+pdl configured), and a **real PDL `people_search` → `add_sourced_candidates`**
  (real people incl. a Google backend engineer → pipeline SOURCED) — all through MCP tools.
  streamable-http boots and serves `/mcp`.

## Settings module + real multi-provider sourcing, done this session

- **Real multi-provider people search:** real adapters for Apollo (existing), **PDL, Proxycurl,
  Coresignal** (new, `app/integrations/people_search/`), all behind `PeopleSearchProvider`
  (`search()` + `enrich()`). **Sample data removed from the product flow** — it is no longer an
  automatic fallback and is not offered in the UI (kept only for tests/local dev when
  explicitly selected). A provider that is unconfigured/plan-gated/failing now raises
  `SourcingProviderError` → HTTP **502** with the real reason (e.g. "Apollo.io search failed:
  requires a paid plan (HTTP 403)"); never fabricated data.
- **Provider selection:** `GET /jobs/{id}/sourcing/providers`; the Sourcing UI has a provider
  dropdown (only real providers; unconfigured shown disabled with a Settings hint); search
  accepts a `provider` override.
- **Settings module (`/settings`, admin-managed):** new `org_settings` table
  (migration `c2d3e4f5a6b7`, org-scoped), `SettingsService`, and `GET/PUT /settings`.
  Admins set **per-provider API keys** (write-only — never returned, only a `configured`
  flag), the **default provider**, and the **live outbound-calling toggle**; the page also
  lists the team. Keys resolve org-first then `.env`, so a key saved in Settings takes effect
  immediately (search + enrichment + `configured_providers` all read the org-merged env). The
  live-calling toggle now gates real Hunar dialing (`_live_calls_ready` reads the org flag).
  Non-admins get a read-only view (PUT → 403). Settings nav item enabled.
- **Verification:** `tests/test_settings.py` (5) + updated sourcing tests. **Full suite 91
  passed.** Web typecheck passes. Browser-verified: Settings renders providers (Apollo
  configured via env, others not), default selector, live-calling toggle, team; Sourcing
  provider dropdown + honest 502 error shown for plan-gated Apollo.
- **To get real search results:** an admin pastes a working key in Settings (recommended:
  a free **People Data Labs** key — single-endpoint search returns full profiles). Apollo's
  provided key is Free-plan and returns 403 for Search (confirmed live).
- Note: demo user `recruiter@demo.test` is created as a recruiter by `dev/bootstrap`; promote
  to admin (`UPDATE users SET role='admin' …`) or use "Create account" (first user = admin) to
  edit Settings.

## Sourcing Phase 4 — enrichment + outreach, done this session

- **Enrichment:** `POST /job-candidates/{id}/enrich` (`SourcingService.enrich`) reveals a
  sourced candidate's phone/email so an outreach call can be placed. Provider boundary gained
  `EnrichmentResult` + `enrich()`. The `sample` provider returns a deterministic, reserved
  test number (`+1-555-01xx`, `example.com` email) — never a real person. Apollo's `enrich`
  raises (its phone reveal is async via `/people/match` webhook + paid plan), so the service
  **degrades to the flagged sample contact** rather than failing. Writes phone/email to the
  Candidate + facts (provenance), moves `SOURCED → OUTREACH_PENDING`, audited. Idempotent.
- **Outreach:** reuses the existing `POST /job-candidates/{id}/launch` (Hunar dispatch); the
  launch endpoint now moves a `SOURCED`/`OUTREACH_PENDING` candidate to `CONTACTED` (audited).
- **Web:** candidate detail page shows **Enrich contact** when no phone, then **Start outreach
  call** (disabled until enriched); notice shows the revealed number and sample flag.
  `lib/api.ts` gains `enrichCandidate` + `EnrichResult`.
- **Verification:** `tests/test_sourcing.py` now 7 (enrich→outreach→CONTACTED, idempotent
  enrich, provider-unavailable→sample fallback). **Full suite 85 passed.** Web typecheck +
  build pass. Browser-verified end to end: SOURCED → enrich (`+1-555-1001`, OUTREACH_PENDING)
  → outreach (CONTACTED, call attempt, FAILED on the non-routable sample number → Retry).
- **Next (Phase 4b):** real Apollo enrichment via the async `/people/match` webhook once a
  paid/scoped key exists; until then the sample fallback keeps outreach demonstrable.

## Job hub — workflow + pipeline UI (done this session)

- `GET /jobs/{id}/workflow` returns the effective workflow (approved else latest draft) with
  full stage detail (purpose, execution_type, information_requirements, requires_human_approval,
  weighted criteria). New page `/jobs/[id]`: the **hiring workflow** as a connected stage flow
  (exec-type badges, "collects" chips, criteria + weights) and a **pipeline board** (columns =
  stages, cards = candidates in their current stage). Jobs list + dashboard link to this hub.
- Still POC-ish / next for "full product": in-UI stage & criteria **editing** (currently the
  draft is auto-generated then read-only), calling-window/language config UI, and
  decision/approval actions on NEEDS_REVIEW candidates (advance/reject with audited outcome).

## Calling policy — done this session

- `GET/PUT /jobs/{id}/calling-policy` persists the job's allowed days, calling window, IANA
  timezone, attempts, retry interval, and preferred Hunar-agent language. It validates the
  verified Hunar constraints (a complete guardrail: timezone, start/end, at least three days,
  at least a three-hour window; supported retry intervals/languages; 1–10 total attempts).
  It audits each save, and `HunarDispatchService` maps the policy into `guardrails` and
  `retry_config` when making a live call.
- The job hub renders a saved calling-policy card. It explicitly says that language is
  agent-level and is only a stored preference pending a future agent-configuration update; it
  is not a per-call override. Browser verified through signup → job creation → save policy;
  the workflow 404 was intentionally rendered as the empty-workflow state. Full test suite:
  **78 passed**; web typecheck and production build pass.
- Local demo caveat: the full test suite truncates the dev DB. It removed the prefilled demo
  user in this session; restored via `POST /dev/bootstrap` with
  `recruiter@demo.test` / `demo-password`.

## Create-job workflow UI refresh — done this session

- `/jobs/new` now presents the original server-backed create → extract → confirm → draft →
  edit → approve → activate journey as a four-step, responsive hiring-workflow wizard. It has
  visible progress/status states, constrained content cards, extraction-review context, and a
  clear approval/activation handoff; no job or workflow API/state transition changed.
- `WorkflowEditor` now uses labelled, responsive stage cards with execution type, purpose,
  collected information, human-approval guidance, weighted criteria, and accessible stage
  reorder controls. Native select controls receive the same dark field treatment as inputs.
- Verified after the change: `npm run typecheck`, `npm run build`, and browser flow through
  job creation, JD confirmation, and workflow drafting, including a 360px-wide visual check.

## Job workspace UI refresh — done this session

- `/jobs/{id}` is now an operational workspace with Overview, Workflow, Pipeline, and Calling
  policy tabs. A recruiter can reopen an unapproved draft, edit and save its stages, then
  approve it; approved versions are clearly read-only and activation remains server-gated.
- Browser verified the overview, tab navigation, draft editor, and a successful workflow save.

## JD PDF upload + Claude Haiku extraction — done this session

- **JD from PDF:** `POST /jobs/{job_id}/versions/upload` (multipart) extracts text with `pypdf`
  and runs the **same** JD-version path as pasting. Rejects non-PDF, >10 MB, and scanned/
  image-only PDFs (no extractable text) with clear 422s. Helper `app/api/pdf.py`. Web: the
  Create-Job "Job description" step now has a **Paste text / Upload PDF** toggle with a
  dropzone (`api.addVersionFromPdf`). Tests: `test_jd_pdf.py` (5).
- **Claude Haiku LLM:** `app/integrations/llm/anthropic_provider.py` (`AnthropicLLMProvider`)
  uses Claude (`claude-haiku-4-5`) for JD extraction when `PLATFORM_LLM_API_KEY` is set;
  otherwise the deterministic stub. Registry selects it; any API/parse error falls back to the
  stub so the flow never breaks. `.env`: `PLATFORM_LLM_API_KEY` (Anthropic sk-ant-… key) +
  `PLATFORM_LLM_MODEL` (default claude-haiku-4-5). Deps added: `pypdf`, `python-multipart`,
  `anthropic`. Tests: `test_llm_anthropic.py` (5, network-free via monkeypatch).

## Signup + dashboard shell — done this session

- **Signup:** `POST /auth/signup` (name, email, password, optional org_name) → creates a new
  org + first **admin** user, logs them in (cookie). Email globally unique (409 on dup);
  `auth.create_account` (HTTP-free) + `EmailTakenError`. `/auth/me` and login/signup now
  return name + email. Tests in `test_auth.py` (signup, dup, dashboard summary). 56 pass.
- **Dashboard API:** `GET /dashboard/summary` (org-scoped counts: total/active jobs,
  candidates in pipeline, needs_review, awaiting_result, failed_calls) and
  `GET /dashboard/activity` (last 15 audit events). New router `app/api/routers/dashboard.py`.
- **Web shell:** `lib/auth.tsx` (AuthProvider/useAuth), `components/AppShell.tsx` (sidebar:
  Dashboard, Jobs, Sourcing/Settings=soon; user footer + sign out; mobile-collapsing),
  `components/AuthScreen.tsx` (Sign in / Create account tabs, demo creds pre-filled). Root
  layout wraps everything; unauthenticated → AuthScreen. Pages: `/` = action-oriented
  dashboard (stat widgets + active jobs + recent activity + Create Job CTA), `/jobs` = jobs
  list. Candidate list/detail pages now render inside the shell.
- **Demo creds:** `recruiter@demo.test` / `demo-password` (pre-filled on the sign-in tab).

## Real auth (session cookies) — done this session

- Mechanism: HttpOnly + SameSite=Lax session cookie backed by a `user_sessions` table
  (Postgres, durable + revocable). Endpoints `POST /auth/login`, `POST /auth/logout`,
  `GET /auth/me` (`app/api/routers/auth.py`). `deps.get_principal` now resolves the cookie.
- Passwords: PBKDF2-HMAC-SHA256, stdlib only (`app/security/passwords.py`); `users.password_hash`
  added (nullable). Only a SHA-256 hash of each session token is stored. Login is
  case-insensitive on email and non-enumerating (wrong password == unknown user == no-password).
- `POST /dev/bootstrap` now sets a password so you can then log in; CORS `allow_credentials=True`.
- Config: `SESSION_COOKIE_NAME`, `SESSION_COOKIE_SECURE` (must be 1 in prod), `SESSION_TTL_HOURS`.
- Web: `lib/api.ts` uses `credentials:"include"` + `me/login/logout`; dashboard has a real
  sign-in form (+ "create demo org" dev convenience) and sign-out. shadcn/ui still not added.
- Migration `app/modules/organizations/migrations/b1f2c3d4e5f6_users_password_and_sessions.py`
  (down_revision `4dfb8fbd7911`). Tests: `tests/test_auth.py` (12) + `test_api.py` updated to
  log in.

## Completed work

- **F-001 (Phase 0):** Hunar contract VERIFIED (docs+OpenAPI+read-only live). Apollo verified
  from docs; adapter `search()` wired. Live Apollo: key valid but Search endpoint 403 (Free
  plan) — needs paid plan or a different provider (multi-provider by ADR-0001).
- **F-002 (Phase 1) — DONE:**
  - 25 SQLAlchemy models under `apps/api/app/modules/<name>/models.py`, shared `Base`.
  - Per-module Alembic migrations (Django-app style) — one linear history; reversible
    round-trip verified on Postgres 16.
  - `apps/api/app/workflow_execution/`: pure `state_machine.py` (legal transitions + outcome
    mapping) and `WorkflowExecutionService` (enforced transitions, audit on every move,
    candidate advancement, explicit audited overrides).
  - Tests in `apps/api/tests/` — **23 passing** (pure unit + DB-backed service).
  - Docs updated to match: `architecture.md` (realized layout + WorkflowExecutionService),
    `domain.md` (enforced transitions + outcomes), `apps/api/README.md`, roadmap, INDEX.

## Verification

- `python -m pytest -q` → **38 passed** (Postgres up, `DATABASE_URL` set).
- `alembic upgrade head` → 25 tables; `downgrade base`→0→`upgrade head`→25. 10 CHECKs enforce.
- Toolchain in `apps/api/.venv` (git-ignored): SQLAlchemy 2.0.52, Alembic 1.19.2,
  psycopg 3.3.5, pytest 9.1.1 (pinned in `requirements.txt`).

## Phase 2 (F-003) — done this session

- LLM boundary `app/integrations/llm/` (protocol + deterministic offline stub + registry).
- `JobService` (create → add JD version w/ extraction → confirm → activate, gated) and
  `WorkflowService` (draft/adopt/approve; unapproved until human). Shared `audit/log.py`.
- Gates enforced: activation blocked unless latest JD confirmed AND a workflow version approved.
- `tests/test_job_creation.py` (6 tests). Full suite **29 passed**. Docs updated
  (architecture realized layout, interfaces LLM boundary, roadmap, INDEX, F-003).

## Phase 3 (F-004) — done this session

- `CandidateService.import_candidate` (facts+provenance; later starting stage audited),
  `InterviewService.launch_ai_stage` (Call + attempt, run→AWAITING_RESULT, Hunar payload with
  effective-info `custom_data.collect`), `WebhookService.handle_hunar_event` (idempotent,
  status normalize, StageResult, fact enrichment, run→NEEDS_REVIEW).
- Pure `compute_effective_information` (carry-forward) + Hunar status map + payload builder.
- Tests `test_effective_info.py` + `test_interview_flow.py`. Full suite **38 passed**.

## App scaffold (F-005) — done this session

- FastAPI: `app/main.py`, `app/config.py`, `app/db/session.py`, `app/api/` (routers, deps,
  errors, schemas). Routers: jobs, candidates, interviews, webhooks, system (`/health`,
  `/dev/bootstrap`). Dev-stub auth via `X-Org-Id`/`X-User-Id`. `tests/test_api.py` (HTTP e2e).
- Next.js (`apps/web`): dashboard + guided job-creation flow + typed `lib/api.ts`. Plain CSS
  (shadcn/ui intended next; no Tailwind). `npm run build` + `npm run typecheck` pass.

## Docker (this session)

- `apps/api/Dockerfile` + `docker-entrypoint.sh` (runs `alembic upgrade head` when
  `RUN_MIGRATIONS=1`, then uvicorn). `compose.yaml` `api` service imports root `.env`
  (`env_file`) and overrides `DATABASE_URL`/`REDIS_URL` to the compose services; healthcheck
  on `/health`. Fixed `requirements.txt` → `psycopg[binary]` (slim image had no libpq).
- Verified: `docker compose up -d --build api` → healthy; `/health` 200; bootstrap + create
  job work; `.env` keys present in container.

## Remaining work

1. **shadcn/ui components** (shell is currently hand-rolled CSS); **per-role** dashboard
   widgets/permissions (owner vs recruiter — arch §30/Q22); invite teammates + password-reset.
2. **Live Hunar:** POST the built payload in a Celery task once a phone number is provisioned.
3. **People search:** enable/upgrade Apollo key (403) or switch provider; then Phase 4 outreach.
4. Transition-policy JSON evaluation (auto PASS/REJECT); calling-window/guardrails scheduling;
   deployment.

## Risks / open questions

- Apollo Search 403 (key lacks API access). Provider choice pending.
- **Hunar live calls WIRED INTO THE PRODUCT (2026-09-06):** the launch endpoint now places a
  real call. `HunarClient` has real HTTP; `HunarDispatchService` (`app/modules/interviews/
  dispatch.py`) resolves the agent (stage `HunarAgentConfig` → else `HUNAR_DEFAULT_AGENT_ID`),
  fills the agent's `required_variables` into `custom_data`, POSTs `/calls/`, and records the
  outcome on the Call; a Celery task (`app/tasks.py`, eager in dev) runs it. Verified live
  end-to-end via `POST /job-candidates/{id}/launch` → `dispatched:true` + real `hunar_call_id`,
  status synced SCHEDULED→CALLING→NO_ANSWER (a rejected call).
- **Automatic results via webhook (wired):** when `PUBLIC_BASE_URL` is set, each dispatched
  call registers Hunar `callback_config` (status/result/recording/summary → our
  `POST /webhooks/hunar`), so results/recordings post back automatically and ingest via the
  existing `WebhookService` (facts + run→NEEDS_REVIEW). Verified end-to-end in the UI: a
  COMPLETED call populated Evidence & Results (interested/expected_ctc/notice_period) and moved
  the stage to NEEDS_REVIEW. In local dev a public URL needs a tunnel (`cloudflared tunnel
  --url http://localhost:8000`); the free quick-tunnel is flaky, so `POST /calls/{id}/sync`
  ("Sync from Hunar" button) is the reliable on-demand fallback (same ingestion code). In prod,
  set `PUBLIC_BASE_URL` to the deployed https domain — no tunnel, fully automatic.
- **Rejected / unanswered handling:** a terminal not-connected call (NO_ANSWER/FAILED/CANCELLED)
  with no result moves the run AWAITING_RESULT→FAILED with a reason + audit (never stuck);
  RETRY_SCHEDULED (retries left) keeps it AWAITING_RESULT. Re-launching a FAILED/CANCELLED run
  starts a **fresh** run (UI shows "Retry call"). Results/recordings still arrive async via the
  webhook; `POST /calls/{id}/sync` pulls status on demand when no public webhook URL is set.
- **Safety:** live calls fire ONLY when `HUNAR_LIVE_CALLS_ENABLED=1` AND a key is set (default
  off); tests force these off in conftest so the suite never dials. Celery eager by default (no
  worker needed); set `CELERY_TASK_ALWAYS_EAGER=0` + run `celery -A app.tasks worker` in prod.
- **Test suite truncates the dev DB:** the HTTP test fixtures run `TRUNCATE organizations …
  CASCADE`, so running `pytest` against the same `DATABASE_URL` used for a live demo wipes
  demo data (incl. the demo account). Re-seed the demo account after a full test run, or use a
  separate test database. Worth fixing later (dedicated test DB / transactional client).
- **Local Postgres:** this session Docker Desktop was down, so a local `postgresql@14` (brew)
  was started and a `recruitment` role/db provisioned + migrated. The compose Postgres path
  still works when Docker is running.

## Exact next action

Ask which to do next: (a) implement the Sourcing and Settings product flows, (b) adopt
shadcn/ui + per-role dashboard widgets, (c) Phase 4 people-search outreach (needs a working
provider key), or (d) wire live Hunar via Celery (needs a provisioned number). Current changes
are uncommitted on `main`; preserve the existing calling-policy work when integrating.

## How to run (demo)

```
docker compose up -d postgres
cd apps/api && . .venv/bin/activate && export DATABASE_URL=postgresql://recruitment:recruitment@localhost:5432/recruitment
alembic upgrade head && uvicorn app.main:app --reload      # :8000
cd ../web && cp .env.local.example .env.local && npm install && npm run dev   # :3000
```
