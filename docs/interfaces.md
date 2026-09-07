# Interfaces

Conventions for the platform API, authentication/authorization, errors, vendor adapter
boundaries, webhooks, and background jobs.

## Platform API conventions

- REST over JSON. Resource-oriented paths, organization-scoped by the authenticated
  principal (org id is never taken from the client body for authorization).
- **Realized endpoints** (the app serves these today):

  ```
  # system
  GET  /health
  # auth / session
  POST /auth/signup   POST /auth/login   POST /auth/logout   GET /auth/me
  GET  /auth/invite?token=            POST /auth/accept-invite            POST /dev/bootstrap
  # dashboard
  GET  /dashboard/summary             GET  /dashboard/activity
  GET  /dashboard/audit               (org audit trail; paginated + search: ?page=&page_size=&q=
                                       -> {items,total,page,page_size}; q matches action/entity/
                                       state/reason/actor-email)
  # assistant (conversational copilot — Claude tool-use over org-scoped ops)
  POST /assistant/chat                ({messages, approve?} -> {reply, links, pending?})
    # tools: dashboard_summary, list_jobs, list_candidates, list_funnels, get_job,
    #        create_job, add_job_description, confirm_job_description, draft_workflow
    # human-in-the-loop: confirm_job_description + draft_workflow return a `pending` action;
    #   the client re-POSTs with approve:{tool,args} to run it deterministically.
    #   approve/activate/delete/launch/decisions are NOT exposed to the model.
  # jobs + workflow
  POST /jobs   GET /jobs   GET /jobs/{id}
  POST /jobs/{id}/versions            POST /jobs/{id}/versions/upload (PDF)
  POST /jobs/{id}/versions/tidy       (reflow messy JD text -> {text}; deterministic, no LLM)
  POST /jobs/{id}/versions/{vid}/confirm
  GET  /jobs/{id}/version             (latest JD version: raw jd_text + extracted + confirmed; null when none)
  GET  /jobs/{id}/funnel              (cumulative-reached hiring funnel: per-stage reached/current + top-line totals)
  POST /jobs/{id}/workflow/draft      GET  /jobs/{id}/workflow
  GET  /jobs/{id}/workflow/versions/{vid}/stages   (list stages)
  PUT  /jobs/{id}/workflow/versions/{vid}/stages   (edit stages + criteria)
  POST /jobs/{id}/workflow/versions/{vid}/approve
  POST /jobs/{id}/activate            POST /jobs/{id}/archive    DELETE /jobs/{id}
  GET/PUT /jobs/{id}/calling-policy
  # funnels (org-owned reusable workflow templates; writes admin-only)
  GET  /funnels   POST /funnels   GET /funnels/{id}
  GET  /funnels/presets              (built-in starter funnels; read-only, code-defined)
  PUT  /funnels/{id}/stages           (edit → new template version)
  PATCH /funnels/{id} (rename)        POST /funnels/{id}/archive
  POST /funnels/{id}/use              ({job_id} → adopt into a job as an unapproved workflow)
  # candidates + pipeline
  POST /jobs/{id}/candidates          GET  /jobs/{id}/candidates
    # POST rejects a duplicate within the role (same phone or email, 409); phone stored E.164.
  POST /jobs/{id}/candidates/import-csv  (bulk add; multipart CSV. name + mobile mandatory;
                                       optional country_code/email/location; per-row errors,
                                       de-dupes by phone -> {added,skipped,errors[]})
  GET  /jobs/{id}/pipeline            (paginated + filterable board slice:
                                       ?stage=<uuid|new|all>&state=&q=&page=&page_size=
                                       -> {items,total,page,page_size})
  PATCH /job-candidates/{id}          (edit profile: full_name/phone/email/location; partial)
  DELETE /job-candidates/{id}
  GET  /candidates                    (org-wide directory: all participations across jobs)
  GET  /job-candidates/{id}/timeline  POST /job-candidates/{id}/decision
  POST /job-candidates/{id}/launch    POST /job-candidates/{id}/enrich    POST /calls/{id}/sync
  # sourcing (people search & outreach — Flow B)
  GET  /jobs/{id}/sourcing/providers  GET  /jobs/{id}/sourcing/suggested-query
  POST /jobs/{id}/sourcing/search     POST /jobs/{id}/sourcing/add
  # settings (admin) + team invites
  GET/PUT /settings                   POST /settings/invites   DELETE /settings/invites/{id}
  # webhooks
  POST /webhooks/hunar
  ```

  This is the complete set of routes the app serves today (verified against
  `apps/api/app/api/routers/`). Detail on request/response shapes lives in
  `apps/api/app/api/schemas.py`.

- Consequential bulk actions (outreach/interview launch) require an explicit pre-launch
  review payload (candidate count, starting stage, calling window, retry policy, language)
  before work is enqueued.
- Write endpoints that trigger external work return quickly after validating and persisting
  intent; the actual work is a background job.
- `POST /jobs/{id}/archive` makes a role inactive without deleting it. `POST /jobs/{id}/activate`
  reactivates an archived role only if its JD is confirmed and workflow approved. Inactive roles
  reject sourcing and new outreach/interview launches with HTTP 409; read-only history remains
  available.

### Calling policy

`GET` and `PUT /jobs/{id}/calling-policy` expose the job-scoped policy used for Hunar
dispatch. The persisted values are allowed days, an IANA timezone, start/end times, maximum
attempts, retry interval, and a preferred future agent language. A saved policy must contain a
complete guardrail; the API rejects missing boundaries/timezone, fewer than three distinct days,
or a window under three hours. Retry intervals are limited to
the verified Hunar set (0, 3, 6, 9, 12, 24 hours), total attempts to 1–10, and language to Hunar's
verified languages. Dispatch maps the window to Hunar `guardrails` and attempts to
`retry_config` (`max_retry_count = max_attempts - 1`). Policy changes are audited. Hunar
language is agent-level, so the preference is not a per-call override and does not update an
existing agent yet.

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

**Live dispatch (realized).** `POST /job-candidates/{id}/launch` persists the call intent, then
enqueues a Celery task (`dispatch_hunar_call`, eager in dev) that runs `HunarDispatchService`:
resolve the agent (stage `HunarAgentConfig`, else `HUNAR_DEFAULT_AGENT_ID`), fill the agent's
`required_variables` into `custom_data`, `POST /calls/`, and record `hunar_call_id` + status on
the Call. Gated by `HUNAR_LIVE_CALLS_ENABLED` (+ key); off by default. Results/recordings arrive
async via the webhook; `POST /calls/{id}/sync` pulls current status on demand (dev, no public
webhook). A terminal not-connected call (no answer / failed / cancelled) fails the run with a
reason instead of leaving it waiting; re-launching a failed run starts a fresh attempt.

Implemented in `apps/api/app/integrations/hunar/` (`HunarClient`, `HunarConfig`,
`verify_webhook_signature`, `webhook_dedup_key`). The adapter centralizes authentication,
timeouts, and retries; isolates request/response shapes; keeps Hunar details out of business
logic. It is single-provider by design — do not turn it into a generic provider framework.

Per-call context is passed via `custom_data` (verified), so the stage-driven model reuses a
job/stage agent and injects candidate/stage context at call time rather than provisioning
per-candidate agents (see ADR-0002).

### Voice-AI (Hunar) health & key

- `GET /hunar/health` — any authenticated user. `{ status, source, checked_at }` where
  `status ∈ {healthy, invalid, unconfigured, unreachable}` and `source ∈ {override, env, null}`.
  Result cached ~60s in Redis; `?refresh=1` forces a live probe (`GET /numbers/`). Never
  returns the key.
- `PUT /hunar/key` — admin only. Body `{ api_key }`. Validates the key against Hunar before
  saving it durably (global `app_config` row); 401/403 → 422 (rejected, not saved), transport
  error → 502 (not saved). On success busts the health cache and audit-logs `hunar.key.updated`
  (never the key value). Resolution order for the effective key: DB override → `.env`.

## People-search adapter boundary (multi-provider)

People search is **provider-agnostic** — **four real providers are implemented**: Apollo.io,
People Data Labs (PDL), Proxycurl, Coresignal. The `PeopleSearchProvider` interface exposes
`search()` and `enrich()` and returns normalized `ExternalCandidate` / `EnrichmentResult`
shapes; providers own their auth, request/response shaping, and pagination, return only fields
the provider actually provides, model missing data as absence (e.g. PDL returns plan-gated
fields as boolean `true` → coerced to absent), and preserve provenance (`source`, `source_id`,
`raw`). Semantic ranking beyond deterministic filters is a platform-LLM concern, kept out of the
adapter. Implemented in `apps/api/app/integrations/people_search/`. See ADR-0001.

**Real data only — no fabrication.** `SourcingService` runs the provider the recruiter selects
(`provider` in the search body), or `provider: "auto"`. Auto is deliberately limited to the
configured PDL provider: it runs the exact query, then makes one transparent
zero-result retry without seniority (or without location if seniority is absent). It never
silently fans out across providers. A provider that is unconfigured, plan-gated, or failing
raises `SourcingProviderError` → **HTTP 502** with
the real reason (e.g. "Apollo.io search failed: requires a paid plan (HTTP 403)"). A `sample`
provider exists only for tests/local dev and is never used automatically. `GET
/jobs/{id}/sourcing/providers` reports which providers are configured (has a key) + the default.

**Provider keys resolve org-first.** Keys come from org Settings (`org_settings.provider_keys`)
overlaid on process `.env`, so a key saved in Settings takes effect immediately for search,
enrichment, and the providers list — no redeploy. Search returns no contact details;
`POST /job-candidates/{id}/enrich` reveals phone/email via the candidate's source provider
(honest 502 when the provider/plan can't), moving `SOURCED → OUTREACH_PENDING`. Outreach then
reuses the interview launch path (`SOURCED`/`OUTREACH_PENDING → CONTACTED`).

## Settings & team invites

`GET /settings` (any user) returns org name, people-search providers (+ `configured` flags,
never raw keys), default provider, live-calling flag, the team, and pending invites. `PUT
/settings` (**admin only** → 403 otherwise) sets the default provider, toggles live outbound
calling (gates real Hunar dialing), and sets provider API keys (write-only). **Invites:** `POST
/settings/invites` (admin) creates an invite for an email + role and returns a **one-time accept
link** (token shown once, stored only as a SHA-256 hash); `DELETE /settings/invites/{id}`
revokes. The invitee uses `GET /auth/invite?token=` to preview and `POST /auth/accept-invite`
(public) to set a password, which creates their user and signs them in. No email is sent — the
admin shares the link. Backed by `org_settings` + `user_invites` tables.

## MCP server (`apps/mcp`)

A Model Context Protocol server exposes the platform as **31 tools** (thin wrappers over these
same HTTP endpoints, so all gates/auth/audit still apply) for conversational use from Claude
Code / ChatGPT. It signs in once (`RECRUIT_EMAIL`/`RECRUIT_PASSWORD`), reuses the session
cookie, and re-authenticates on 401. Transports: **stdio** (Claude Code; registered via root
`.mcp.json`) and **streamable-http** (`MCP_TRANSPORT=streamable-http`, endpoint `/mcp`; ChatGPT
connectors — needs a public tunnel). Includes one-shot journey macros `source_and_outreach`
(Flow B) and `import_and_interview` (Flow A). See `apps/mcp/README.md`.

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
`POST /jobs/{id}/versions/upload` (multipart PDF). Both create an unconfirmed `JobVersion`.

PDF upload path: text is extracted server-side via `pypdf` and **reflowed** (`tidy_jd_text`) so
ragged/one-word-per-line extraction becomes readable prose (bullets and headings preserved) —
this is deterministic, no LLM. If a PDF yields no text (scanned/image-only), it falls back to
the provider's **native PDF reading** (`read_pdf_text`, Claude vision) bounded by size (2 MB) and
pages (4); if that also yields nothing the recruiter is asked to paste. `POST /jobs/{id}/versions/tidy`
exposes the same reflow so a recruiter can clean pasted/edited JD text in place before saving.

**Candidate phone + de-duplication.** Phones are stored E.164 (`+<country><national>`); the add
UI takes a required country-code selector, CSV accepts a `country_code` column (or a `+`-prefixed
number). Adding a candidate whose phone or email already exists **within the same role** is
rejected (409) — de-duplication is per-job (the same person may appear once per role), and the
match is country-code tolerant (a bare national number matches its E.164 form by suffix).

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
