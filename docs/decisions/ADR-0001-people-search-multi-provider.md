# ADR-0001: People search is a multi-provider adapter

- **Status:** Accepted
- **Date:** 2026-09-06
- **Deciders:** Rishabh (owner), Claude Code
- **Documentation-impact level:** 2

## Context

The assignment email (Assignment 1 — Hunar AI) states for the People Search & Reachout
journey: "use any of the people search APIs - People Data Labs (PDL), Apollo.IO, Proxycurl,
Coresignal." The owner explicitly asked for a **basic provider-agnostic adapter**, not an
Apollo-only integration. The earlier architecture note "no generic multi-provider
abstraction" was about the **voice** provider (Hunar is the sole voice provider) and does
not apply to sourcing.

## Decision

People search is accessed through a thin `PeopleSearchProvider` interface with one active
provider selected at runtime via `PEOPLE_SEARCH_PROVIDER` (`apollo` | `pdl` | `proxycurl` |
`coresignal`). Apollo is the first implementation; the others are registered keys that fail
with a clear "not implemented" error until added. Providers normalize results to a common
`ExternalCandidate` shape, model missing fields as absence, and preserve provenance
(`source`, `source_id`, `raw`). Implemented in
`apps/api/app/integrations/people_search/`.

## Alternatives considered

- **Apollo-only client** — simplest, but contradicts the assignment and the owner's request;
  swapping providers would touch every caller.
- **Full plugin framework / entry points** — over-engineered for assignment scope.

## Consequences

- Positive: provider swap is a config change; callers depend only on normalized types; aligns
  with the assignment's allowed providers.
- Trade-off: a normalization layer must map each provider's fields; per-provider capabilities
  still need verification before use (tracked in the capability matrix).
- Voice stays deliberately single-provider (Hunar) — this ADR does not introduce a voice
  abstraction.

## Evidence / references

Assignment email (People Search options); `docs/interfaces.md`;
`apps/api/app/integrations/people_search/` (base, apollo, registry).
