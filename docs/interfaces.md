# Interfaces

Conventions for the platform API, authentication/authorization, errors, vendor adapter
boundaries, webhooks, and background jobs.

## Platform API conventions

- REST over JSON. Resource-oriented paths, organization-scoped by the authenticated
  principal (org id is never taken from the client body for authorization).
- Illustrative endpoints (final contracts locked after Hunar mapping is `VERIFIED`):

  ```
  POST   /jobs                              GET    /jobs        GET/PATCH /jobs/{id}
  POST   /jobs/{id}/extract                 POST   /jobs/{id}/workflow/resolve
  POST   /jobs/{id}/workflow/generate       PUT    /jobs/{id}/workflow
  POST   /jobs/{id}/rubric/generate         PUT    /jobs/{id}/rubric
  POST   /jobs/{id}/approve
  POST   /jobs/{id}/candidates              POST   /jobs/{id}/candidates/import
  POST   /jobs/{id}/people-search           POST   /jobs/{id}/outreach
  POST   /jobs/{id}/interviews
  GET    /candidates/{id}                   GET    /candidates/{id}/timeline
  POST   /webhooks/hunar
  ```

- Consequential bulk actions (outreach/interview launch) require an explicit pre-launch
  review payload (candidate count, starting stage, calling window, retry policy, language)
  before work is enqueued.
- Write endpoints that trigger external work return quickly after validating and persisting
  intent; the actual work is a background job.

## Authentication and authorization

- Session/token-based auth; the principal carries organization id and role. **Realized:**
  server-side sessions via an HttpOnly, SameSite=Lax cookie. `POST /auth/signup` (name, email,
  password, optional org_name) creates a new organization + its first admin user and logs them
  in; email must be globally unique (409 otherwise). `POST /auth/login` (email + password)
  validates credentials and sets the cookie; `POST /auth/logout` revokes the session
  server-side and clears the cookie; `GET /auth/me` returns the current principal (org, role,
  name, email). `POST /dev/bootstrap` remains a dev convenience. Passwords are
  stored as PBKDF2-HMAC-SHA256 hashes (stdlib, no external dependency); only a SHA-256 hash of
  each session token is persisted (`user_sessions`), so a DB leak cannot be replayed. Sessions
  live in Postgres (durable, explicitly revocable), not Redis. Cookies must be `Secure` in
  production (`SESSION_COOKIE_SECURE=1`); left off for plain-HTTP localhost.
- **Role-based capabilities**, not enterprise RBAC (see `docs/domain.md` for the matrix).
- Every request is authorized against the resource's organization. Candidate data access is
  always authorization-checked. Cross-organization access is impossible by construction.
- Secrets (Hunar/Apollo/LLM/DB/Redis keys) are server-side only, never exposed to the client
  or via `NEXT_PUBLIC_*`.

## Error-response conventions

- Consistent shape: `{ "error": { "code", "message", "details?", "request_id" } }`.
- Stable machine-readable `code`; human `message`; `request_id` correlates to traces/logs.
- Distinguish validation errors (4xx), authorization failures (403/404 as appropriate),
  external-dependency failures (surfaced with retryability), and unexpected errors (5xx,
  reported to Sentry).
- External API failures are represented as domain outcomes with a next action, not opaque
  500s, wherever the failure is expected (Hunar/Apollo timeout, provisioning failure).

## Hunar adapter boundary

Thin, vendor-specific client. Business services never make raw Hunar HTTP calls. The surface
below is **VERIFIED** (F-001) against the external API — base URL
`https://api.voice.hunar.ai/external/v1`, auth `X-API-Key`:

```
GET/POST /agents/    GET/PUT /agents/{id}/
GET/POST /calls/     POST /calls/bulk/     GET /calls/{id}/
GET /numbers/
```

Implemented in `apps/api/app/integrations/hunar/` (`HunarClient`, `HunarConfig`,
`verify_webhook_signature`, `webhook_dedup_key`). The adapter centralizes authentication,
timeouts, and retries; isolates request/response shapes; keeps Hunar details out of business
logic. It is single-provider by design — do not turn it into a generic provider framework.

Per-call context is passed via `custom_data` (verified), so the stage-driven model reuses a
job/stage agent and injects candidate/stage context at call time rather than provisioning
per-candidate agents (see ADR-0002).

## People-search adapter boundary (multi-provider)

People search is **provider-agnostic** (Apollo.io / PDL / Proxycurl / Coresignal), selected
via `PEOPLE_SEARCH_PROVIDER`. The `PeopleSearchProvider` interface returns a normalized
`ExternalCandidate` shape; providers own their own auth, request/response shaping, and
pagination, return only fields the provider actually provides, model missing data as absence,
and preserve provenance (`source`, `source_id`, `raw`). Selected via
`get_people_search_provider()`. Semantic ranking beyond deterministic filters is a
platform-LLM concern, kept out of the adapter. Implemented in
`apps/api/app/integrations/people_search/`. See ADR-0001.

## LLM adapter boundary

Platform-side product intelligence only: JD understanding, role classification, structured
skill extraction, draft workflow/rubric generation. Never candidate conversation, never
duplicating Hunar evaluation. Implemented in `apps/api/app/integrations/llm/` behind an
`LLMProvider` protocol returning **drafts** (`ExtractedJob`, `DraftStage`). The real provider
is **Claude** (`AnthropicLLMProvider`, model `claude-haiku-4-5`), used for JD extraction when
`PLATFORM_LLM_API_KEY` (an Anthropic key) is set; otherwise a deterministic offline stub runs
so the flow works and tests stay stable. Any API/parse error falls back to the stub — JD entry
never breaks on a transient LLM failure. All outputs require human review/approval before they
execute (enforced by `WorkflowService`/`JobService` gates).

JD can be provided two ways: `POST /jobs/{id}/versions` (pasted `jd_text`) or
`POST /jobs/{id}/versions/upload` (multipart PDF — text extracted server-side via `pypdf`, then
the same extraction path). Both create an unconfirmed `JobVersion`.

## Webhook validation and idempotency

- Dedicated endpoint `POST /webhooks/hunar`. The HTTP handler is lightweight: authenticate/
  validate the event if supported, persist raw event metadata, run an idempotency check,
  enqueue processing, return quickly.
- Idempotency: persist a vendor event ID when available, otherwise derive a stable dedup key
  from documented identifiers. Assume delivery can be duplicated.
- A worker normalizes the payload → resolves the call → updates attempt → updates call
  lifecycle → stores structured result → updates candidate facts → updates pipeline/stage →
  emits audit event. A duplicate never double-advances anything.

## Background-job contract

- Celery owns durable async execution: `provision_job_agent`, `launch_outreach_call`,
  `launch_interview_call`, `process_hunar_webhook`, `sync_call_status`,
  `generate_draft_rubric` (and workflow drafting).
- Jobs are idempotent where they touch external systems or advance state. Infrastructure
  retries use backoff and do not consume candidate-contact attempts unless a call was
  actually initiated per verified vendor behavior.
- Do not create a worker for work that safely completes inside a short request.

## Vendor-capability rule (applies everywhere)

**No vendor capability may be treated as fact unless marked `VERIFIED` in
`docs/vendor-capability-matrix.md`.** No recruiter-facing UI control, API contract, or
background job may depend on an `UNKNOWN` or `UNSUPPORTED` capability. When a capability is
unverified, implement the documented safe fallback and surface uncertainty.
