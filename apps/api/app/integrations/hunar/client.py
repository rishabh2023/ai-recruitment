"""Thin Hunar Voice AI adapter (basic).

Hunar is the single voice/conversation provider (no multi-provider abstraction here, by
design). This client isolates Hunar's request/response shapes, centralizes auth
(`X-API-Key`) and the base URL, and exposes only the endpoints verified against the Hunar
external API. HTTP wiring is left to the transport the app chooses; method signatures and
the webhook verifier below reflect the VERIFIED contract in
docs/vendor-capability-matrix.md.

Verified base: https://api.voice.hunar.ai/external/v1  (auth: X-API-Key header)
Endpoints:   GET/POST /agents/, GET/PUT /agents/{id}/,
             GET/POST /calls/, POST /calls/bulk/, GET /calls/{id}/, GET /numbers/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass


@dataclass(frozen=True)
class HunarConfig:
    api_key: str
    base_url: str = "https://api.voice.hunar.ai/external/v1"
    webhook_signing_key: str = ""

    def auth_headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}


def verify_webhook_signature(
    *,
    signing_key: str,
    timestamp: str,
    raw_body: bytes,
    signature_header: str,
) -> bool:
    """Verify a Hunar webhook signature (VERIFIED contract).

    Signed message is ``f"{timestamp}.{raw_body}"``; the signature is a base64-encoded
    HMAC-SHA256 digest sent in ``X-Hunar-Signature`` (comma-separated if multiple keys
    are active). Comparison is constant-time.
    """
    if not signing_key or not signature_header:
        return False
    message = timestamp.encode("utf-8") + b"." + raw_body
    expected = base64.b64encode(
        hmac.new(signing_key.encode("utf-8"), message, hashlib.sha256).digest()
    ).decode("utf-8")
    candidates = [s.strip() for s in signature_header.split(",") if s.strip()]
    return any(hmac.compare_digest(expected, got) for got in candidates)


def webhook_dedup_key(event_type: str, call_id: str) -> str:
    """Stable idempotency key derived from documented identifiers.

    Hunar does not send a dedicated event id; the call id plus the event type uniquely
    identifies a delivery (see docs/interfaces.md — idempotency).
    """
    return f"{event_type}:{call_id}"


class HunarClient:
    """Verified method surface. Bind an HTTP transport in the app layer.

    Methods mirror the verified endpoints; concrete HTTP calls are intentionally not wired
    here so the adapter stays transport-agnostic and testable.
    """

    def __init__(self, config: HunarConfig) -> None:
        self._config = config

    # --- Agents -----------------------------------------------------------------
    def list_agents(self, *, page: int = 1) -> dict: ...
    def get_agent(self, agent_id: str) -> dict: ...
    def create_agent(self, payload: dict) -> dict: ...
    def update_agent(self, agent_id: str, payload: dict) -> dict: ...

    # --- Calls ------------------------------------------------------------------
    def list_calls(self, *, page: int = 1, **filters) -> dict: ...
    def get_call(self, call_id: str) -> dict: ...
    def create_call(self, payload: dict) -> dict: ...
    def create_bulk_calls(self, payload: dict) -> dict: ...

    # --- Numbers ----------------------------------------------------------------
    def list_numbers(self) -> dict: ...
