"""Hunar ↔ platform mapping helpers (verified contract, F-001).

Maps Hunar's documented `CallStatus` to our normalized business status, and builds the
`POST /calls/` request payload from the effective stage context. Pure functions — no I/O.
"""

from __future__ import annotations

from typing import Any

# Hunar CallStatus (verified) → normalized status (docs/domain.md).
HUNAR_STATUS_MAP: dict[str, str] = {
    "NOT_STARTED": "QUEUED",
    "SCHEDULED": "SCHEDULED",
    "INITIATED": "CALLING",
    "RINGING": "CALLING",
    "IN_PROGRESS": "CONNECTED",
    "COMPLETED": "COMPLETED",
    "NOT_CONNECTED": "NO_ANSWER",
    "FAILED": "FAILED",
    "CANCELLED": "CANCELLED",
}


def normalize_call_status(hunar_status: str, *, retries_left: int | None = None) -> str:
    """Normalize a Hunar status. NOT_CONNECTED becomes RETRY_SCHEDULED when retries remain."""
    normalized = HUNAR_STATUS_MAP.get(hunar_status, "FAILED")
    if hunar_status == "NOT_CONNECTED" and retries_left and retries_left > 0:
        return "RETRY_SCHEDULED"
    return normalized


def build_call_request(
    *,
    agent_id: str,
    callee_name: str,
    mobile_number: str,
    custom_data: dict[str, str] | None = None,
    request_id: str | None = None,
    timezone: str | None = None,
    guardrails: dict[str, Any] | None = None,
    retry_config: dict[str, Any] | None = None,
    callback_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the verified `POST /calls/` body. Stage/candidate context rides in `custom_data`
    (the stage-driven model reuses an agent + injects context — ADR-0002)."""
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "callee_name": callee_name,
        "mobile_number": mobile_number,
    }
    if custom_data:
        body["custom_data"] = {k: str(v) for k, v in custom_data.items()}
    if request_id:
        body["request_id"] = request_id[:64]
    if timezone:
        body["timezone"] = timezone
    if guardrails:
        body["guardrails"] = guardrails
    if retry_config:
        body["retry_config"] = retry_config
    if callback_config:
        body["callback_config"] = callback_config
    return body
