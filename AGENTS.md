# Codex — Adapter

You are working in the **AI Recruitment Workflow** repository. The Git repo is the durable
source of truth, not this conversation. Shared rules live in the documents below — this
adapter points you to them and does not duplicate them.

## Read before any meaningful work

Always:

1. `PROJECT.md` — canonical orientation.
2. `docs/agent-handbook.md` — the required loop (follow it exactly).
3. `docs/quality.md` — Definition of Ready / Done, evidence standards.
4. `docs/task-intake.md` — classify the task tier before planning.

For the task at hand, also read:

- The relevant feature brief in `docs/features/` (and update `docs/work/active-feature.md`).
- The relevant canonical doc: `architecture.md`, `domain.md`, `interfaces.md`, or `experience.md`.
- `docs/vendor-capability-matrix.md` for anything touching Hunar or Apollo.

## The loop (from the handbook)

Request → classify risk → confirm Definition of Ready → inspect relevant code and docs →
plan → implement one vertical slice → run automated checks → verify browser behavior when
relevant → fresh review → safe release → update durable project knowledge.

## Non-negotiables

- Inspect code before making claims. Never invent vendor behavior — treat anything not
  marked `VERIFIED` as unverified.
- Keep changes small and reversible. Implement failure, recovery, authorization, and edge
  states, not only happy paths.
- Update documents per the documentation-impact level in `docs/task-intake.md`.
- Before ending an incomplete session or switching agents, write a handoff in
  `docs/work/active-feature.md` so Claude Code or Antigravity can continue safely.
- Report verification evidence and remaining limitations before claiming completion.

## Continuing after another agent

If a Claude Code or Antigravity session stopped mid-task, resume from
`docs/work/active-feature.md`: read its "exact next action" and branch/worktree, confirm
Definition of Ready, then continue the loop.
