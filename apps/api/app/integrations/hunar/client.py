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

import httpx


@dataclass(frozen=True)
class HunarConfig:
    api_key: str
    base_url: str = "https://api.voice.hunar.ai/external/v1"
    webhook_signing_key: str = ""

    def auth_headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}


class HunarError(Exception):
    """A Hunar API call failed (network, timeout, or non-2xx). Carries status + body."""

    def __init__(self, message: str, *, status_code: int | None = None, body: object = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


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
    """HTTP client for the verified Hunar endpoints (auth via ``X-API-Key``).

    Bounded timeout so a slow/failing vendor never hangs a worker; non-2xx and transport
    errors raise ``HunarError`` (with status + parsed body when available).
    """

    def __init__(self, config: HunarConfig, *, timeout: float = 30.0) -> None:
        self._config = config
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings) -> "HunarClient":
        return cls(
            HunarConfig(
                api_key=settings.hunar_api_key,
                base_url=settings.hunar_api_base_url,
                webhook_signing_key=settings.hunar_webhook_signing_key,
            )
        )

    def _request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> dict:
        url = f"{self._config.base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as c:
                r = c.request(method, url, headers=self._config.auth_headers(), json=json, params=params)
        except httpx.HTTPError as exc:
            raise HunarError(f"Hunar request failed: {exc}") from exc
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = r.text
            raise HunarError(
                f"Hunar {method} {path} -> {r.status_code}", status_code=r.status_code, body=body
            )
        return r.json() if r.content else {}

    # --- Agents -----------------------------------------------------------------
    def list_agents(self, *, page: int = 1) -> dict:
        return self._request("GET", "/agents/", params={"page": page})

    def get_agent(self, agent_id: str) -> dict:
        return self._request("GET", f"/agents/{agent_id}/")

    def create_agent(self, payload: dict) -> dict:
        return self._request("POST", "/agents/", json=payload)

    def update_agent(self, agent_id: str, payload: dict) -> dict:
        return self._request("PUT", f"/agents/{agent_id}/", json=payload)

    # --- Calls ------------------------------------------------------------------
    def list_calls(self, *, page: int = 1, **filters) -> dict:
        return self._request("GET", "/calls/", params={"page": page, **filters})

    def get_call(self, call_id: str) -> dict:
        return self._request("GET", f"/calls/{call_id}/")

    def create_call(self, payload: dict) -> dict:
        return self._request("POST", "/calls/", json=payload)

    def create_bulk_calls(self, payload: dict) -> dict:
        return self._request("POST", "/calls/bulk/", json=payload)

    # --- Numbers ----------------------------------------------------------------
    def list_numbers(self) -> dict:
        return self._request("GET", "/numbers/")
