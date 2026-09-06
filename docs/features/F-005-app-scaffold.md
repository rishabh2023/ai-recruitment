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
- Job hub calling-policy UI and its authenticated API: recruiters can set the verified Hunar
  calling window, retry policy, and agent-language preference; dispatch uses the supported
  guardrails/retry fields.
- Create-job workflow UI refresh: the existing create → extract → confirm → draft → edit →
  approve → activate flow is presented as a responsive four-step wizard with purpose-built
  workflow-stage cards. The state transitions and API contract are unchanged.
- Job workspace refresh: `/jobs/{id}` groups overview, workflow, pipeline, and calling-policy
  work into tabs. Draft workflows can be reopened, edited, saved, and approved in place;
  approved versions stay read-only and jobs still use the existing activation gate.

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

`apps/api/tests/test_api.py` and `test_hunar_dispatch.py` cover policy validation, persistence,
and payload mapping; full suite **78 passed**. Web: `npm run typecheck` and `npm run build`
pass; the production page was browser-verified through create account → create job → save
calling policy (2026-09-06). The refreshed create-job screen was browser-verified through
create job → extract/confirm details → draft workflow on desktop and a 360px-wide viewport
(2026-09-06); `npm run typecheck` and `npm run build` pass.

## Remaining limitations / open questions

- Dev-stub auth only; shadcn/ui not wired yet; no candidate/timeline UI yet (backend ready).
- Webhook runs processing inline (would be a Celery enqueue in production).
