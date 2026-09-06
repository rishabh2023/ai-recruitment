# Codex / Antigravity — `apps/web` (Next.js frontend)

The Next.js + React + TypeScript recruiter console lives here (scaffolded in F-005; builds and
typechecks). shadcn/ui is the intended component layer, not yet added (no Tailwind). See
`apps/web/README.md`.

## Before working here

Read the root `AGENTS.md` (Codex) or `.agents/rules/project-context.md` (Antigravity) first,
then:

- `PROJECT.md`, `docs/agent-handbook.md`, `docs/quality.md`, `docs/task-intake.md`
- `docs/experience.md` — the authoritative UX contract (required states, role-aware
  dashboard shell, pipeline-board-as-view, pre-launch review, approval gates).
- `docs/interfaces.md` — API and error conventions this app consumes.

## Frontend-specific expectations

- The UI renders state; it is never the source of truth.
- Every meaningful flow implements the full set of required states from `docs/experience.md`
  (loading, empty, success, validation error, external API failure, partial data, permission
  denied, retry/recovery, desktop + mobile, basic accessibility).
- Recruiters see product concepts only — never Hunar internals.
- Secrets are server-side only; never `NEXT_PUBLIC_*`.
