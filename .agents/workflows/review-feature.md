# Workflow: Review a Feature

Agent-neutral fresh-review procedure. A review is a pass **independent** of the
implementation narrative — verify against the docs and the code, not against the author's
claims.

## 1. Establish intent

- Read the feature brief (`docs/features/`) and its acceptance criteria.
- Read the relevant canonical docs (`architecture` / `domain` / `interfaces` / `experience`
  / `quality`).

## 2. Verify against Definition of Done

Check each item in `docs/quality.md` → Definition of Done. Do not accept assertions without
evidence.

## 3. Correctness and scope

- Acceptance criteria actually met and demonstrated.
- Change is a small, reversible vertical slice; no unrelated refactors; no unnecessary
  dependencies; no hand-edited generated output.

## 4. Failure, edge, authorization, recovery

Walk the edge-case checklist (`docs/quality.md`): partial data, external API failure,
duplicate events/idempotency, retryability (business vs infrastructure), timeout/worker
crash, authorization/cross-org, auditability, versioning, user-visible next action. Confirm
each relevant case is handled and tested.

## 5. Vendor discipline

- No capability relied on that is not `VERIFIED`. No UI control around an unverified
  capability. Safe fallbacks present where a capability is `UNKNOWN`.

## 6. Observability and security

- Traces/spans/metrics/errors present for external calls, background work, and transitions.
- No secrets committed or logged; candidate data protected; audit events emitted for
  consequential actions.

## 7. Documentation

- Docs updated to the correct impact level; `INDEX.md`, the brief, and
  `docs/work/active-feature.md` current; ADR present for Level 3 decisions.

## 8. Verdict

State clearly: pass, or the specific blocking issues with file/line references and the
required change. Note remaining limitations.
