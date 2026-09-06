# Integrations

Thin vendor adapters. Business logic never calls a vendor directly.

## `hunar/` — voice execution (single provider)

Hunar is the **only** voice/conversation provider — no multi-provider abstraction here by
design. `HunarClient` isolates request/response shapes and centralizes `X-API-Key` auth and
the base URL. `verify_webhook_signature` and `webhook_dedup_key` implement the **verified**
webhook contract (HMAC-SHA256 over `{timestamp}.{raw_body}`, `X-Hunar-Signature`; idempotency
key = `event_type:call_id`). Verified base: `https://api.voice.hunar.ai/external/v1`. See
`docs/vendor-capability-matrix.md`.

## `people_search/` — sourcing (multi-provider, basic)

People search is intentionally **provider-agnostic**: the assignment permits Apollo.io,
People Data Labs (PDL), Proxycurl, or Coresignal. `PeopleSearchProvider` is the interface;
`get_people_search_provider()` selects the active one from `PEOPLE_SEARCH_PROVIDER` and its
API key. Apollo is the first implementation; PDL/Proxycurl/Coresignal are registered keys
that raise a clear "not implemented" error until added — no caller changes needed to plug one
in. Providers normalize results to `ExternalCandidate` (missing fields modeled as absence,
provenance preserved in `source`/`source_id`/`raw`).

> Apollo's exact request/response contract is still `UNKNOWN` (see the matrix). The Apollo
> HTTP call is deliberately not wired until verified — the mapping helpers show the intended
> shape without depending on an unverified contract.
