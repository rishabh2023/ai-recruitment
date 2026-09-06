# Agent Handbook

This is the **agent-neutral** loop every coding agent (Claude Code, Codex, Antigravity, and
future agents) follows. The Git repository is the durable source of truth — not any single
agent conversation.

## The required loop

```
Request
→ classify risk
→ confirm Definition of Ready
→ inspect relevant code and documents
→ plan
→ implement one vertical slice
→ run automated checks
→ verify browser behavior when relevant
→ fresh review
→ safe release
→ update durable project knowledge
```

1. **Classify risk** — use `docs/task-intake.md` to pick the tier and documentation-impact
   level.
2. **Confirm Definition of Ready** — `docs/quality.md`. Do not start implementation until it
   is satisfied.
3. **Inspect** — read the relevant documents (below) and the actual code before making any
   claim about behavior.
4. **Plan** — acceptance criteria + enumerated edge/failure/authorization/recovery cases.
5. **Implement one vertical slice** — small and reversible.
6. **Run automated checks** — at the level the tier requires; show the output.
7. **Verify browser behavior** — for user-facing flows, including the required states in
   `docs/experience.md`.
8. **Fresh review** — a review pass independent of the implementation narrative.
9. **Safe release** — draft PR, inspect CI at exact head; no merge unless explicitly
   requested.
10. **Update durable knowledge** — docs per the impact level; `docs/work/active-feature.md`;
    feature brief; `INDEX.md`; an ADR for Level 3.

## What every agent must do

- **Read relevant documents before meaningful work:** `PROJECT.md`, `docs/quality.md`,
  `docs/task-intake.md`, the relevant feature brief, and the relevant
  `architecture` / `domain` / `interfaces` / `experience` document. Read
  `docs/vendor-capability-matrix.md` for anything touching Hunar or Apollo.
- **Inspect code before making claims.** Do not assert behavior you have not read.
- **Never invent vendor behavior.** Treat anything not `VERIFIED` as unavailable and use the
  documented safe fallback.
- **Keep changes small and reversible.**
- **Implement failure, recovery, authorization, and edge states** — not only happy paths.
- **Update project documents** based on the documentation-impact level.
- **Create a handoff before switching agents or ending incomplete work** — write
  `docs/work/active-feature.md` (completed work, verification, remaining work, risks,
  decisions, branch/worktree, exact next action).
- **Report verification evidence and remaining limitations before claiming completion.** No
  vague completion statements.

## Handoff contract

Because a session may reach its limit at any time, any other agent must be able to resume
safely from `docs/work/active-feature.md` alone. Keep it current: it names the exact next
action and the branch/worktree.
