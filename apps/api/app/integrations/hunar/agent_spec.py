"""Generate a Hunar agent spec from a funnel stage's intent (F-009).

Pure functions, no I/O. Given a stage's role/purpose and the fields it must collect
(`information_requirements`), produce a `POST /agents/` body whose script screens for that
exact role/stage and whose `result_schema` keys equal the stage's information requirements — so
the webhook stores every answer as candidate evidence, by construction.

Templating: placeholders use Hunar's single-brace form (e.g. ``{candidate_name}``), matching the
account's existing agents. The platform injects these via `custom_data` at call time. The exact
interpolation contract is pinned in docs/vendor-capability-matrix.md; keep this module in sync.
"""

from __future__ import annotations

from dataclasses import dataclass

# What each known requirement key means, phrased for the agent's ask-list, and its result type.
_FIELD_ASK = {
    "interest": "whether they are genuinely interested in this role",
    "current_ctc": "their current CTC / compensation",
    "expected_ctc": "their expected CTC / compensation",
    "notice_period": "their notice period or availability to start",
    "location": "their current location and willingness to relocate if relevant",
    "years_experience": "their years of relevant experience",
    "salary_expectation": "their salary expectation",
    "availability": "their availability / start date",
    "skills": "their relevant skills and recent hands-on work",
}
_FIELD_TYPE = {
    "interest": "boolean — true if the candidate is interested in the role",
    "years_experience": "number — years of relevant experience",
}
_DEFAULT_TYPE = "string — the candidate's answer, or null if not provided"

_MAX_NAME = 120

# Base configuration families (architecture §6.4): a stage's purpose selects a base script that
# is then specialised with the role, company, and the exact fields to collect. This is what makes
# a technical-interview stage evaluate against criteria while a screening stage qualifies interest
# and logistics, and a sales stage probes sales capability — instead of one generic script.
_PURPOSE_KEYWORDS = {
    "technical": ("technical", "interview", "coding", "engineering", "system design", "assessment"),
    "sales": ("sales", "sdr", "account executive", "quota", "pitch"),
    "manager": ("hiring manager", "manager round", "leadership", "director", "culture"),
    "compensation": ("compensation", "offer", "salary", "ctc negotiation", "package"),
    "screening": ("screen", "outreach", "intro", "qualify", "recruiter"),
}


def classify_purpose(stage_name: str, purpose: str) -> str:
    """Map a stage's name + purpose text to a base family. Defaults to ``screening`` — the safest,
    least-committal conversation — when nothing matches."""
    hay = f"{stage_name} {purpose}".lower()
    # Most-specific families first so "technical interview" doesn't fall through to "screening".
    for kind in ("compensation", "manager", "sales", "technical", "screening"):
        if any(kw in hay for kw in _PURPOSE_KEYWORDS[kind]):
            return kind
    return "screening"


# Per-family objective + prompt-body. `{ask_list}` and the role/stage are injected by the builder.
_BASE_SCRIPTS = {
    "screening": (
        "screen and qualify the candidate: confirm genuine interest and collect the required "
        "logistical details",
        "Confirm their interest in the role, then qualify logistical fit by asking about: "
        "{ask_list}. Keep it a short, warm screening conversation.",
    ),
    "technical": (
        "conduct a structured technical interview: assess the candidate against the role's "
        "criteria and capture concrete evidence of their skills",
        "Conduct a structured, role-specific technical interview. Ask about real, hands-on "
        "experience and probe for depth and specifics (projects, trade-offs, outcomes) on: "
        "{ask_list}. Capture concrete evidence, not just yes/no answers.",
    ),
    "sales": (
        "assess the candidate's sales capability: pitch, objection handling, and track record "
        "against target",
        "Assess sales capability with realistic probing on pitch, pipeline, quota attainment and "
        "objection handling, covering: {ask_list}. Ask for specific numbers and examples.",
    ),
    "manager": (
        "conduct a hiring-manager round: evaluate ownership, collaboration, and role fit at depth",
        "Conduct a hiring-manager conversation focused on ownership, collaboration and judgement, "
        "covering: {ask_list}. Probe for how they handled real situations.",
    ),
    "compensation": (
        "align on compensation and logistics before an offer: current/expected package, notice "
        "and start date",
        "Have a respectful compensation-and-logistics conversation covering: {ask_list}. Do not "
        "make or imply any offer; capture their numbers for the hiring team.",
    ),
}


# Purposes whose call is an EVALUATION interview — the agent probes the stage's success criteria,
# not just logistical fields. Screening/compensation are conversations about facts, not skills.
_INTERVIEW_KINDS = frozenset({"technical", "manager", "sales"})


@dataclass(frozen=True)
class StageIntent:
    """The minimal descriptor an agent needs to understand a stage."""

    role: str  # job title / domain, e.g. "Sales Executive"
    company: str
    stage_name: str  # e.g. "Initial Screening"
    collect: tuple[str, ...]  # stage.information_requirements
    purpose: str = ""  # stage.purpose — the stage's own description of what it is for
    criteria: tuple[str, ...] = ()  # stage success-criteria names (interview topics)


def stage_intent(
    *, job_title: str, company: str, stage_name: str, information_requirements, purpose: str = "", criteria=None
) -> StageIntent:
    reqs = tuple(str(k) for k in (information_requirements or []) if str(k).strip())
    crit = tuple(str(c) for c in (criteria or []) if str(c).strip())
    return StageIntent(
        role=(job_title or "this role").strip(),
        company=(company or "our company").strip(),
        stage_name=(stage_name or "screening").strip(),
        collect=reqs,
        purpose=(purpose or "").strip(),
        criteria=crit,
    )


def _ask_phrase(key: str) -> str:
    return _FIELD_ASK.get(key, key.replace("_", " "))


def _slug(name: str) -> str:
    """A result-schema key from a criterion name, e.g. 'Backend / API engineering' -> 'backend_api_engineering'."""
    out = []
    for ch in name.lower().strip():
        out.append(ch if ch.isalnum() else "_")
    slug = "_".join(filter(None, "".join(out).split("_")))
    return slug or "criterion"


def stage_topics(intent: StageIntent) -> list[tuple[str, str]]:
    """The (result_key, plain-language ask) pairs the agent should cover for this stage.

    Always the stage's information_requirements. For interview-type stages (technical/manager/
    sales), ALSO one topic per success criterion — so a technical stage actually interviews on
    Backend/API, System design, etc. rather than reusing a screening script. De-duplicated,
    order-preserving; falls back to a single ``interest`` topic when a stage defines nothing."""
    topics: list[tuple[str, str]] = [(k, _ask_phrase(k)) for k in intent.collect]
    if classify_purpose(intent.stage_name, intent.purpose) in _INTERVIEW_KINDS:
        topics += [(_slug(c), c) for c in intent.criteria]
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for key, phrase in topics:
        if key in seen:
            continue
        seen.add(key)
        uniq.append((key, phrase))
    return uniq or [("interest", _ask_phrase("interest"))]


def agent_profile(intent: StageIntent) -> dict:
    """The product-safe, editable summary of what a stage's agent does — no telephony internals.

    Keys: ``objective`` (what it accomplishes), ``collects`` (plain-language list of what it asks),
    ``purpose_family`` (screening/technical/…), ``name``. Derived from the same generator that
    builds the Hunar spec, so it faithfully describes a freshly generated agent."""
    spec = build_agent_spec(intent)
    topics = stage_topics(intent)
    return {
        "name": spec["name"],
        "objective": spec["objective"],
        "collects": [phrase for _, phrase in topics],
        "collect_keys": [key for key, _ in topics],
        "purpose_family": classify_purpose(intent.stage_name, intent.purpose),
    }


def build_agent_spec(
    intent: StageIntent,
    *,
    voice_persona: str = "NEHA",
    language: str = "ENGLISH",
    status: str = "ACTIVE",
) -> dict:
    """Build a `POST /agents/` body for the stage intent.

    `result_schema` keys are exactly the stage's collect fields (plus a free-text ``summary``),
    so extracted answers map 1:1 onto what the platform stores as evidence.
    """
    # Topics = information_requirements, plus the stage's success criteria for interview stages,
    # so a technical stage actually interviews on its criteria (never a bare screen).
    topics = stage_topics(intent)
    collect = [key for key, _ in topics]
    ask_list = "; ".join(phrase for _, phrase in topics)

    kind = classify_purpose(intent.stage_name, intent.purpose)
    base_objective, base_body = _BASE_SCRIPTS[kind]
    base_body = base_body.replace("{ask_list}", ask_list)

    name = f"{intent.role} — {intent.stage_name}"[:_MAX_NAME]
    introduction = (
        "Hi {candidate_name}, this is {persona_name} calling from {company} about the "
        "{job_role} role. Do you have a few minutes to talk?"
    )
    purpose_clause = f" Stage context: {intent.purpose}." if intent.purpose else ""
    objective = (
        f"Run the {intent.stage_name} for the {intent.role} role — {base_objective}.{purpose_clause}"
    )
    agent_prompt = (
        "You are {persona_name}, a professional and friendly interviewer for {company} speaking "
        "with {candidate_name} about the {job_role} role. Conduct the "
        f"{intent.stage_name}.{purpose_clause} {base_body} "
        "Keep the conversation focused and respectful. If they are not interested or ask to "
        "stop, thank them and end the call. Do not make any offer, promise, or commitment; the "
        "hiring team reviews next steps."
    )
    conclusion = (
        "Thank you for your time, {candidate_name}. Our team will review and follow up. "
        "Have a great day!"
    )

    result_schema = {k: _FIELD_TYPE.get(k, _DEFAULT_TYPE) for k in collect}
    result_schema["summary"] = "string — a concise summary of the candidate's responses and fit"
    result_variables = list(result_schema.keys())

    return {
        "name": name,
        "voice_persona": voice_persona,
        "language": language,
        "status": status,
        "introduction": introduction,
        "objective": objective,
        "agent_prompt": agent_prompt,
        "conclusion": conclusion,
        "result_prompt": (
            "From the call transcript, extract each field defined in the result schema. Use null "
            "for anything the candidate did not provide."
        ),
        "result_schema": result_schema,
        "result_variables": result_variables,
        "custom_variables": [
            "candidate_name", "persona_name", "job_role", "job_title", "role",
            "company", "location", "stage", "collect",
        ],
    }
