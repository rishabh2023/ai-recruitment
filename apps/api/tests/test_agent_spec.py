"""F-009 agent-spec generator: result schema mirrors the stage's collect fields."""

from __future__ import annotations

from app.integrations.hunar.agent_spec import build_agent_spec, classify_purpose, stage_intent


def test_purpose_classification_selects_base_family():
    assert classify_purpose("Technical Interview", "assess coding & system design") == "technical"
    assert classify_purpose("Sales Round", "pitch and quota") == "sales"
    assert classify_purpose("Compensation Discussion", "align on offer") == "compensation"
    assert classify_purpose("Hiring Manager Round", "leadership fit") == "manager"
    assert classify_purpose("Initial Screening", "confirm interest") == "screening"
    assert classify_purpose("", "") == "screening"  # safe default


def test_technical_stage_scripts_an_evaluation_not_a_screen():
    intent = stage_intent(
        job_title="Java Backend Developer", company="Acme", stage_name="Technical Interview",
        information_requirements=["skills", "years_experience"], purpose="assess backend depth",
    )
    spec = build_agent_spec(intent)
    # A technical stage must produce an evaluation-shaped script, distinct from a screening one.
    assert "technical interview" in spec["agent_prompt"].lower()
    assert "evidence" in spec["objective"].lower() or "criteria" in spec["objective"].lower()


def test_result_schema_keys_equal_information_requirements():
    intent = stage_intent(
        job_title="Full Stack Developer",
        company="Acme",
        stage_name="Initial Screening",
        information_requirements=["interest", "current_ctc", "expected_ctc", "notice_period", "location"],
    )
    spec = build_agent_spec(intent)
    # Every collect field is an extraction key (plus a free-text summary) — this is what makes
    # the candidate "Evidence & Results" panel populate.
    assert set(spec["result_schema"]) == {
        "interest", "current_ctc", "expected_ctc", "notice_period", "location", "summary"
    }
    assert set(spec["result_variables"]) == set(spec["result_schema"])


def test_role_and_stage_shape_name_and_prompt():
    intent = stage_intent(
        job_title="Sales Executive", company="Acme", stage_name="Initial Screening",
        information_requirements=["interest", "expected_ctc"],
    )
    spec = build_agent_spec(intent)
    assert spec["name"] == "Sales Executive — Initial Screening"
    # A Sales agent must not be scripted as a different role.
    assert "Sales Executive" in spec["objective"]
    assert "{candidate_name}" in spec["introduction"]
    assert "{job_role}" in spec["introduction"]


def test_technical_stage_interviews_on_its_success_criteria():
    # A technical stage often has NO information_requirements — its evaluation targets are its
    # success criteria. The agent must interview on those, with a result key per criterion.
    intent = stage_intent(
        job_title="Fullstack Engineer", company="Acme", stage_name="Technical Assessment",
        information_requirements=[], purpose="Evaluate engineering competencies",
        criteria=["Backend / API engineering", "System design", "Applied AI / LLM"],
    )
    spec = build_agent_spec(intent)
    assert {"backend_api_engineering", "system_design", "applied_ai_llm"} <= set(spec["result_schema"])
    assert "System design" in spec["agent_prompt"]


def test_screening_stage_ignores_criteria():
    # Screening is a facts conversation, not an evaluation — criteria are NOT turned into topics.
    intent = stage_intent(
        job_title="X", company="Y", stage_name="Initial Screening",
        information_requirements=["interest"], purpose="qualify", criteria=["System design"],
    )
    spec = build_agent_spec(intent)
    assert "system_design" not in spec["result_schema"]


def test_required_create_fields_present():
    intent = stage_intent(job_title="X", company="Y", stage_name="Z", information_requirements=[])
    spec = build_agent_spec(intent)
    # POST /agents/ required fields (docs/vendor-capability-matrix.md).
    for key in ("name", "voice_persona", "agent_prompt", "objective", "introduction", "result_schema", "language"):
        assert key in spec and spec[key], f"missing required field {key}"


def test_empty_requirements_still_screens_for_interest():
    intent = stage_intent(job_title="X", company="Y", stage_name="Screen", information_requirements=[])
    spec = build_agent_spec(intent)
    assert "interest" in spec["result_schema"]
    assert spec["result_schema"]["interest"].startswith("boolean")
