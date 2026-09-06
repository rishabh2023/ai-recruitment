"""Pure unit tests for the stage-run state machine (no DB)."""

from __future__ import annotations

import pytest

from app.workflow_execution.state_machine import (
    OUTCOME_TARGET,
    InvalidTransition,
    StageOutcome,
    StageRunState,
    TERMINAL,
    TRANSITIONS,
    assert_transition,
    can_transition,
    is_terminal,
)

S = StageRunState


def test_every_state_has_a_transition_entry():
    assert set(TRANSITIONS) == set(S)


def test_terminal_states_have_no_outgoing():
    for t in TERMINAL:
        assert TRANSITIONS[t] == frozenset()
        assert is_terminal(t)


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.PENDING, S.READY),
        (S.READY, S.SCHEDULED),
        (S.SCHEDULED, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.AWAITING_RESULT),
        (S.AWAITING_RESULT, S.COMPLETED),
        (S.IN_PROGRESS, S.NEEDS_REVIEW),
        (S.NEEDS_REVIEW, S.COMPLETED),
        (S.AWAITING_RESULT, S.SCHEDULED),  # business retry
    ],
)
def test_valid_transitions(src, dst):
    assert can_transition(src, dst)
    assert_transition(src, dst)  # does not raise


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.COMPLETED, S.PENDING),
        (S.PENDING, S.IN_PROGRESS),   # must go through READY/SCHEDULED
        (S.FAILED, S.COMPLETED),
        (S.CANCELLED, S.READY),
    ],
)
def test_invalid_transitions_raise(src, dst):
    assert not can_transition(src, dst)
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def test_string_inputs_accepted():
    assert can_transition("PENDING", "READY")
    with pytest.raises(InvalidTransition):
        assert_transition("COMPLETED", "PENDING")


def test_outcome_targets_are_complete_and_sane():
    assert set(OUTCOME_TARGET) == set(StageOutcome)
    assert OUTCOME_TARGET[StageOutcome.PASS] == S.COMPLETED
    assert OUTCOME_TARGET[StageOutcome.REVIEW] == S.NEEDS_REVIEW
    assert OUTCOME_TARGET[StageOutcome.RETRY] == S.SCHEDULED
    assert OUTCOME_TARGET[StageOutcome.FAIL] == S.FAILED
