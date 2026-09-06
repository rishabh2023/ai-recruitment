"""MCP server for the AI Recruitment Workflow platform.

Exposes the platform's recruiter workflow as MCP tools so it can be driven conversationally
from an MCP client (Claude Code, ChatGPT developer mode, etc.). Every tool is a thin wrapper
over the FastAPI backend (the same API the web app uses), so business rules, gates, auth, and
audit all still apply — the LLM operates in product concepts (jobs, candidates, sourcing,
outreach), never Hunar/telephony internals.

Auth: the server signs in once with a recruiter/admin account (env RECRUIT_EMAIL /
RECRUIT_PASSWORD) and reuses the session cookie, re-authenticating automatically on 401.

Transports:
- stdio (default) — for Claude Code / local subprocess hosts.
- streamable-http — set MCP_TRANSPORT=streamable-http (+ optional MCP_HOST/MCP_PORT) for
  network hosts such as ChatGPT custom connectors.

Config (env):
  RECRUIT_API_URL   backend base URL (default http://localhost:8000)
  RECRUIT_EMAIL     login email (default recruiter@demo.test)
  RECRUIT_PASSWORD  login password (default demo-password)
  MCP_TRANSPORT     stdio | streamable-http (default stdio)
  MCP_HOST/MCP_PORT bind for streamable-http (default 127.0.0.1:8765)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer  # mcp 2.x (FastMCP was renamed to MCPServer)

API_URL = os.environ.get("RECRUIT_API_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.environ.get("RECRUIT_EMAIL", "recruiter@demo.test")
PASSWORD = os.environ.get("RECRUIT_PASSWORD", "demo-password")

mcp = MCPServer("ai-recruitment")

# One cookie-bearing client for the whole process (session cookie persists across calls).
_client = httpx.Client(base_url=API_URL, timeout=40.0)


class ApiError(RuntimeError):
    """A backend call failed; message carries the platform's error text for the LLM."""


def _login() -> None:
    r = _client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        raise ApiError(
            f"Could not sign in to the recruitment API as {EMAIL} "
            f"(HTTP {r.status_code}). Check RECRUIT_EMAIL/RECRUIT_PASSWORD and that the API is running."
        )


def _call(method: str, path: str, *, json: Any | None = None, _retry: bool = True) -> Any:
    """Call the backend, (re)authenticating on 401. Returns parsed JSON (or None)."""
    resp = _client.request(method, path, json=json)
    if resp.status_code == 401 and _retry:
        _login()
        return _call(method, path, json=json, _retry=False)
    body: Any = None
    if resp.content:
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
    if resp.status_code >= 400:
        msg = None
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            msg = body["error"].get("message")
        raise ApiError(msg or f"{method} {path} failed (HTTP {resp.status_code}).")
    return body


# ---------------------------------------------------------------------------
# Context / dashboard
# ---------------------------------------------------------------------------
@mcp.tool()
def whoami() -> dict:
    """Return the signed-in principal (org, user, role). Use to confirm connectivity/auth."""
    return _call("GET", "/auth/me")


@mcp.tool()
def dashboard_summary() -> dict:
    """Org-wide hiring counts: total/active jobs, candidates in pipeline, needs-review,
    awaiting-result, failed calls. Good first call to understand current state."""
    return _call("GET", "/dashboard/summary")


@mcp.tool()
def recent_activity() -> list:
    """The most recent audit events across the organization (last ~15)."""
    return _call("GET", "/dashboard/activity")


# ---------------------------------------------------------------------------
# Jobs & workflow
# ---------------------------------------------------------------------------
@mcp.tool()
def list_jobs() -> list:
    """List all jobs (roles) in the organization with id, title, status, created_at."""
    return _call("GET", "/jobs")


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Fetch a single job by id."""
    return _call("GET", f"/jobs/{job_id}")


@mcp.tool()
def create_job(title: str) -> dict:
    """Create a new job (role) with a title. Returns the created job (id, status=draft).
    Next: add_job_description → confirm_job_version → draft_workflow → approve_workflow →
    activate_job."""
    return _call("POST", "/jobs", json={"title": title})


@mcp.tool()
def add_job_description(job_id: str, jd_text: str) -> dict:
    """Attach a job-description version (raw JD text). The platform extracts structured job
    metadata (title, location, skills, seniority). Returns the version incl. `extracted`.
    The recruiter must then confirm it before drafting a workflow."""
    return _call("POST", f"/jobs/{job_id}/versions", json={"jd_text": jd_text})


@mcp.tool()
def confirm_job_version(job_id: str, version_id: str) -> dict:
    """Confirm an extracted JD version as accurate (required before drafting a workflow)."""
    return _call("POST", f"/jobs/{job_id}/versions/{version_id}/confirm")


@mcp.tool()
def draft_workflow(job_id: str) -> dict:
    """Generate a draft hiring workflow (stages + criteria) from the confirmed JD. The draft is
    unapproved until a human approves it."""
    return _call("POST", f"/jobs/{job_id}/workflow/draft")


@mcp.tool()
def get_job_workflow(job_id: str) -> dict:
    """Get the job's effective workflow (approved else latest draft) with full stage detail:
    purpose, execution type, information to collect, approval requirements, weighted criteria."""
    return _call("GET", f"/jobs/{job_id}/workflow")


@mcp.tool()
def approve_workflow(job_id: str, version_id: str) -> dict:
    """Approve a drafted workflow version (human approval gate). Approved versions are
    read-only and enable candidate progression."""
    return _call("POST", f"/jobs/{job_id}/workflow/versions/{version_id}/approve")


@mcp.tool()
def activate_job(job_id: str) -> dict:
    """Activate a job for hiring. Blocked unless the latest JD is confirmed AND a workflow
    version is approved."""
    return _call("POST", f"/jobs/{job_id}/activate")


@mcp.tool()
def get_calling_policy(job_id: str) -> dict | None:
    """Get the job's calling window / retry / language policy (Hunar guardrails), or null."""
    return _call("GET", f"/jobs/{job_id}/calling-policy")


@mcp.tool()
def set_calling_policy(
    job_id: str,
    allowed_days: list[str],
    earliest_call_time: str,
    last_call_time: str,
    timezone: str,
    max_attempts: int = 3,
    retry_interval_hours: int = 6,
    language: str | None = None,
) -> dict:
    """Set the job's calling policy. allowed_days: >=3 of MON..SUN; times "HH:MM" with a >=3h
    window; timezone: IANA (e.g. Asia/Kolkata); retry_interval_hours in {0,3,6,9,12,24};
    max_attempts 1..10; language optional (Hunar agent-level)."""
    return _call("PUT", f"/jobs/{job_id}/calling-policy", json={
        "allowed_days": allowed_days, "earliest_call_time": earliest_call_time,
        "last_call_time": last_call_time, "timezone": timezone, "max_attempts": max_attempts,
        "retry_interval_hours": retry_interval_hours, "language": language,
    })


# ---------------------------------------------------------------------------
# Candidates & pipeline
# ---------------------------------------------------------------------------
@mcp.tool()
def list_candidates(job_id: str) -> list:
    """List candidates in a job's pipeline with their current stage and pipeline state."""
    return _call("GET", f"/jobs/{job_id}/candidates")


@mcp.tool()
def import_candidate(
    job_id: str,
    full_name: str,
    phone: str | None = None,
    email: str | None = None,
    location: str | None = None,
    known_facts: dict[str, str] | None = None,
) -> dict:
    """Add an existing candidate to a job. known_facts (e.g. {"expected_ctc":"24 LPA"}) become
    starting context carried into the AI stage. Returns the job-candidate."""
    return _call("POST", f"/jobs/{job_id}/candidates", json={
        "full_name": full_name, "phone": phone, "email": email, "location": location,
        "source": "import", "known_facts": known_facts or {},
    })


@mcp.tool()
def candidate_timeline(job_candidate_id: str) -> dict:
    """Full candidate workflow/timeline: profile, stage runs, call attempts, and collected
    facts/evidence."""
    return _call("GET", f"/job-candidates/{job_candidate_id}/timeline")


@mcp.tool()
def decide_candidate(job_candidate_id: str, outcome: str, reason: str | None = None) -> dict:
    """Recruiter decision on a candidate awaiting review. outcome: "pass" (advance) or
    "reject". Only valid when the current stage run is NEEDS_REVIEW."""
    return _call("POST", f"/job-candidates/{job_candidate_id}/decision",
                 json={"outcome": outcome, "reason": reason})


@mcp.tool()
def launch_stage(job_candidate_id: str) -> dict:
    """Launch the candidate's current AI stage — an interview (imported candidate) or an
    outreach call (sourced candidate). Requires a phone number (enrich first if missing).
    A real Hunar call is placed only when live calling is enabled; otherwise it is queued."""
    return _call("POST", f"/job-candidates/{job_candidate_id}/launch")


@mcp.tool()
def sync_call(call_id: str) -> dict:
    """Pull the latest status/result for a call from Hunar and apply it (on-demand refresh)."""
    return _call("POST", f"/calls/{call_id}/sync")


# ---------------------------------------------------------------------------
# Sourcing (People Search & Outreach — Flow B)
# ---------------------------------------------------------------------------
@mcp.tool()
def list_people_search_providers(job_id: str) -> dict:
    """List real people-search providers (Apollo/PDL/Proxycurl/Coresignal) and whether each is
    configured, plus the default. Configure keys via update_settings / the Settings screen."""
    return _call("GET", f"/jobs/{job_id}/sourcing/providers")


@mcp.tool()
def suggested_search_query(job_id: str) -> dict:
    """A starting people-search query derived from the job's JD (titles/locations/skills)."""
    return _call("GET", f"/jobs/{job_id}/sourcing/suggested-query")


@mcp.tool()
def people_search(
    job_id: str,
    provider: str | None = None,
    titles: list[str] | None = None,
    locations: list[str] | None = None,
    seniorities: list[str] | None = None,
    skills: list[str] | None = None,
    keywords: list[str] | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Search real candidates for a job via the chosen (or default) provider. Returns normalized
    profiles (no contact details — those come from enrichment). A provider that is unconfigured
    or plan-gated returns an honest error, never fabricated data."""
    return _call("POST", f"/jobs/{job_id}/sourcing/search", json={
        "provider": provider, "titles": titles or [], "locations": locations or [],
        "seniorities": seniorities or [], "skills": skills or [], "keywords": keywords or [],
        "page": page, "page_size": page_size,
    })


@mcp.tool()
def add_sourced_candidates(job_id: str, candidates: list[dict]) -> dict:
    """Add selected search results to the job pipeline as SOURCED (deduped by source+source_id).
    Each candidate dict should carry the fields from people_search results: source, source_id,
    full_name, and optionally title, company, location, linkedin_url."""
    return _call("POST", f"/jobs/{job_id}/sourcing/add", json={"candidates": candidates})


@mcp.tool()
def enrich_candidate(job_candidate_id: str) -> dict:
    """Reveal a sourced candidate's contact details (phone/email) via their source provider so
    an outreach call can be placed. Moves SOURCED → OUTREACH_PENDING. Idempotent."""
    return _call("POST", f"/job-candidates/{job_candidate_id}/enrich")


# ---------------------------------------------------------------------------
# Settings (admin)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_settings() -> dict:
    """Organization settings: people-search providers (+ configured flags), default provider,
    live-calling flag, and the team. Provider API keys are never returned."""
    return _call("GET", "/settings")


@mcp.tool()
def update_settings(
    default_provider: str | None = None,
    live_calls_enabled: bool | None = None,
    provider_keys: dict[str, str] | None = None,
) -> dict:
    """Admin-only. Set the default people-search provider, toggle live outbound calling, and/or
    set provider API keys (provider_keys map, e.g. {"pdl":"<key>"}; empty string clears a key).
    Keys are write-only — never echoed back."""
    payload: dict[str, Any] = {}
    if default_provider is not None:
        payload["default_provider"] = default_provider
    if live_calls_enabled is not None:
        payload["live_calls_enabled"] = live_calls_enabled
    if provider_keys is not None:
        payload["provider_keys"] = provider_keys
    return _call("PUT", "/settings", json=payload)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "8765")),
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
