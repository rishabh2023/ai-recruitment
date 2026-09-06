# ADR-0002: Use Hunar native guardrails, retry, and runtime context; platform coordinates the gaps

- **Status:** Accepted
- **Date:** 2026-09-06
- **Deciders:** Rishabh (owner), Claude Code
- **Documentation-impact level:** 3

## Context

F-001 verified the Hunar external API (`[docs]` + `[openapi]` + read-only `[live]` calls).
Three findings change earlier assumptions:

1. **Runtime context exists** — `custom_data` on single/bulk calls plus agent
   `custom_variables`/`required_variables`.
2. **Native calling guardrails exist** — `guardrails.allowed_days` (min 3 distinct),
   `earliest_call_time`/`last_call_time` (HH:MM, min 3-hour window), IANA `timezone`.
3. **Native retry exists** — `retry_config.max_retry_count` (0–10),
   `retry_interval_hours` ∈ {0,3,6,9,12,24}; NOT_CONNECTED eligible; response exposes
   `retry_count`/`retries_left`/`next_retry_scheduled_at`.

## Decision

- **Hunar provisioning:** reuse a per-job/stage agent configuration and inject stage +
  candidate context via `custom_data` at call time. Do **not** create an agent per candidate.
  This confirms the "reuse agent + runtime context" branch of the stage-driven model
  (`docs/architecture.md`), superseding any per-candidate provisioning idea.
- **Calling windows:** pass the recruiter's calling policy to Hunar `guardrails`. The
  platform still owns policy the recruiter configures and **coordinates the cases Hunar's
  constraints cannot express** (e.g. fewer than 3 allowed days, sub-3-hour windows, blackout
  dates), scheduling the next valid attempt itself rather than sending an invalid guardrail.
- **Retry:** use Hunar native retry for call-level redial of NOT_CONNECTED. The platform owns
  **business** retry policy (attempt caps, "call me later", per-job/stage overrides) and does
  not run a competing redial engine. Infrastructure retries (timeouts, worker/API failures)
  never consume a candidate-contact attempt unless a call was actually initiated.
- **Language:** exposed at agent → job/stage level (Hunar sets language on the agent, not per
  call). No per-candidate language override is offered unless Hunar adds one.
- **Recording:** consume `recording_url` / `call_recording_done` only; no enable/disable
  control (none is exposed).
- **BYO telephony:** unsupported via API; use org-provisioned Hunar numbers.

## Alternatives considered

- **Platform-only calling window / retry engine** — rejected: duplicates verified Hunar
  behavior and risks two competing engines. The platform fills only the documented gaps.
- **Per-candidate Hunar agents** — rejected: unnecessary given `custom_data`; harms
  auditability and cost.

## Consequences

- Positive: less platform code, uses vendor-native reliability, keeps the stage-driven model
  intact, clean audit of what was passed per call.
- Trade-off: platform must detect when a desired policy falls outside Hunar's guardrail
  constraints and coordinate scheduling itself; retry accounting must reconcile platform vs
  Hunar attempt counters.
- **Operational note:** the assignment key currently has **0 provisioned numbers**
  (`GET /numbers/` count 0), so live outbound calls need a `from_phone_number`/number first.

## Evidence / references

`docs/vendor-capability-matrix.md` (Hunar rows, F-001 evidence); OpenAPI spec;
`apps/api/app/integrations/hunar/`; `docs/architecture.md` §"Hunar provisioning boundary".
