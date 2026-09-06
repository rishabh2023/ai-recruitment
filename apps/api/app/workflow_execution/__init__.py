"""Workflow execution engine: pure state machine + WorkflowExecutionService."""

from .effective_info import compute_effective_information
from .service import WorkflowExecutionService
from .state_machine import (
    InvalidTransition,
    OUTCOME_TARGET,
    StageOutcome,
    StageRunState,
    TERMINAL,
    TRANSITIONS,
    assert_transition,
    can_transition,
    is_terminal,
)

__all__ = [
    "WorkflowExecutionService",
    "compute_effective_information",
    "InvalidTransition",
    "StageOutcome",
    "StageRunState",
    "OUTCOME_TARGET",
    "TERMINAL",
    "TRANSITIONS",
    "assert_transition",
    "can_transition",
    "is_terminal",
]
