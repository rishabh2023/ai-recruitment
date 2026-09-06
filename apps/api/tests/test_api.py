"""End-to-end API tests via FastAPI TestClient (real DB, committed rows cleaned up)."""

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
    # Clean up committed rows (the API commits per request).
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE webhook_events RESTART IDENTITY CASCADE"))


def _auth(client):
    """Bootstrap an org+recruiter, then log in. The session cookie is stored on the
    TestClient's cookie jar and sent automatically on later requests, so callers can pass an
    empty headers dict."""
    r = client.post(
        "/dev/bootstrap",
        json={"org_name": "Acme", "user_email": "recruiter@acme.test", "password": "pw-123456"},
    )
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": "recruiter@acme.test", "password": "pw-123456"})
    assert login.status_code == 200, login.text
    return {}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_unauthorized_without_cookie(client):
    r = client.get("/jobs")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_full_flow(client):
    h = _auth(client)

    job = client.post("/jobs", json={"title": "Backend Engineer"}, headers=h).json()
    jid = job["id"]
    assert job["status"] == "draft"

    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": "Backend Engineer\nPython, FastAPI"}, headers=h).json()
    assert ver["confirmed"] is False and ver["extracted"]["role_family"] == "engineering"

    # activation blocked before confirm/approve
    assert client.post(f"/jobs/{jid}/activate", headers=h).status_code == 409

    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    wf = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    assert wf["approved"] is False

    stages = client.get(f"/jobs/{jid}/workflow/versions/{wf['id']}/stages", headers=h).json()
    assert stages[0]["stage_order"] == 1

    client.post(f"/jobs/{jid}/workflow/versions/{wf['id']}/approve", headers=h)
    act = client.post(f"/jobs/{jid}/activate", headers=h).json()
    assert act["status"] == "active"

    # rich workflow view: approved, ordered stages with detail + criteria
    wfd = client.get(f"/jobs/{jid}/workflow", headers=h).json()
    assert wfd["approved"] is True
    assert wfd["stages"][0]["stage_order"] == 1
    assert "execution_type" in wfd["stages"][0]
    assert any(st["criteria"] for st in wfd["stages"])  # at least one stage has criteria

    jc = client.post(
        f"/jobs/{jid}/candidates",
        json={"full_name": "Asha", "phone": "+919999999999", "known_facts": {"location": "Bengaluru"}},
        headers=h,
    ).json()
    jc_id = jc["id"]

    # list candidates for the job (display fields + resolved stage name)
    lst = client.get(f"/jobs/{jid}/candidates", headers=h).json()
    assert len(lst) == 1
    assert lst[0]["candidate"]["full_name"] == "Asha"
    assert lst[0]["current_stage_name"]  # resolved, not just an id

    launch = client.post(f"/job-candidates/{jc_id}/launch", headers=h).json()
    assert launch["normalized_status"] == "QUEUED"
    assert "collect" in launch["hunar_payload"]["custom_data"]
    request_id = launch["hunar_payload"]["request_id"]

    event = {
        "event": "call_result_done", "id": "hunar-1", "request_id": request_id,
        "status": "COMPLETED", "result": {"interested": "yes", "expected_ctc": "24 LPA"},
    }
    r1 = client.post("/webhooks/hunar", json=event)
    assert r1.json() == {"status": "received", "duplicate": False}
    r2 = client.post("/webhooks/hunar", json=event)
    assert r2.json()["duplicate"] is True  # idempotent

    tl = client.get(f"/job-candidates/{jc_id}/timeline", headers=h).json()
    assert tl["candidate"]["full_name"] == "Asha"
    assert tl["stage_runs"][0]["stage_name"]  # resolved stage name
    assert any(f["field_key"] == "expected_ctc" for f in tl["facts"])
    assert tl["calls"][0]["normalized_status"] == "COMPLETED"
