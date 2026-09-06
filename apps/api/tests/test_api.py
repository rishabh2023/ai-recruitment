"""End-to-end API tests via FastAPI TestClient (real DB, committed rows cleaned up)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.main import app
from app.modules.audit.models import AuditEvent


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


def test_archived_job_can_be_reactivated_and_audits_both_changes(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Backend Engineer"}, headers=h).json()["id"]
    ver = client.post(
        f"/jobs/{jid}/versions", json={"jd_text": "Backend Engineer\nPython"}, headers=h
    ).json()
    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    workflow = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    client.post(f"/jobs/{jid}/workflow/versions/{workflow['id']}/approve", headers=h)
    assert client.post(f"/jobs/{jid}/activate", headers=h).json()["status"] == "active"

    archived = client.post(f"/jobs/{jid}/archive", headers=h)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    assert client.get(f"/jobs/{jid}", headers=h).json()["status"] == "archived"

    reactivated = client.post(f"/jobs/{jid}/activate", headers=h)
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "active"

    actions = {item["action"] for item in client.get("/dashboard/activity", headers=h).json()}
    assert {"job.archived", "job.activated"} <= actions


def test_draft_role_can_be_archived(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Draft role"}, headers=h).json()["id"]

    r = client.post(f"/jobs/{jid}/archive", headers=h)

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "archived"
    assert client.get(f"/jobs/{jid}", headers=h).json()["status"] == "archived"
    # archiving is idempotent
    assert client.post(f"/jobs/{jid}/archive", headers=h).json()["status"] == "archived"


def test_unauthorized_without_cookie(client):
    r = client.get("/jobs")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_edit_workflow_stages(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Data Scientist"}, headers=h).json()["id"]
    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": "Data Scientist\nPython, ML"}, headers=h).json()
    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    wf = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()

    # customize: replace with two stages
    payload = {"stages": [
        {"name": "Phone Screen", "execution_type": "ai", "information_requirements": ["interest", "notice_period"],
         "criteria": [{"name": "Communication", "kind": "numeric", "weight": 100}]},
        {"name": "Final Review", "execution_type": "human", "requires_human_approval": True},
    ]}
    r = client.put(f"/jobs/{jid}/workflow/versions/{wf['id']}/stages", json=payload, headers=h)
    assert r.status_code == 200, r.text
    stages = r.json()["stages"]
    assert [s["name"] for s in stages] == ["Phone Screen", "Final Review"]
    assert stages[0]["stage_order"] == 1 and stages[0]["criteria"][0]["weight"] == 100
    assert stages[1]["requires_human_approval"] is True

    # invalid execution type rejected
    bad = {"stages": [{"name": "X", "execution_type": "robot"}]}
    assert client.put(f"/jobs/{jid}/workflow/versions/{wf['id']}/stages", json=bad, headers=h).status_code == 422

    # once approved, editing is blocked
    client.post(f"/jobs/{jid}/workflow/versions/{wf['id']}/approve", headers=h)
    assert client.put(f"/jobs/{jid}/workflow/versions/{wf['id']}/stages", json=payload, headers=h).status_code == 409


def test_calling_policy_upsert_and_validation(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Support Rep"}, headers=h).json()["id"]
    assert client.get(f"/jobs/{jid}/calling-policy", headers=h).json() is None

    good = {"allowed_days": ["MON", "TUE", "WED"], "earliest_call_time": "09:00",
            "last_call_time": "18:00", "timezone": "Asia/Kolkata", "max_attempts": 3,
            "retry_interval_hours": 6, "language": "ENGLISH"}
    r = client.put(f"/jobs/{jid}/calling-policy", json=good, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["earliest_call_time"] == "09:00" and r.json()["timezone"] == "Asia/Kolkata"
    # persisted
    assert client.get(f"/jobs/{jid}/calling-policy", headers=h).json()["language"] == "ENGLISH"

    # < 3 days rejected
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "allowed_days": ["MON", "TUE"]}, headers=h).status_code == 422
    # A saved policy must be complete; silently omitting a partial policy would allow unrestricted calls.
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "allowed_days": []}, headers=h).status_code == 422
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "earliest_call_time": None}, headers=h).status_code == 422
    # < 3h window rejected
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "last_call_time": "10:00"}, headers=h).status_code == 422
    # bad retry interval rejected
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "retry_interval_hours": 5}, headers=h).status_code == 422
    # Hunar accepts IANA timezones and a fixed set of agent languages only.
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "timezone": "India/Delhi"}, headers=h).status_code == 422
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "language": "KLINGON"}, headers=h).status_code == 422
    # An initial call is always placed, so zero total attempts is not a meaningful policy.
    assert client.put(f"/jobs/{jid}/calling-policy", json={**good, "max_attempts": 0}, headers=h).status_code == 422
    with Session(engine) as session:
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "calling_policy.saved")) is not None


def test_full_flow(client):
    h = _auth(client)

    job = client.post("/jobs", json={"title": "Backend Engineer"}, headers=h).json()
    jid = job["id"]
    assert job["status"] == "draft"

    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": "Backend Engineer\nPython, FastAPI"}, headers=h).json()
    assert ver["confirmed"] is False and ver["extracted"]["role_family"] == "engineering"
    assert ver["jd_text"] == "Backend Engineer\nPython, FastAPI"
    # the JD card reads the latest version back (raw text + confirmed flag)
    latest = client.get(f"/jobs/{jid}/version", headers=h).json()
    assert latest["id"] == ver["id"] and latest["jd_text"] == "Backend Engineer\nPython, FastAPI"

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

    # recruiter decision: candidate is NEEDS_REVIEW after the result → advance to next stage
    dec = client.post(f"/job-candidates/{jc_id}/decision", json={"outcome": "pass"}, headers=h).json()
    assert dec["advanced"] is True and dec["current_stage_name"]

    tl = client.get(f"/job-candidates/{jc_id}/timeline", headers=h).json()
    assert tl["candidate"]["full_name"] == "Asha"
    assert tl["stage_runs"][0]["stage_name"]  # resolved stage name
    assert any(f["field_key"] == "expected_ctc" for f in tl["facts"])
    assert tl["calls"][0]["normalized_status"] == "COMPLETED"


def test_get_latest_version_null_when_no_jd(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "No JD Yet"}, headers=h).json()["id"]
    assert client.get(f"/jobs/{jid}/version", headers=h).json() is None


def test_job_funnel_cumulative_reached(client):
    from uuid import UUID

    from app.modules.candidates.models import JobCandidate

    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Data Analyst"}, headers=h).json()["id"]
    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": "Data Analyst\nSQL, dashboards"}, headers=h).json()
    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    wf = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    client.post(f"/jobs/{jid}/workflow/versions/{wf['id']}/approve", headers=h)
    stages = client.get(f"/jobs/{jid}/workflow", headers=h).json()["stages"]
    assert len(stages) >= 2, "stub workflow should have multiple stages"
    stage0_id = stages[0]["id"]

    # empty funnel: no candidates yet, no divide-by-zero
    empty = client.get(f"/jobs/{jid}/funnel", headers=h).json()
    assert empty["total"] == 0 and empty["completion_pct"] == 0.0
    assert empty["stages"][0]["reached"] == 0 and empty["stages"][0]["reached_pct"] == 0.0

    # three candidates all land at the first stage on import
    ids = [
        client.post(f"/jobs/{jid}/candidates", json={"full_name": name}, headers=h).json()["id"]
        for name in ("Alice", "Bob", "Cara")
    ]
    for cid in ids:
        assert client.get(f"/jobs/{jid}/candidates", headers=h)  # sanity: reachable

    # Craft persisted pipeline states: A completed the whole workflow, B rejected at stage 0,
    # C still sitting at stage 0. (Driving each stage's NEEDS_REVIEW over HTTP is out of scope
    # for this read-model test.)
    with Session(engine) as session:
        a, b, c = (session.get(JobCandidate, UUID(i)) for i in ids)
        a.pipeline_state, a.current_stage_id = "COMPLETED", None
        b.pipeline_state = "REJECTED"  # keep current_stage_id at stage 0 (furthest reached)
        # C left as imported (INTERVIEW_PENDING at stage 0)
        session.commit()

    funnel = client.get(f"/jobs/{jid}/funnel", headers=h).json()
    assert funnel["total"] == 3
    assert funnel["rejected"] == 1 and funnel["completed"] == 1 and funnel["in_progress"] == 1
    assert funnel["completion_pct"] == 33.3
    s0, s1 = funnel["stages"][0], funnel["stages"][1]
    # cumulative reached: everyone reached stage 0; only the completed candidate reached stage 1+
    assert s0["reached"] == 3 and s0["reached_pct"] == 100.0
    assert s1["reached"] == 1
    # current occupancy excludes rejected/completed → only C sits at stage 0
    assert s0["stage_id"] == stage0_id and s0["current"] == 1


def test_org_wide_candidate_directory(client):
    h = _auth(client)
    j1 = client.post("/jobs", json={"title": "Backend Engineer"}, headers=h).json()["id"]
    j2 = client.post("/jobs", json={"title": "Data Analyst"}, headers=h).json()["id"]
    client.post(f"/jobs/{j1}/candidates", json={"full_name": "Asha"}, headers=h)
    client.post(f"/jobs/{j2}/candidates", json={"full_name": "Bo"}, headers=h)

    rows = client.get("/candidates", headers=h)
    assert rows.status_code == 200, rows.text
    body = rows.json()
    assert len(body) == 2
    by_name = {r["candidate"]["full_name"]: r for r in body}
    assert by_name["Asha"]["job_title"] == "Backend Engineer"
    assert by_name["Bo"]["job_title"] == "Data Analyst"
    assert all("pipeline_state" in r and "created_at" in r for r in body)


def test_delete_job_only_when_not_active(client):
    h = _auth(client)
    # active job cannot be deleted
    jid = client.post("/jobs", json={"title": "Live role"}, headers=h).json()["id"]
    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": "Live role\nPython"}, headers=h).json()
    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    wf = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    client.post(f"/jobs/{jid}/workflow/versions/{wf['id']}/approve", headers=h)
    client.post(f"/jobs/{jid}/activate", headers=h)
    assert client.delete(f"/jobs/{jid}", headers=h).status_code == 409

    # a draft job deletes (204) and is gone
    draft = client.post("/jobs", json={"title": "Throwaway"}, headers=h).json()["id"]
    assert client.delete(f"/jobs/{draft}", headers=h).status_code == 204
    assert client.get(f"/jobs/{draft}", headers=h).status_code == 404

    # an archived job deletes too
    client.post(f"/jobs/{jid}/archive", headers=h)
    assert client.delete(f"/jobs/{jid}", headers=h).status_code == 204
    assert client.get(f"/jobs/{jid}", headers=h).status_code == 404


def test_delete_job_candidate_removes_participation(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Analyst"}, headers=h).json()["id"]
    jc = client.post(f"/jobs/{jid}/candidates", json={"full_name": "Zed"}, headers=h).json()["id"]
    assert len(client.get(f"/jobs/{jid}/candidates", headers=h).json()) == 1
    assert client.delete(f"/job-candidates/{jc}", headers=h).status_code == 204
    assert client.get(f"/jobs/{jid}/candidates", headers=h).json() == []
    assert client.delete(f"/job-candidates/{jc}", headers=h).status_code == 404


def test_audit_log_endpoint(client):
    h = _auth(client)
    jid = client.post("/jobs", json={"title": "Audited Role"}, headers=h).json()["id"]
    client.post(f"/jobs/{jid}/archive", headers=h)
    resp = client.get("/dashboard/audit", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) >= {"items", "total", "page", "page_size"}
    actions = [r["action"] for r in body["items"]]
    assert "job.created" in actions and "job.archived" in actions
    created = next(r for r in body["items"] if r["action"] == "job.created")
    assert created["entity_type"] == "job" and created["actor_email"] == "recruiter@acme.test"


def test_audit_log_paginates_and_searches(client):
    h = _auth(client)
    for i in range(6):
        client.post("/jobs", json={"title": f"Role {i}"}, headers=h)
    page1 = client.get("/dashboard/audit?page=1&page_size=3", headers=h).json()
    assert len(page1["items"]) == 3 and page1["total"] >= 6 and page1["page"] == 1
    page2 = client.get("/dashboard/audit?page=2&page_size=3", headers=h).json()
    assert page1["items"][0]["id"] != page2["items"][0]["id"]
    # search narrows by action
    only_created = client.get("/dashboard/audit?q=job.created", headers=h).json()
    assert only_created["total"] >= 6 and all(r["action"] == "job.created" for r in only_created["items"])
    # search by actor email
    by_actor = client.get("/dashboard/audit?q=recruiter@acme.test", headers=h).json()
    assert by_actor["total"] >= 6


def test_assistant_chat_without_key_is_graceful(client):
    # conftest blanks platform_llm_api_key (hermetic) → the endpoint must not call Claude and
    # must return an actionable message rather than erroring.
    h = _auth(client)
    r = client.post("/assistant/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers=h)
    assert r.status_code == 200, r.text
    assert "key" in r.json()["reply"].lower()
    assert r.json()["links"] == []


def test_assistant_tools_jd_flow_hermetic(client):
    # Exercise the assistant tool dispatcher directly (no LLM) end-to-end: create → JD → confirm → draft.
    from app.api.deps import Principal
    from app.api.routers.assistant import _run_tool
    from app.modules.organizations.models import Organization, User

    _auth(client)  # bootstraps org "Acme" + recruiter, commits
    with Session(engine) as session:
        org = session.scalars(select(Organization)).first()
        user = session.scalars(select(User)).first()
        p = Principal(org_id=org.id, user_id=user.id, role="admin")
        links: list = []

        created = _run_tool("create_job", {"title": "FDE"}, session, p, links)
        assert created["created"] and created["status"] == "draft"
        jid = created["id"]

        added = _run_tool("add_job_description", {"job_id": jid, "jd_text": "Backend Engineer\nPython, FastAPI, PostgreSQL. 4+ years."}, session, p, links)
        assert added["added"] and added["extracted"]["role_family"] == "engineering"

        got = _run_tool("get_job", {"job_id": jid}, session, p, links)
        assert got["jd_added"] is True and got["jd_confirmed"] is False

        assert _run_tool("draft_workflow", {"job_id": jid}, session, p, links)["error"]  # not confirmed yet
        assert _run_tool("confirm_job_description", {"job_id": jid}, session, p, links)["confirmed"] is True
        drafted = _run_tool("draft_workflow", {"job_id": jid}, session, p, links)
        assert drafted["drafted"] and len(drafted["stages"]) >= 3

        # ownership guard: a random job id is rejected
        assert _run_tool("get_job", {"job_id": "00000000-0000-0000-0000-000000000000"}, session, p, links)["error"]
        session.rollback()
