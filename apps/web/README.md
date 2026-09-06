# Web (Next.js recruiter console)

Next.js (App Router) + React + TypeScript. Talks to the FastAPI backend. Plain CSS for now;
**shadcn/ui is the intended component layer** and plugs in next (kept out of this first
scaffold to keep the build lean). No Tailwind.

## Run

```bash
cd apps/web
cp .env.local.example .env.local     # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                          # http://localhost:3000
```

The backend must be running (see `apps/api/README.md`). On first load click **Connect
(dev session)** — it calls `POST /dev/bootstrap` to create a dev org + recruiter and stores
the ids in `localStorage`, sent as `X-Org-Id` / `X-User-Id` (placeholder auth).

## What's here

- `app/page.tsx` — dashboard: connect, list jobs, create-job CTA.
- `app/jobs/new/page.tsx` — guided job creation: create → paste JD → **confirm extracted
  details** → **draft workflow** → review stages → **approve** → **activate** (mirrors the
  Phase 2 approval gates).
- `lib/api.ts` — typed API client + dev session helpers.

## Verified

`npm run build` compiles and prerenders all routes; `npm run typecheck` is clean (2026-09-06).

## Next

Add shadcn/ui components; candidate import + timeline screens (backend endpoints already
exist: `POST /jobs/{id}/candidates`, `POST /job-candidates/{id}/launch`,
`GET /job-candidates/{id}/timeline`); loading/empty/error states per `docs/experience.md`.
