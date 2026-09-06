"""Pure unit tests for carry-forward and Hunar status mapping."""

from __future__ import annotations

from app.integrations.hunar import normalize_call_status
from app.workflow_execution import compute_effective_information


def test_prior_unresolved_comes_first_and_known_removed():
    out = compute_effective_information(
        stage_requirements=["expected_ctc", "notice_period", "skills"],
        unresolved_prior=["interest", "expected_ctc"],
        known_field_keys=["interest", "location"],
    )
    # interest is known (removed); expected_ctc appears once, prior-first; order preserved.
    assert out == ["expected_ctc", "notice_period", "skills"]


def test_all_known_yields_empty():
    assert compute_effective_information(["a", "b"], [], ["a", "b"]) == []


def test_dedup_within_inputs():
    assert compute_effective_information(["a", "a", "b"], ["a"], []) == ["a", "b"]


def test_status_mapping():
    assert normalize_call_status("IN_PROGRESS") == "CONNECTED"
    assert normalize_call_status("COMPLETED") == "COMPLETED"
    assert normalize_call_status("NOT_CONNECTED") == "NO_ANSWER"
    assert normalize_call_status("NOT_CONNECTED", retries_left=2) == "RETRY_SCHEDULED"
    assert normalize_call_status("RINGING") == "CALLING"
    assert normalize_call_status("SOMETHING_NEW") == "FAILED"
