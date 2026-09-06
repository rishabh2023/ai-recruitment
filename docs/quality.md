# Quality

Definition of Ready, Definition of Done, release controls, and evidence standards.

> A feature is **not** complete merely because its happy path works. Completion requires
> risk-appropriate proof and explicit handling of failure, recovery, authorization, and
> edge states.

## Definition of Ready (before implementation starts)

- Task tier classified (`docs/task-intake.md`) and documentation-impact level identified.
- The relevant feature brief exists in `docs/features/` and is linked from `INDEX.md`.
- Requirements and acceptance criteria are written and unambiguous.
- Any vendor capability the work depends on is `VERIFIED` (or the work is explicitly the
  verification itself, e.g. F-001).
- Affected domain entities, state transitions, and interfaces are identified.
- Failure, edge, authorization, and recovery cases are enumerated (see the edge-case
  checklist below).
- A rollback/recovery approach is known for High-Risk work.

## Definition of Done

- Acceptance criteria met and demonstrated with evidence (not asserted).
- Automated checks pass (see evidence standards) at the level the tier requires.
- Failure/recovery, authorization, and edge states implemented — not only the happy path.
- Observability added where the change introduces external calls, background work, or state
  transitions (traces/spans, error reporting, relevant metrics).
- Documents updated per the documentation-impact level.
- Fresh review completed.
- Handoff / `docs/work/active-feature.md` updated if work is incomplete or an agent switch is
  imminent.
- Remaining limitations and unverified assumptions stated explicitly.

## Evidence standards (risk-appropriate proof)

Provide proof appropriate to the change. Higher tiers require more of the following:

- **Type checks** — TypeScript / Python typing pass.
- **Linting** — clean.
- **Unit tests** — core logic, including failure branches.
- **Integration tests** — cross-module / DB / adapter behavior.
- **Webhook & idempotency tests** — duplicate delivery does not double-advance state.
- **State-transition tests** — stage-run and call lifecycle transitions, including invalid
  transitions rejected.
- **Browser verification** — user-facing flows verified in a browser, including required
  states from `docs/experience.md`.
- **Authorization checks** — cross-org / cross-role access denied; candidate data protected.
- **Failure / retry tests** — external API failure, timeout, partial result, business vs
  infrastructure retry.
- **Observability** — spans/errors/metrics present and correct.
- **Staging verification** — exercised in a staging-like environment for High-Risk work.
- **Rollback / recovery plan** — documented and, where feasible, tested.
- **Fresh review** — a review pass independent of the implementation narrative.

State which of these were run and show the output. "Tests pass" without evidence is not
acceptable.

## Edge-case discipline (consider for each meaningful feature)

Happy path · existing/partially known data · missing required data · human intervention ·
skip/override · duplicate request/event · partial success · external API failure ·
retryability · timeout/worker crash · authorization · auditability · versioning ·
user-visible recovery / next action.

## Release controls

- Small, reversible changes; prefer vertical slices.
- Default change size ≤ ~12 files unless closure genuinely requires more.
- No merge unless explicitly requested. Publish draft PRs; inspect exact-head CI.
- Secrets never committed; any exposed key is rotated.
- Migrations are reversible and reviewed; data-affecting changes have a recovery plan.
