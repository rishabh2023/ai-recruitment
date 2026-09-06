"""Candidate stage-run state machine (pure, no I/O).

The DB stores stage-run state (TEXT + CHECK); valid *transitions* are enforced here, in the
application layer, per docs/domain.md and architecture §65. Keeping this pure makes it fully
unit-testable and the single source of truth for what moves are legal.
"""

from __future__ import annotations

from enum import Enum


class StageRunState(str, Enum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_RESULT = "AWAITING_RESULT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


#: States with no normal outgoing transition (only an explicit override may leave them).
TERMINAL: frozenset[StageRunState] = frozenset(
    {StageRunState.COMPLETED, StageRunState.FAILED, StageRunState.CANCELLED, StageRunState.SKIPPED}
)

# Any active (non-terminal) run may be cancelled; encoded per-state below for clarity.
_S = StageRunState
TRANSITIONS: dict[StageRunState, frozenset[StageRunState]] = {
    _S.PENDING: frozenset({_S.BLOCKED, _S.READY, _S.CANCELLED, _S.SKIPPED}),
    _S.BLOCKED: frozenset({_S.READY, _S.CANCELLED, _S.SKIPPED}),
    _S.READY: frozenset({_S.SCHEDULED, _S.IN_PROGRESS, _S.BLOCKED, _S.CANCELLED, _S.SKIPPED}),
    _S.SCHEDULED: frozenset({_S.IN_PROGRESS, _S.READY, _S.BLOCKED, _S.CANCELLED, _S.SKIPPED}),
    _S.IN_PROGRESS: frozenset(
        {_S.AWAITING_RESULT, _S.NEEDS_REVIEW, _S.COMPLETED, _S.FAILED, _S.CANCELLED}
    ),
    _S.AWAITING_RESULT: frozenset(
        {_S.NEEDS_REVIEW, _S.COMPLETED, _S.FAILED, _S.SCHEDULED, _S.CANCELLED}
    ),
    _S.NEEDS_REVIEW: frozenset(
        {_S.COMPLETED, _S.FAILED, _S.CANCELLED, _S.SKIPPED, _S.IN_PROGRESS, _S.READY}
    ),
    _S.COMPLETED: frozenset(),
    _S.FAILED: frozenset(),
    _S.CANCELLED: frozenset(),
    _S.SKIPPED: frozenset(),
}


class InvalidTransition(Exception):
    """Raised when a stage-run transition is not permitted by the state machine."""

    def __init__(self, current: StageRunState, target: StageRunState) -> None:
        super().__init__(f"Invalid stage-run transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def _coerce(state: StageRunState | str) -> StageRunState:
    return state if isinstance(state, StageRunState) else StageRunState(state)


def can_transition(current: StageRunState | str, target: StageRunState | str) -> bool:
    return _coerce(target) in TRANSITIONS[_coerce(current)]


def assert_transition(current: StageRunState | str, target: StageRunState | str) -> None:
    cur, tgt = _coerce(current), _coerce(target)
    if tgt not in TRANSITIONS[cur]:
        raise InvalidTransition(cur, tgt)


def is_terminal(state: StageRunState | str) -> bool:
    return _coerce(state) in TERMINAL


class StageOutcome(str, Enum):
    """Result of evaluating a completed stage against its transition policy."""

    PASS = "PASS"        # advance to next stage
    REVIEW = "REVIEW"    # needs a human decision
    REJECT = "REJECT"    # stop; candidate rejected
    RETRY = "RETRY"      # reschedule another attempt
    FAIL = "FAIL"        # execution failure (infrastructure)


#: Outcome → the stage-run state it drives the run into.
OUTCOME_TARGET: dict[StageOutcome, StageRunState] = {
    StageOutcome.PASS: StageRunState.COMPLETED,
    StageOutcome.REVIEW: StageRunState.NEEDS_REVIEW,
    StageOutcome.REJECT: StageRunState.COMPLETED,
    StageOutcome.RETRY: StageRunState.SCHEDULED,
    StageOutcome.FAIL: StageRunState.FAILED,
}
