# F-005: App Scaffold (FastAPI + Next.js)

- **Status:** Done — FastAPI wired to Phase 2–3 services (41 tests incl. HTTP e2e); Next.js
  builds and typechecks
- **Risk tier:** Standard
- **Documentation-impact level:** 2
- **Affected areas:** `apps/api/app/{main.py,config.py,api/,db/session.py}`, `apps/web/`
- **Depends on:** F-002/F-003/F-004

## Problem / intent

Expose the service layer over HTTP and give recruiters a UI, so the platform is demoable and
matches the assignment's deliverable shape (deployed app + repo).

## Scope

**In scope**

- FastAPI app: config, engine/session dependency, principal (dev-stub header auth), error
  handlers (`{error:{code,message,request_id}}`), CORS, routers for jobs / candidates /
  interviews / webhooks / system, plus `/dev/bootstrap` and `/health`.
- Next.js App Router console: dashboard (connect, list jobs) + guided job-creation flow
  (create → confirm JD → draft → approve → activate) + typed API client.

**Out of scope**

- Real auth (session/token) — currently `X-Org-Id`/`X-User-Id` dev headers.
- shadcn/ui styling; candidate import/timeline screens (endpoints exist); Celery wiring;
  live Hunar call; deployment.

## Acceptance criteria

- [x] `POST /dev/bootstrap` → ids; unauthorized without headers returns 401 in the error shape.
- [x] Full job flow over HTTP (create → version → confirm → draft → stages → approve →
      activate) with the activation gate returning 409 until satisfied.
- [x] Candidate import + launch + timeline over HTTP; webhook endpoint idempotent
      (`duplicate:true` on re-delivery).
- [x] Next.js `npm run build` + `npm run typecheck` pass.

## Evidence

`apps/api/tests/test_api.py` (TestClient e2e) — full suite **41 passed**. Web:
`✓ Compiled successfully`, 3 routes prerendered; typecheck clean (2026-09-06).

## Remaining limitations / open questions

- Dev-stub auth only; shadcn/ui not wired yet; no candidate/timeline UI yet (backend ready).
- Webhook runs processing inline (would be a Celery enqueue in production).
