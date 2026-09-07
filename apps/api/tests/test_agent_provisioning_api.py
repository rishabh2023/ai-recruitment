"""F-009 HTTP surface: view the per-stage voice agent, override it, and the provisioning guard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))


def _auth(client):
    client.post(
        "/dev/bootstrap",
        json={"org_name": "Acme", "user_email": "recruiter@acme.test", "password": "pw-123456"},
    )
    client.post("/auth/login", json={"email": "recruiter@acme.test", "password": "pw-123456"})
    return {}


def _draft_version(client, h, title="Backend Engineer"):
    jid = client.post("/jobs", json={"title": title}, headers=h).json()["id"]
    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": f"{title}\nPython, FastAPI"}, headers=h).json()
    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    workflow = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    return jid, workflow["id"]


def test_view_agents_reports_unset_when_no_binding_and_no_default(client):
    h = _auth(client)
    jid, vid = _draft_version(client, h)
    rows = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()
    assert rows, "expected at least one AI stage"
    assert all(r["execution_type"] == "ai" for r in rows)
    # No agent configured in the hermetic test env → the recruiter sees this stage is unset.
    assert all(r["source"] == "unset" and r["hunar_agent_id"] is None for r in rows)


def test_override_binds_a_specific_agent(client):
    h = _auth(client)
    jid, vid = _draft_version(client, h)
    rows = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()
    stage_id = rows[0]["stage_id"]
    resp = client.put(
        f"/jobs/{jid}/workflow/stages/{stage_id}/agent",
        json={"hunar_agent_id": "agent-chosen-by-recruiter"}, headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "bound"
    assert body["hunar_agent_id"] == "agent-chosen-by-recruiter"
    # And the view now reflects the binding.
    after = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()
    bound = next(r for r in after if r["stage_id"] == stage_id)
    assert bound["source"] == "bound" and bound["hunar_agent_id"] == "agent-chosen-by-recruiter"


def test_provision_requires_calling_configured(client):
    h = _auth(client)
    jid, vid = _draft_version(client, h)
    # Live calls are off + no Hunar key in the hermetic env → provisioning is refused, not silent.
    resp = client.post(f"/jobs/{jid}/workflow/versions/{vid}/agents/provision", headers=h)
    assert resp.status_code == 409, resp.text


def test_view_shows_objective_and_what_it_collects(client):
    h = _auth(client)
    jid, vid = _draft_version(client, h)
    rows = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()
    first = rows[0]
    # Clear, product-safe visibility of what each stage's agent does — derived even before binding.
    assert first["objective"] and isinstance(first["collects"], list)
    assert first["purpose_family"] in {"screening", "technical", "sales", "manager", "compensation"}
    assert "hunar" not in first["objective"].lower()  # no telephony internals leak into copy


def test_edit_agent_objective_and_collects_persists(client):
    h = _auth(client)
    jid, vid = _draft_version(client, h)
    rows = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()
    stage_id = rows[0]["stage_id"]
    # Bind an agent first (override), so there is an editable agent on the stage.
    client.put(f"/jobs/{jid}/workflow/stages/{stage_id}/agent", json={"hunar_agent_id": "agent-1"}, headers=h)
    resp = client.put(
        f"/jobs/{jid}/workflow/stages/{stage_id}/agent/spec",
        json={"objective": "Qualify interest and confirm start date only.", "collects": ["interest", "availability"]},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["objective"] == "Qualify interest and confirm start date only."
    assert set(body["collect_keys"]) == {"interest", "availability"}
    assert body["editable"] is True
    # The edit survives a reload.
    after = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()
    edited = next(r for r in after if r["stage_id"] == stage_id)
    assert edited["objective"] == "Qualify interest and confirm start date only."


def test_edit_requires_an_existing_agent(client):
    h = _auth(client)
    jid, vid = _draft_version(client, h)
    stage_id = client.get(f"/jobs/{jid}/workflow/versions/{vid}/agents", headers=h).json()[0]["stage_id"]
    # No agent bound yet → editing is refused with a clear message, not a silent no-op.
    resp = client.put(
        f"/jobs/{jid}/workflow/stages/{stage_id}/agent/spec",
        json={"objective": "x", "collects": ["interest"]}, headers=h,
    )
    assert resp.status_code == 409, resp.text
