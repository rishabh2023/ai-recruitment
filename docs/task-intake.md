# Task Intake

Every task is classified into a **tier** (drives planning, testing, review, release) and a
**documentation-impact level** (drives which documents must change). Classify before
planning.

## Task tiers

### Small — isolated, reversible UI or copy change

- **Examples:** copy edits, a class/style tweak, a non-behavioral refactor within one file.
- **Planning:** none beyond a one-line intent.
- **Tests:** type check + lint; existing tests still pass. Add a test only if behavior
  changed.
- **Docs:** usually Level 0.
- **Review:** self-review + fresh read.
- **Release:** single small commit; no special controls.

### Standard — feature, API, workflow, state, or multi-file change

- **Examples:** a new endpoint, a UI flow, a service method, a stage-config field.
- **Planning:** short plan, acceptance criteria, enumerated edge/failure/auth cases; feature
  brief exists and is linked in `INDEX.md`.
- **Tests:** unit + integration for changed logic; state-transition tests where relevant;
  browser verification for user-facing flows; the required states from `docs/experience.md`.
- **Docs:** Level 1–2.
- **Review:** fresh review pass; Definition of Done satisfied.
- **Release:** vertical slice; draft PR; inspect CI at exact head.

### High Risk — sensitive or hard-to-reverse

- **Triggers:** candidate personal data, authorization, deletion, external integration
  (Hunar/Apollo/LLM), webhooks, background work, migrations, production infrastructure, or
  any irreversible action.
- **Planning:** full plan with explicit risk analysis, rollback/recovery plan, and a
  verification plan; all depended-on vendor capabilities `VERIFIED`.
- **Tests:** everything in Standard **plus** webhook/idempotency, failure/retry (business vs
  infrastructure), authorization/cross-org, and staging verification.
- **Docs:** Level 2–3; an ADR in `docs/decisions/` for architectural/security/data/product
  decisions.
- **Review:** fresh review required; do not merge unless explicitly requested.
- **Release:** reversible migrations; documented rollback; observability in place before
  launch.

## Documentation-impact levels

| Level | Meaning | What to update |
| ----- | ------- | -------------- |
| **0** | No durable behavior change | Nothing (or a code comment). |
| **1** | Local feature behavior change | The feature brief; `docs/work/active-feature.md`. |
| **2** | Shared UI, API, domain, or quality change | The relevant canonical doc (`architecture` / `domain` / `interfaces` / `experience` / `quality`), the feature brief, and `docs/features/INDEX.md`. |
| **3** | Architecture, security, data model, or major product decision | An ADR in `docs/decisions/`, plus the affected canonical docs and `PROJECT.md` if the canonical model shifts. |

## Mapping tier → likely level

Small → usually Level 0. Standard → usually Level 1–2. High Risk → usually Level 2–3.
When in doubt, over-document by one level.
