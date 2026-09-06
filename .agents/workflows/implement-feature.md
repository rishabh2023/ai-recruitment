# Workflow: Implement a Feature

Agent-neutral procedure for delivering a feature. Follows `docs/agent-handbook.md`.

## 1. Classify

- Determine the **task tier** and **documentation-impact level** (`docs/task-intake.md`).
- Confirm a feature brief exists in `docs/features/` and is linked from `INDEX.md`. If not,
  create it from `FEATURE_TEMPLATE.md`.

## 2. Confirm Definition of Ready

- Check every item in `docs/quality.md` → Definition of Ready.
- Confirm all depended-on vendor capabilities are `VERIFIED` in
  `docs/vendor-capability-matrix.md` (or the feature *is* the verification).
- Stop and resolve blockers before writing code.

## 3. Inspect

- Read the relevant canonical docs and the actual code paths involved. Do not assert
  behavior you have not read.

## 4. Plan

- Write acceptance criteria and enumerate edge/failure/authorization/recovery cases (from
  the checklist in `docs/quality.md`) into the feature brief.
- Break the work into small, reversible vertical slices.

## 5. Implement one slice

- Match surrounding code style. Implement failure, recovery, authorization, and edge states
  — not only the happy path.
- Keep the change small (default ≤ ~12 files unless closure requires more).

## 6. Prove it

- Run the checks the tier requires (`docs/quality.md` evidence standards) and capture output.
- Verify user-facing flows in a browser, including the required states in
  `docs/experience.md`.
- Add observability for new external calls, background work, or state transitions.

## 7. Review and release

- Run `.agents/workflows/review-feature.md` (fresh review).
- Publish a draft PR; inspect CI at exact head. **No merge unless explicitly requested.**

## 8. Update durable knowledge

- Update docs per the impact level; update the feature brief, `INDEX.md`, and
  `docs/work/active-feature.md`. Write an ADR for Level 3.
- State remaining limitations and unverified assumptions explicitly.
