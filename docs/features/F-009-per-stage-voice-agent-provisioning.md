# F-009: Per-stage voice-agent provisioning (intent-matched, auto-created)

- **Status:** Shipped to `main` (commits `09a98c4`, `e8c750f`) and verified against live Hunar
  calls. Delivered: intent generators; provisioning service (bound → LLM semantic match →
  deterministic name match → create), **coverage-aware** (only reuse an agent that collects/
  assesses everything the stage needs); **criteria-driven interview stages** (technical/manager/
  sales agents assess the stage's success criteria, not a screening script); eager+lazy triggers;
  surfaced default-agent fallback; view / override / **edit** API + recruiter-safe web panel; the
  Evidence key-mismatch fix (store every field Hunar returns); and an **LLM post-call assessment**
  (recommendation + per-criterion notes + recruiter summary). Remaining (nice-to-have): account-
  agent **name picker** for override (override currently takes an id); a persistent public webhook
  URL (dev uses an ephemeral tunnel); migrate/rebind any legacy hand-made agents.
- **Risk tier:** High Risk *(creates vendor resources and drives real candidate calls)*
- **Documentation-impact level:** 3
- **Affected areas:** `apps/api` (interviews / workflows), Hunar adapter, `apps/web` (funnel setup), `docs/architecture.md`, `docs/domain.md`, `docs/vendor-capability-matrix.md`
- **Depends on:** F-001 (Hunar contract), F-004 (interview execution). Verified Hunar `POST/PUT /agents/` and `GET /agents/`.
- **Owner / current agent:** Claude (vision captured 2026-09-07)

## Problem / intent

Every AI stage places a voice call through a Hunar **agent**. Today the platform uses **one
global default agent** (`HUNAR_DEFAULT_AGENT_ID`). That is wrong for a product with many roles
and many funnels:

- A single agent's script and result schema cannot fit every role and every stage. A Sales
  role, a Java Backend role, and a Full Stack role each need a different conversation.
- With one global default, a candidate for role X is screened by role Y's agent — the wrong
  intent — or, when the default points at a placeholder, a "test call".
- The stage that runs the call also defines *what to collect*
  (`stage.information_requirements`), but the agent's `result_schema` is authored separately, so
  extracted results frequently do not match the keys the platform stores → the candidate's
  "Evidence & Results" panel stays empty.

**The vision:** each **funnel stage** is backed by a voice agent that *understands that stage's
intent* — the role (job title/domain), the stage's purpose (screening vs technical interview vs
sales qualification vs compensation), and the exact information that stage must collect. If a
suitable agent already exists on the Hunar account, reuse it; **if one does not exist, create it
at the beginning** (when the funnel is set up/approved) so the stage is always ready to run a
correct, on-intent call. The agent's result schema is derived from the stage's
`information_requirements`, which also fixes the Evidence mismatch by construction.

The global `HUNAR_DEFAULT_AGENT_ID` becomes a last-resort fallback only, never the normal path.

## Scope

**In scope**

- A per-stage agent binding: `HunarAgentConfig(job_workflow_stage_id → hunar_agent_id)` becomes
  the primary resolution path (the code already prefers it; this feature *populates* it).
- An **agent-provisioning service** that, for each AI stage of a funnel, ensures a bound agent:
  1. **Bound already?** use it.
  2. **Match an existing agent by intent** (role + stage purpose) → bind it (reuse, no dup).
     *Implemented as a semantic **LLM match** (`LLMProvider.match_agent`, confidence ≥ 0.7,
     returns only a real candidate id) with a conservative deterministic name match as the
     offline fallback.*
  3. **No match → create one** via `POST /agents/` with an intent-derived
     name / introduction / objective / agent_prompt, `custom_variables` for the context the
     platform injects, and a `result_schema` whose keys are exactly the stage's
     `information_requirements` (so Evidence populates). Bind it.
- Provisioning trigger: at **funnel approval/activation** (eager, so stages are call-ready), and
  a **lazy safety net** at launch time if a stage is somehow unbound.
- A funnel-setup UI affordance to **view / override** the agent chosen for each AI stage (pick a
  different account agent, or re-provision).
- Result-schema/key alignment as a direct consequence (subsumes the standalone Evidence-key fix).

**Out of scope (for now)**

- Per-candidate agents (explicitly avoided — the model is reuse-agent + inject-context, ADR-0002).
- Editing an agent's *voice/persona* from our UI (choose persona at create; manage voices in Hunar).
- Multi-language agent generation (English first; language is a later extension).

## Vendor capabilities required

- `GET /agents/` (list) — `VERIFIED`. Used for intent-matching against existing agents.
- `GET /agents/{id}/` — `VERIFIED`. Read a candidate agent's config for matching/verification.
- `POST /agents/` (create) — `VERIFIED`. Required fields: name, voice_persona, agent_prompt,
  objective, introduction, result_schema (+ language default ENGLISH); status enum
  DRAFT/ACTIVE/ARCHIVED.
- `PUT /agents/{id}/` (update) — `VERIFIED`. For re-provisioning / keeping a bound agent in sync.
- `custom_data` per-call injection + agent `custom_variables`/`required_variables` — `VERIFIED`.
- **Templating syntax note (to verify before generating prompts):** observed working agents use
  **single-brace** placeholders (`{callee_name}`, `{persona_name}`, `{role}`), not `{{ }}`.
  Confirm against Hunar docs and pin the convention in the matrix before auto-generating prompts.

## Intent model (how an agent "understands the stage")

An agent is generated/selected from a small **stage intent descriptor**:

- `role` — job title + domain (e.g. "Sales Executive", "Java Backend Developer").
- `stage_purpose` — derived from the stage name/purpose and `execution_type` (screening,
  technical interview, hiring-manager, compensation…).
- `collect` — the stage's `information_requirements` (the exact keys to gather and extract).
- `company` — organization name.

From this descriptor the service produces:

- **introduction / objective / agent_prompt** — a role- and purpose-appropriate script that
  references injected variables (`{candidate_name}`, `{job_role}`, `{company}`) and asks for each
  `collect` field.
- **result_schema / result_variables** — one key per `collect` field (plus a free-text
  `summary`), typed sensibly (boolean for interest, string/number for the rest). **These keys
  equal the stage's `information_requirements`**, so the webhook stores every answer as evidence.
- **custom_variables** — the context keys the platform injects.

## Acceptance criteria

- [x] Creating/approving a funnel binds every AI stage to a Hunar agent (reused or newly created).
      *(Eager at approval via `maybe_provision_version_agents`; lazy net at dispatch.)*
- [x] Two jobs of different roles get **different** agents whose scripts match their role/stage.
      *(Name includes role+stage; purpose classifier selects a base family — screening / technical
      / sales / manager / compensation. Tests in `test_agent_spec.py`, `test_agent_provisioning.py`.)*
- [x] A newly created agent's `result_schema` keys equal the stage's `information_requirements`
      *(by construction in `agent_spec.build_agent_spec`)*; webhook→Evidence wiring pre-existing —
      **needs a staging call to confirm end-to-end population.**
- [x] Re-approving a funnel does **not** create duplicate agents (idempotent bound→matched→create;
      `test_version_sweep_binds_every_ai_stage_once`).
- [~] A recruiter can view the agent chosen per stage and override it. *View + override API done
      (`GET …/agents`, `PUT …/stages/{id}/agent`) and a recruiter-safe web panel; override by
      **account-agent name picker** (vs raw id) is the remaining UI slice.*
- [x] `HUNAR_DEFAULT_AGENT_ID` used only as fallback and **surfaced** (audit
      `interview.agent_fallback_default`), never silent.
- [x] No agent created without the live-calls guard + org authorization (`provisioning_ready`;
      provision endpoint returns 409 when calling is off — `test_provision_requires_calling_configured`).

## Edge / failure / authorization cases

- Hunar `POST /agents/` fails (rate limit / validation) → stage stays unbound, provisioning
  records a typed error; launch falls back to the default with a visible warning, never a silent
  wrong-agent call.
- Intent match is ambiguous (multiple similar agents) → prefer an exact bound/previous choice,
  else the highest-confidence name match, else create; never guess silently on a low-confidence
  match.
- Stage `information_requirements` is empty → generate a minimal interest+summary schema.
- Non-AI stage → no agent (skip).
- Only an admin/recruiter of the org may provision/override; agent ids are server-side (recruiters
  see "voice agent for this stage", never Hunar internals).
- Re-provision must not orphan in-flight calls already dispatched against the old binding.

## Plan (vertical slices, in order)

1. **Intent descriptor + generators** (pure, unit-tested): `stage → descriptor`,
   `descriptor → {name, introduction, objective, agent_prompt, custom_variables, result_schema}`.
2. **Provisioning service**: resolve-or-create per stage (bound → match → create → bind),
   idempotent, Hunar calls mocked in tests. Writes `HunarAgentConfig`.
3. **Triggers**: on funnel approval/activation (eager) + lazy at launch. Audited.
4. **Dispatch uses the binding** (already does via `_resolve_agent_id`); default becomes fallback
   with a surfaced warning.
5. **Web**: per-stage agent view/override in funnel setup.
6. **Docs**: architecture (agent ownership), domain (`HunarAgentConfig` lifecycle), matrix
   (templating syntax pinned).

## Evidence (Definition of Done)

Unit (generators, intent match), integration (provisioning idempotency with mocked Hunar,
result-schema == information_requirements), state (no dup on re-approve), authorization,
failure/fallback (create fails → visible default fallback), webhook (evidence populates from a
generated schema), browser (override UI), staging with a real Hunar sandbox agent before any live
candidate call.

## Notes

- This subsumes the standalone "Evidence & Results key mismatch" fix. It was fixed at the source:
  the webhook result handler (`app/modules/webhooks/service.py`) now stores **every field Hunar
  returns** as evidence (only pure transport metadata is skipped) rather than matching against a
  hardcoded key allowlist — so a renamed/added field never silently drops off the Evidence panel.
- Interim state is gone: the global `HUNAR_DEFAULT_AGENT_ID` is now a surfaced last-resort fallback
  only; each AI stage gets a correct per-stage agent.

## Implementation map (as shipped)

- **Generators** — `app/integrations/hunar/agent_spec.py`: `stage_intent`, `classify_purpose`
  (screening/technical/sales/manager/compensation), `stage_topics` (interview stages assess the
  stage's **success criteria**), `build_agent_spec`, `agent_profile`.
- **Provisioning** — `app/modules/interviews/agent_provisioning.py`: `AgentProvisioningService`
  (bound → LLM match → name match → create, coverage-aware, idempotent), `update_stage_agent`
  (edit objective + fields, push to Hunar), version sweep + `maybe_provision_version_agents`.
- **LLM boundary** — `app/integrations/llm/`: `match_agent` (semantic reuse, strict + fallback) and
  `assess_interview` (post-call recommendation + per-criterion notes + summary; Anthropic + stub).
- **Dispatch** — `app/modules/interviews/dispatch.py`: per-stage agent resolution + lazy provision;
  common context aliases (`role`, `persona_name`, `callee_name`, …) + placeholder fill for missing
  required vars (a missing optional detail never 422s); surfaced 422 body + default-fallback audit.
- **Result handling** — `app/modules/webhooks/service.py`: dynamic evidence storage + LLM assessment
  on `stage_results.assessment`.
- **API / Web** — `GET/POST/PUT /jobs/.../agents*` (view/provision/override/edit-spec); web Voice
  agents panel, "What the AI asks" per stage, and the AI Assessment card on the candidate view.
- **Migrations** — `hunar_agent_configs.spec` (`a1b2c3d4e5f6`), `stage_results.assessment`
  (`b2c3d4e5f6a7`). Applied automatically on container start (`RUN_MIGRATIONS=1`).
- **Related fix** — launching a freshly-advanced `PENDING` stage run promotes it to `READY` first
  (`app/modules/interviews/service.py`).
