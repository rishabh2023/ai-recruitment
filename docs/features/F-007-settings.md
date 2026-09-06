# F-007: Settings — Organization Configuration

- **Status:** Done
- **Risk tier:** Standard
- **Documentation-impact level:** 1
- **Affected areas:** Settings API, organization service, Settings UI, audit log, API tests
- **Depends on:** F-005 app scaffold and existing authenticated admin Settings access
- **Owner / current agent:** Codex

## Problem / intent

An organization administrator needs to correct or rename the organization displayed across
the recruitment workspace without database intervention.

## Scope

Admins can change the organization name from Settings. The name is persisted, returned by the
existing settings endpoint, and reflected immediately in the Settings UI. Settings uses focused
Organization, Providers, Outreach, and Team tabs so administrators work in one section at a
time instead of navigating a long stacked page. This change does not rename user accounts,
change organization identifiers, or affect vendor configuration.

## Vendor capabilities required

None.

## Acceptance criteria

- [x] Admin can save a trimmed non-empty organization name through `PUT /settings`.
- [x] Non-admin requests remain forbidden.
- [x] Blank and overlong names return a validation error without changing the saved name.
- [x] The rename is recorded in the audit log.
- [x] Settings renders an admin editor and read-only value for non-admin users.
- [x] Settings sections are available as responsive, keyboard-accessible tabs.

## Edge / failure / authorization cases

- Empty or whitespace-only names are rejected.
- Names longer than 120 characters are rejected.
- A non-admin receives the existing 403 organization-settings gate.
- Submitting the already saved value does not create a duplicate rename audit event.

## Evidence (Definition of Done)

- `apps/api/.venv/bin/python -m pytest tests/test_settings.py -q` — 11 passed.
- `apps/web: npm run typecheck` — passed.
- `git diff --check` — passed.

## Remaining limitations / open questions

Browser verification requires an authenticated local session; the API and type checks cover the
rename path and its validation/authorization states.
