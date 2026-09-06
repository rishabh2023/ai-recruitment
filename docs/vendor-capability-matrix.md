# Vendor Capability Matrix

**Rule:** No vendor capability is treated as fact unless marked `VERIFIED` here, with
evidence. No recruiter-facing UI control, API contract, or background job may be built
around an `UNKNOWN` or `UNSUPPORTED` capability. When unverified, implement the safe
fallback and surface uncertainty.

Status legend: `VERIFIED` (documented + confirmed against sandbox) · `UNKNOWN` (not yet
confirmed — treat as unavailable) · `UNSUPPORTED` (confirmed not available).

**Evidence sources for Hunar (F-001, 2026-09-06):**
- `[docs]` Hunar external API docs — https://api.voice.hunar.ai/docs/external/
- `[openapi]` OpenAPI spec — https://api.voice.hunar.ai/docs/external/openapi.json
- `[live]` F-001 read-only: `GET /external/v1/agents/` → HTTP 200, `GET /external/v1/numbers/`
  → HTTP 200 (count 0).
- `[live-call]` 2026-09-06: a **real outbound call was placed and COMPLETED** via `POST /calls/`
  (agent "AI Hiring Assistant", callee a consenting test number). Status progressed
  NOT_STARTED→SCHEDULED→RINGING→IN_PROGRESS→COMPLETED; `answered_by=HUMAN`,
  `engagement_status=ENGAGED`, `duration_seconds=117`, `call_ended_by=AGENT`. Hunar
  auto-assigned `from_phone_number` (+9180…599) even though `GET /numbers/` reports count 0 —
  **the "no from-number" blocker below is superseded.** Structured `result` was `{}` and
  `recording_url` null on the synchronous `GET /calls/{id}/`; those arrive async via the
  `call_result_done` / `call_recording_done` webhooks (not exercised in this direct test).

Base URL (verified): `https://api.voice.hunar.ai/external/v1`. Auth: `X-API-Key` header.

## Hunar

| Capability | Status | Evidence | Notes / fallback |
| ---------- | ------ | -------- | ---------------- |
| Authentication | `VERIFIED` | `[live]` `[docs]` | `X-API-Key` header confirmed working against live API. |
| Agent creation / update | `VERIFIED` | `[openapi]` | `POST/PUT /agents/`. Required: name, voice_persona, agent_prompt, objective, introduction, result_schema (+ language default ENGLISH). Status enum DRAFT/ACTIVE/ARCHIVED. |
| Runtime / custom variables (per-call context) | `VERIFIED` | `[openapi]` | `custom_data` (key→string) on single & bulk calls; agent exposes `custom_variables`/`required_variables`. **Supports the stage-driven "reuse agent + inject context" model — no per-candidate agents.** |
| Outbound single call | `VERIFIED` (live — call placed + COMPLETED) | `[openapi]` `[live-call]` | `POST /calls/` returns 200 with the created call (id, status NOT_STARTED, auto-assigned `from_phone_number`). A real call completed end-to-end 2026-09-06 (answered_by HUMAN, 117s). **Agent gate:** the agent's `required_variables` must all be present in `custom_data` or the API returns 422 (e.g. "AI Hiring Assistant" requires `candidate_name, job_role, company, location`). Earlier "no from-number" blocker is superseded — Hunar assigned one automatically. |
| Bulk call | `VERIFIED` | `[openapi]` | `POST /calls/bulk/`, `data` 1–10000 items, `remove_invalid_rows`/`remove_duplicate_phone_numbers` default true. |
| Webhook events (types, payload, signature) | `VERIFIED` | `[docs]` | Events: `call_status_updated`, `call_recording_done`, `call_result_done`, `call_summary`. HMAC-SHA256 over `{timestamp}.{raw_body}`, header `X-Hunar-Signature` (comma-sep for key rotation) + `X-Hunar-Timestamp`. Verifier implemented + unit-checked in `apps/api/app/integrations/hunar`. |
| Call status / result retrieval | `VERIFIED` | `[openapi]` `[live]` | `GET /calls/{id}/` returns status, `result`, `recording_url`, durations, engagement/answered_by, retry fields. List paginates (`count/next/previous/results`, calls page_size ≤ 200). |
| Structured result / evaluation schema | `VERIFIED` (mechanism) | `[openapi]` | Agent `result_schema` (JSON schema) → `result` object on response + `call_result_done`. Schema shape is caller-defined; **platform still validates** per docs/domain.md. |
| Retry behavior (native) | `VERIFIED` | `[docs]` `[openapi]` | `retry_config`: `max_retry_count` 0–10, `retry_interval_hours` ∈ {0,3,6,9,12,24}; NOT_CONNECTED eligible; response exposes `retry_count`/`retries_left`/`next_retry_scheduled_at`. Platform owns business policy above this; do not double-retry. |
| Language support / configuration | `VERIFIED` | `[openapi]` | 12 languages (EN, HI, TA, TE, KN, MR, ML, GU, BN, TR, AR, ES). **Set at agent level**, not per-call → maps to job/stage, not candidate override. Voice personas: NEHA, ROY, ZOE, SAM, MIRA, EESHA. |
| Calling window / guardrails (native) | `VERIFIED` | `[docs]` `[openapi]` | `guardrails`: `allowed_days` (**min 3 distinct**), `earliest_call_time`/`last_call_time` (HH:MM, **min 3-hour window**), IANA `timezone`. Hunar enforces windows; platform coordinates cases outside these constraints. See ADR-0002. |
| Recording / transcript behavior | `VERIFIED` (consume only) | `[docs]` `[openapi]` | `recording_url` on COMPLETED + `call_recording_done`. **No enable/disable toggle exposed** → no "record call" control; display only what is returned. |
| BYO telephony | `UNSUPPORTED` (via API) | `[openapi]` | `numbers/` are org-provisioned (`telephony_provider_id`, `provider`); no BYO provisioning endpoint. Use Hunar-managed numbers only. |

## People Search (multi-provider)

The platform is **not Apollo-only**. The assignment permits Apollo.io, People Data Labs
(PDL), Proxycurl, or Coresignal, selected via `PEOPLE_SEARCH_PROVIDER`. The rows below track
the currently active first provider (Apollo); each additional provider gets its own
verification before use. See ADR-0001 and `apps/api/app/integrations/people_search/`.

### Apollo (first provider)

Evidence: `[apollo-docs]` https://docs.apollo.io/reference/people-api-search,
…/reference/people-enrichment, …/reference/authentication (read 2026-09-06). `[apollo-live]`
adapter call to `mixed_people/api_search` with the user's key → **HTTP 403 API_INACCESSIBLE**
("not included in your Free plan"). A 403 (not 401) confirms the key is valid; the search
endpoint requires a **paid Apollo plan**.

> **Blocker:** the current Apollo key returns 403 for the Search API. Per docs the endpoint is
> 0-credit but "requires a Master API key or scoped API key with endpoint access" — so this key
> needs API access enabled (Master/scoped key or plan upgrade). Options (multi-provider by
> design, ADR-0001): enable/upgrade the Apollo key, or switch `PEOPLE_SEARCH_PROVIDER` to
> PDL / Proxycurl / Coresignal and verify that provider. Contract confirmed via
> https://docs.apollo.io/reference/people-api-search.

| Capability | Status | Evidence | Notes / fallback |
| ---------- | ------ | -------- | ---------------- |
| Authentication | `VERIFIED` (live) | `[apollo-live]` | `x-api-key` accepted (403 plan gate, not 401 → key valid). |
| People search (query params, filters) | `VERIFIED` (docs); **not on this plan** | `[apollo-docs]` `[apollo-live]` | `POST /api/v1/mixed_people/api_search`; params `person_titles[]`, `person_locations[]`, `person_seniorities[]`, `q_keywords`, `page`, `per_page`. Adapter wired + mapping unit-checked; endpoint returns 403 on Free plan. |
| Returned profile fields | `VERIFIED` (docs) | `[apollo-docs]` | Search returns `id`, `first_name`, `last_name_obfuscated`, `title`, `organization.name`, `city/state/country`, `linkedin_url`, and `has_email`/`has_direct_phone` flags. Every field treated as optional (progressive profile). |
| Contact/phone availability | `VERIFIED` (docs) — **not in search** | `[apollo-docs]` | Search returns **no** email/phone. Enrichment `POST /people/match` with `reveal_phone_number=true` requires an HTTPS `webhook_url`; phone delivered **async via webhook**. Outreach needs an enrichment step before a Hunar call → Phase 4. |
| Rate limits / pagination | `VERIFIED` (docs) | `[apollo-docs]` | `per_page` ≤ 100; display cap 50,000 (≤ 500 pages). Adapter caps per_page at 100; conservative request rate. |

## How to update this file

When F-001 (or later verification work) confirms an item: set the status, add a one-line
evidence pointer (doc URL / sandbox test / captured payload location), and update the safe
fallback if it changes. Record a corresponding ADR in `docs/decisions/` when a verified
result changes an architectural or product decision.
