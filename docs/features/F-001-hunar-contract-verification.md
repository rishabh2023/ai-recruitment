# F-001: Hunar Contract Verification

- **Status:** In progress — Hunar contract **VERIFIED** (docs + OpenAPI + read-only live); Apollo/people-search verification pending; live outbound test call blocked (no provisioned number)
- **Risk tier:** High Risk (external integration; foundational to every later phase)
- **Documentation-impact level:** 2–3 (updates the capability matrix; ADRs where a verified
  result changes an architectural/product decision)
- **Affected areas:** a sandbox/spike Hunar adapter, `docs/vendor-capability-matrix.md`,
  `docs/decisions/`
- **Depends on:** Hunar sandbox/test credentials and API documentation; Apollo test
  credentials and documentation
- **Owner / current agent:** TBD

## Problem / intent

Every later phase assumes things about Hunar (and Apollo) that are currently `UNKNOWN`. The
FDE discipline is: **never design a product control around a vendor capability that has not
been verified.** F-001 verifies the documented capabilities in a sandbox or safe test
environment and records evidence, so Phases 1–5 can depend on facts rather than assumptions.

This feature deliberately produces **verification evidence and an updated capability matrix**
— not product features and not a recruiter-facing UI.

## Scope

**In scope**

- A minimal, isolated adapter/spike (kept out of the eventual product code path) that
  exercises Hunar's documented endpoints against sandbox/test credentials.
- Verifying each Hunar capability listed below and recording the exact contract.
- Verifying the Apollo contract at the level needed to plan Phase 4.
- Updating `docs/vendor-capability-matrix.md` with `VERIFIED`/`UNKNOWN`/`UNSUPPORTED` +
  evidence pointers, and writing ADRs where a verified result changes a decision (e.g.
  whether runtime context removes the need for per-stage agent provisioning; whether native
  retry is used; whether recording fields exist).

**Out of scope**

- Any product feature, database schema, recruiter UI, or Celery pipeline.
- Placing real calls to real candidates. Use sandbox/test numbers only.
- Building the production Hunar adapter (Phase 3+); this is a throwaway spike whose output is
  knowledge.

## Vendor capabilities to verify

From `docs/vendor-capability-matrix.md` — all currently `UNKNOWN`:

**Hunar** — authentication · agent create/update · runtime/custom variables · outbound single
call · bulk call · webhook events (types, payload, signature/validation) · call status/result
retrieval · structured result/evaluation schema · retry behavior (native) · language support
· recording/transcript behavior · BYO telephony · documented call statuses (for the
normalized mapping in `docs/domain.md`).

**Apollo** — authentication · people-search params/filters · returned profile fields ·
contact/phone availability · rate limits/pagination.

## Acceptance criteria

- [ ] For each capability above: a status of `VERIFIED` / `UNKNOWN` / `UNSUPPORTED` with an
      evidence pointer (doc link, sandbox test location, or captured payload).
- [ ] Documented exact request/response shapes for every `VERIFIED` Hunar capability
      (enough to design the real adapter interface in `docs/interfaces.md`).
- [ ] A documented mapping from Hunar's real call statuses to the normalized statuses in
      `docs/domain.md` (or a note that it must be revised).
- [ ] A documented webhook event shape + a stable idempotency/dedup key strategy based on
      real identifiers.
- [ ] A clear finding on whether runtime/custom context is sufficient to avoid per-stage
      agent provisioning (informs `docs/architecture.md` §"Hunar provisioning boundary").
- [ ] Findings on retry, language, and recording that confirm or revise the safe fallbacks.
- [ ] `docs/vendor-capability-matrix.md` updated; ADR(s) written for decisions that change.
- [ ] No secrets committed; sandbox credentials handled server-side/in env only.

## Edge / failure / authorization cases to probe

Auth failure/expiry · malformed/duplicate webhook · webhook signature absent or
unverifiable · call to invalid/missing phone · successful call with incomplete structured
output · timeouts · rate limiting · fields documented but absent in practice · differences
between documentation and sandbox behavior.

## Plan (vertical slices)

1. Obtain sandbox/test credentials and current API docs for Hunar and Apollo (blocker until
   available — record in the handoff).
2. Isolated auth spike for each vendor; confirm authentication.
3. Hunar: agent create/update + runtime/custom variables contract.
4. Hunar: single outbound call to a test number → observe statuses → webhook → result
   retrieval → structured result schema. Capture real payloads.
5. Hunar: bulk call, native retry, language, recording behavior — verify or mark unsupported.
6. Apollo: search + returned fields + contact availability + limits.
7. Update the capability matrix; write ADRs; revise `docs/domain.md` status mapping and
   `docs/interfaces.md` adapter methods if reality differs.

## Verification findings (2026-09-06)

Evidence: `[docs]` https://api.voice.hunar.ai/docs/external/ · `[openapi]`
…/openapi.json · `[live]` read-only `GET /agents/` (200, count 171) and `GET /numbers/`
(200, count 0). No calls placed. Full table in `docs/vendor-capability-matrix.md`.

- **VERIFIED:** auth (`X-API-Key`), agent create/update, runtime context (`custom_data`),
  single + bulk calls, webhooks (4 events, HMAC-SHA256 `{ts}.{body}`, dedup =
  `event_type:call_id` — verifier unit-checked), call/result retrieval, structured result
  (`result_schema`), native retry, 12 languages (agent-level), native calling guardrails,
  recording URL (consume-only), status enum + normalized mapping (`docs/domain.md`).
- **UNSUPPORTED:** BYO telephony via API.
- **Blocker (live call):** `numbers` count 0 → no `from_phone_number`; a live outbound test
  needs a provisioned number.
- **Decisions produced:** ADR-0001 (multi-provider people search), ADR-0002 (use Hunar
  native guardrails/retry/runtime context; platform coordinates the gaps).
- **Delivered:** `apps/api/app/integrations/hunar/` (client + verified webhook verifier),
  `apps/api/app/integrations/people_search/` (provider-agnostic adapter, Apollo first),
  `.env`/`.env.example`.

## Remaining work

- Verify Apollo (or the chosen people-search provider) contract before Phase 4, then wire the
  provider `search()` HTTP call and flip its matrix rows.
- Optional live smoke: create a DRAFT agent + place one call to a **test** number once a
  number is provisioned (requires user go-ahead; the live key expires ~3 days after
  2026-09-04).

## Evidence (Definition of Done)

Captured above and in the capability matrix. Remaining `UNKNOWN` items (all people-search
providers) are listed explicitly there.

## Remaining limitations / open questions

- Sandbox may not expose every production capability; note any capability that can only be
  confirmed in production.
- Whether Hunar exposes recording configuration and BYO telephony is expected to remain
  gated until documented.
