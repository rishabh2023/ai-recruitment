# Claude Code — Adapter

You are working in the **AI Recruitment Workflow** repository. The Git repo is the durable
source of truth, not this conversation. Shared rules live in the documents below — this
adapter only points you to them; it does not duplicate them.

## Read before any meaningful work

Always:

1. [`PROJECT.md`](PROJECT.md) — canonical orientation.
2. [`docs/agent-handbook.md`](docs/agent-handbook.md) — the required loop (follow it exactly).
3. [`docs/quality.md`](docs/quality.md) — Definition of Ready / Done, evidence standards.
4. [`docs/task-intake.md`](docs/task-intake.md) — classify the task tier before planning.

For the task at hand, also read:

- The relevant feature brief in [`docs/features/`](docs/features) (and update
  [`docs/work/active-feature.md`](docs/work/active-feature.md)).
- The relevant canonical doc: `architecture.md`, `domain.md`, `interfaces.md`, or `experience.md`.
- [`docs/vendor-capability-matrix.md`](docs/vendor-capability-matrix.md) for anything touching Hunar or Apollo.

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
  `docs/work/active-feature.md` (completed work, verification, remaining work, risks,
  decisions, branch, exact next action) so Codex or Antigravity can continue safely.
- Report verification evidence and remaining limitations before claiming completion.
  No vague completion statements.

## Attribution

- End git commit messages with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- End pull request descriptions with:
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
