# F-006 — Sourcing: People Search & Outreach

**Status:** Done  
**Risk tier:** Standard  
**Documentation impact:** Level 2

## Outcome

Recruiters can source real candidates for a job, add selected candidates to its pipeline,
and continue into enrichment and outreach. Search results retain their provider provenance;
the platform does not fabricate candidates.

## Search modes

- **Auto (recommended):** uses the configured People Data Labs (PDL)
  connection. It first runs the job-derived query exactly. When that returns no candidates,
  it performs one transparent retry: it removes seniority, or removes location when no
  seniority was supplied. The result explains the relaxation.
- **Manual:** recruiters may select a configured provider explicitly.
- Auto does not silently fan out across providers. Apollo search is plan-gated and Proxycurl
  and Coresignal have not been live-verified, so neither is used by Auto.
- If PDL is not configured, Auto returns an actionable availability error rather than invented
  results.

## Acceptance criteria

- Suggested filters derive from the selected job's extracted JD.
- An exact zero-result Auto search performs at most one documented broadening retry.
- Search responses preserve both the original query and the `applied_query` that produced the
  displayed result.
- The UI makes Auto the default when PDL is configured, preserves manual selection, and shows
  which provider supplied the result.
- Results can be added as `SOURCED` candidates without duplicate insertion.
- Provider, configuration, plan, and transport failures are visible to the recruiter.

## PDL query recall (post-launch fix)

The PDL Elasticsearch query was tuned so realistic JD-derived searches return people instead of
zero. Title uses analyzed `match_phrase` on a cleaned title (parentheticals/slashes stripped) —
an exact `terms` keyword match on e.g. "Full Stack Engineer (MERN)" matched nobody. Skills and
keywords are `should` boosts, not AND-ed `must` filters. Seniority applies only for values that
are valid PDL `job_title_levels` (buckets like "mid" are dropped rather than excluding everyone).
No explicit `minimum_should_match` (PDL rejects that clause; should-only bools use the ES default).
Verified live: the same JD query went from 0 → ~63k matches. Covered by
`apps/api/tests/test_pdl_query.py`.

## Verification

- `apps/api/tests/test_sourcing.py`: Auto broadening and missing-PDL coverage;
  `test_pdl_query.py`: query-construction (recall) coverage.
- Web typecheck and `git diff --check` pass.
- Signed-in browser verification: JD-suggested query returns real profiles (live PDL).
