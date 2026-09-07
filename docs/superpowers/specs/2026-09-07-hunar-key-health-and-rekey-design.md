# Hunar Key Health Check & Re-Key Flow — Design

**Date:** 2026-09-07
**Status:** Approved for planning
**Feature area:** Hunar voice-AI integration (see `docs/vendor-capability-matrix.md`,
`docs/features/F-001-hunar-contract-verification.md`)

## Problem

The Hunar API key is a server-side env var (`hunar_api_key`, `apps/api/app/config.py`). There
is no way to tell from the app whether that key is currently valid or expired, and no way to
recover in-app when it expires — an expired key surfaces only as a failed call deep in a stage.

Recruiters and admins should be able to see, on any screen after login, whether the voice-AI
integration is healthy, and an admin should be able to paste a new live key to restore service
without a redeploy.

## Goals

- A **global** Hunar health signal, visible on every authenticated screen.
- Detect an expired/invalid key (HTTP 401/403) distinctly from a transient network failure.
- Let an admin paste a **new live key** that takes effect immediately (no redeploy), validated
  against Hunar **before** it is accepted.
- `.env` remains a fallback default. The pasted key is stored **durably in the DB** (a global
  config row) so it survives a Redis flush/restart; only the health result is cached in Redis.

## Non-goals

- Not per-organization. One Hunar account → one global key. (Consistent with the current
  single env var.)
- Not changing the live-calls safety switch (`hunar_live_calls_enabled`); a valid key can exist
  while calling is paused. The two are independent.
- No automatic key rotation or secret-manager integration.

## Key resolution (the core change)

Resolution order becomes: **DB override → `.env` key**.

- `HunarClient.from_settings(...)` is supplemented by a resolver that first reads the DB
  override, falling back to `settings.hunar_api_key`.
- The override is a single global config row (see below). It is durable — it survives Redis
  flushes and app restarts. Only the health *result* is cached in Redis.
- If no override is set, resolution falls back to the `.env` key.

## Backend

### DB — global config row (durable key override)

Everything today is per-org; the Hunar key is global. Add a small **global** single-row config
store rather than overloading `OrgSettings`:

- New table `app_config` (module placement decided in plan; likely a new tiny `app/modules/
  platform/` or under `organizations`) — a key/value row store, e.g. columns
  `(key text primary key, value text, updated_at, updated_by)`. First use: row
  `hunar_api_key`. The value column holds the secret; it is **never** returned to clients.
- A migration adds the table (follow the per-module migration convention in `apps/api`).
- Rationale for key/value over a dedicated column: future global settings reuse the same table
  without another migration; keep it minimal (one known key for now).

### Redis helper (health cache only)

The API app has no shared Redis client yet (only `redis_url` in config + Celery broker use).
Add a tiny module `app/redis_client.py` exposing a lazily-created `redis.Redis` from
`settings.redis_url`, plus typed get/set/delete helpers for the health cache key. All Redis
access is wrapped so a Redis outage degrades gracefully (treat the health cache as a miss —
recompute live) — never 500 because Redis is down. The key override does **not** depend on
Redis; it lives in the DB.

### Hunar key store + health service

New module `app/integrations/hunar/keystore.py` (or `app/modules/... ` — placement decided in
plan) providing:

- `resolve_api_key(session) -> tuple[str, source]` where `source ∈ {"override", "env", None}`.
- `set_override(session, key: str) -> None` / `clear_override(session) -> None` — write/delete
  the `hunar_api_key` row in `app_config`.
- `check_health(*, refresh: bool=False) -> HunarHealth` — returns a cached result unless
  `refresh`. Health is computed by calling the lightweight verified read `GET /numbers/` via
  `HunarClient.list_numbers()`:
  - success (2xx) → `healthy`
  - `HunarError` with status 401/403 → `invalid` (expired/wrong key → re-key needed)
  - no key configured at all → `unconfigured`
  - `HunarError` from transport/timeout or other 5xx → `unreachable` (transient; do **not**
    demand a re-key)
- Cache: Redis key `hunar:health` holding `{status, source, checked_at}`, TTL ~60s. `refresh=1`
  bypasses and rewrites it.

`HunarHealth` shape: `{ status, source, checked_at }` where
`status ∈ {healthy, invalid, unconfigured, unreachable}`.

### Endpoints (new router `app/api/routers/hunar.py`, prefix `/hunar`)

- `GET /hunar/health` — any authenticated user. Returns the cached `HunarHealth`
  (query `?refresh=1` forces a live check). Never returns the key. Adds an OpenTelemetry span +
  Sentry reporting for the outbound Hunar call (per backend rules).
- `PUT /hunar/key` — **admin only** (`role == "admin"`, mirror `_require_admin` in
  `settings.py`). Body `{ api_key: str }`. Flow:
  1. Reject empty/whitespace with `validation_error` (422).
  2. Validate the candidate key with a live `GET /numbers/` using a throwaway `HunarClient`
     built from the candidate key.
  3. On success → store override in the DB (`app_config.hunar_api_key`), bust `hunar:health`,
     write an audit event
     (`hunar.key.updated`, actor + source, **never the key value**), return the fresh
     `HunarHealth` (`healthy`, source `override`).
  4. On 401/403 → `validation_error` (422) "That key was rejected by the voice-AI provider."
  5. On unreachable → `502`/`bad_gateway` "Couldn't reach the voice-AI provider to verify the
     key; try again." — override is **not** saved.
- (Optional, plan-time) `DELETE /hunar/key` admin-only to clear the override and fall back to
  `.env`. Include if cheap; otherwise defer.

### Schemas

Add to `app/api/schemas.py`: `HunarHealthOut { status, source, checked_at }` and
`HunarKeyUpdateIn { api_key }`.

## Frontend

### API client (`apps/web/lib/api.ts`)

- `getHunarHealth(refresh?: boolean): Promise<HunarHealth>`
- `updateHunarKey(apiKey: string): Promise<HunarHealth>`

### Global health badge (app shell)

A small badge in the sidebar footer (near the signed-in user), visible on every authenticated
screen — added in the shared shell so it is not per-page. States:

- `healthy` → green "Voice AI connected"
- checking / loading → amber "Checking voice AI…"
- `invalid` → red "Voice AI key expired"
- `unconfigured` → red "Voice AI not configured"
- `unreachable` → grey "Voice AI unreachable — retrying"

Polling: fetch on mount + a light interval (e.g. every 60s) so an expiry is noticed without a
page reload. Product language only — never "Hunar", agent IDs, or telephony.

### Re-key modal (admin only)

When status is `invalid` / `unconfigured` and the user is an **admin**, the badge exposes an
"Update key" action opening a modal:

- Single password field "Paste new live key from the voice-AI provider".
- Submit → `updateHunarKey(...)`. On success the modal closes and the badge flips to green.
- On rejection (422) show the server message inline; key not saved.
- The key is saved durably; no "temporary" caveat needed.

Non-admins see the status only, with helper text "Ask an admin to update the voice-AI key."
Admin-ness comes from the existing settings signal (`is_admin`) — reuse it (e.g. fetch
`GET /settings` or expose `is_admin` where the shell can read it).

### States covered

loading, healthy, invalid (admin can fix / non-admin informed), unconfigured, unreachable
(transient, no forced re-key), permission-denied (non-admin cannot open modal / server rejects
`PUT`), desktop + mobile, basic a11y (badge has an accessible label; modal is focus-trapped).

## Testing

- **Backend (mock Hunar `GET /numbers/`, never dial):**
  - health = `healthy` on 2xx; `invalid` on 401/403; `unreachable` on transport error;
    `unconfigured` when no key set.
  - resolution prefers DB override over env; falls back to env when override absent.
  - the DB override persists across a simulated Redis flush (health cache cleared, override
    still resolves from DB).
  - health result is cached; `refresh=1` forces a re-check.
  - `PUT /hunar/key`: admin validates-then-saves to DB; rejects invalid key without saving;
    rejects empty; forbidden for non-admin; busts the cache on success; audit event written
    without the key value.
  - Redis-down: health degrades to a miss (recomputed live), no 500; override still resolves.
- **Frontend:** badge renders each status; admin sees "Update key", non-admin does not; modal
  success flips to green; modal error shows inline.

## Docs impact

- `docs/vendor-capability-matrix.md` — note the `/numbers/` read is used as the health probe.
- `docs/interfaces.md` — document `GET /hunar/health` and `PUT /hunar/key`.
- `docs/features/` — add/extend a Hunar feature brief; update
  `docs/work/active-feature.md` handoff.
- `.env.example` — no new var (override is a durable DB row), but note the health/re-key
  behavior.

## Open questions (resolved)

- Storage: **key override in DB (durable, global) + health cache in Redis** (user decision;
  `.env` stays the fallback).
- Scope: **global** (user decision).
- Check method: **lightweight `GET /numbers/`** (user decision).
