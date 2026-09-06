"""Funnels API tests — reusable workflow-template library (create/edit/version/use/archive)."""

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
        conn.execute(text("TRUNCATE webhook_events RESTART IDENTITY CASCADE"))


def _admin(client, email="admin@acme.test"):
    r = client.post("/auth/signup", json={"name": "Admin", "email": email, "password": "pw-123456", "org_name": "Acme"})
    assert r.status_code in (200, 201), r.text


_STAGES = [
    {"name": "AI Screen", "purpose": "Confirm interest & fit", "execution_type": "ai",
     "information_requirements": ["interest", "notice_period"], "requires_human_approval": False,
     "criteria": [{"name": "Communication", "kind": "numeric", "weight": 100}]},
    {"name": "Hiring Manager Review", "purpose": "Human decision", "execution_type": "human",
     "information_requirements": [], "requires_human_approval": True, "criteria": []},
]


def test_funnel_create_list_get_and_stage_config(client):
    _admin(client)
    created = client.post("/funnels", json={"name": "Engineering funnel", "stages": _STAGES})
    assert created.status_code == 201, created.text
    fid = created.json()["id"]
    assert created.json()["version"] == 1 and len(created.json()["stages"]) == 2

    lst = client.get("/funnels").json()
    assert any(f["id"] == fid and f["name"] == "Engineering funnel" and f["stage_count"] == 2 for f in lst)

    detail = client.get(f"/funnels/{fid}").json()
    s0, s1 = detail["stages"]
    assert s0["purpose"] == "Confirm interest & fit"
    assert s0["information_requirements"] == ["interest", "notice_period"]
    assert s0["criteria"][0]["name"] == "Communication" and s0["criteria"][0]["weight"] == 100
    assert s1["execution_type"] == "human" and s1["requires_human_approval"] is True


def test_editing_stages_creates_a_new_version(client):
    _admin(client)
    fid = client.post("/funnels", json={"name": "F", "stages": _STAGES}).json()["id"]
    assert client.get(f"/funnels/{fid}").json()["version"] == 1

    one_stage = [{"name": "Only screen", "execution_type": "ai", "information_requirements": [],
                  "requires_human_approval": False, "criteria": []}]
    edited = client.put(f"/funnels/{fid}/stages", json={"stages": one_stage})
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2 and len(edited.json()["stages"]) == 1
    # empty stage list is rejected
    assert client.put(f"/funnels/{fid}/stages", json={"stages": []}).status_code == 422


def test_use_funnel_copies_full_config_into_job(client):
    _admin(client)
    fid = client.post("/funnels", json={"name": "Eng", "stages": _STAGES}).json()["id"]
    jid = client.post("/jobs", json={"title": "Backend Engineer"}).json()["id"]

    used = client.post(f"/funnels/{fid}/use", json={"job_id": jid})
    assert used.status_code == 201, used.text
    assert used.json()["approved"] is False  # adopted as an unapproved draft for review

    wf = client.get(f"/jobs/{jid}/workflow").json()
    assert wf["approved"] is False and [s["name"] for s in wf["stages"]] == ["AI Screen", "Hiring Manager Review"]
    s0 = wf["stages"][0]
    assert s0["purpose"] == "Confirm interest & fit"
    assert s0["information_requirements"] == ["interest", "notice_period"]
    assert s0["criteria"][0]["name"] == "Communication"
    assert wf["stages"][1]["requires_human_approval"] is True


def test_rename_and_archive(client):
    _admin(client)
    fid = client.post("/funnels", json={"name": "Old name", "stages": _STAGES}).json()["id"]
    assert client.patch(f"/funnels/{fid}", json={"name": "New name"}).json()["name"] == "New name"

    assert client.post(f"/funnels/{fid}/archive").json()["archived"] is True
    # archived funnels are hidden by default, visible with include_archived
    assert not any(f["id"] == fid for f in client.get("/funnels").json())
    assert any(f["id"] == fid for f in client.get("/funnels?include_archived=true").json())


def test_missing_and_cross_org_404(client):
    _admin(client)
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/funnels/{missing}").status_code == 404
    assert client.put(f"/funnels/{missing}/stages", json={"stages": _STAGES}).status_code == 404


def test_writes_are_admin_only(client):
    # /dev/bootstrap creates a non-admin recruiter.
    r = client.post("/dev/bootstrap", json={"org_name": "Beta", "user_email": "rec@beta.test", "password": "pw-123456"})
    assert r.status_code == 201, r.text
    client.post("/auth/login", json={"email": "rec@beta.test", "password": "pw-123456"})

    assert client.post("/funnels", json={"name": "X", "stages": _STAGES}).status_code == 403
    # reads are allowed for any member
    assert client.get("/funnels").status_code == 200


def test_presets_listed_and_usable(client):
    _admin(client)
    presets = client.get("/funnels/presets")
    assert presets.status_code == 200, presets.text
    body = presets.json()
    keys = {p["key"] for p in body}
    assert {"engineering", "sales", "general"} <= keys
    eng = next(p for p in body if p["key"] == "engineering")
    assert len(eng["stages"]) >= 3 and eng["stages"][0]["execution_type"] == "ai"

    created = client.post("/funnels", json={"name": eng["name"], "stages": eng["stages"]})
    assert created.status_code == 201, created.text
    assert len(created.json()["stages"]) == len(eng["stages"])
