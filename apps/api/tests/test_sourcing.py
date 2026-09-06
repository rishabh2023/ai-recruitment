"""Sourcing (People Search & Outreach — Flow B) API tests.

Covers: JD-derived suggested query, explicit sample-provider search + filtering, Auto PDL
search behavior, and adding selected candidates to the pipeline (including de-duplication).
Network-free: the sample provider is offline, and the Auto PDL adapter is monkeypatched so no
real HTTP is attempted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.integrations.people_search.base import ExternalCandidate, PeopleSearchResult
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE webhook_events RESTART IDENTITY CASCADE"))


def _auth(client):
    client.post("/dev/bootstrap", json={"org_name": "Acme", "user_email": "r@acme.test", "password": "pw-123456"})
    client.post("/auth/login", json={"email": "r@acme.test", "password": "pw-123456"})
    return {}


def _job_with_jd(client, h, title="Forward Deployed Engineer", jd=None):
    jid = client.post("/jobs", json={"title": title}, headers=h).json()["id"]
    jd = jd or "Forward Deployed Engineer\nBengaluru\nPython, FastAPI, AWS, LLM\n5+ years"
    ver = client.post(f"/jobs/{jid}/versions", json={"jd_text": jd}, headers=h).json()
    client.post(f"/jobs/{jid}/versions/{ver['id']}/confirm", headers=h)
    return jid


def test_suggested_query_from_jd(client):
    h = _auth(client)
    jid = _job_with_jd(client, h)
    r = client.get(f"/jobs/{jid}/sourcing/suggested-query", headers=h)
    assert r.status_code == 200, r.text
    q = r.json()
    # Title is derived from the JD; the deterministic stub extractor uses the first line.
    assert q["titles"], q
    assert q["page"] == 1


def test_sample_search_returns_and_filters(client):
    h = _auth(client)
    jid = _job_with_jd(client, h)
    # The default in tests is the offline sample provider (see conftest); it is explicit, not
    # a fallback. Broad search returns profiles flagged as sample.
    r = client.post(f"/jobs/{jid}/sourcing/search", json={"provider": "sample"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "sample" and body["is_sample"] is True
    assert len(body["candidates"]) > 0
    # Search never returns contact details (mirrors real providers — enrichment required).
    assert all(c["has_contact"] is False for c in body["candidates"])

    # Filtered search narrows results.
    r2 = client.post(f"/jobs/{jid}/sourcing/search", json={"provider": "sample", "titles": ["Account Executive"]}, headers=h)
    cands = r2.json()["candidates"]
    assert cands and all("account executive" in (c["title"] or "").lower() for c in cands)


def test_providers_list(client):
    h = _auth(client)
    jid = _job_with_jd(client, h)
    r = client.get(f"/jobs/{jid}/sourcing/providers", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    keys = {p["key"] for p in body["providers"]}
    assert {"apollo", "pdl", "proxycurl", "coresignal"} <= keys
    # No real keys in the test env → none configured, and no sample offered as a real provider.
    assert all(p["configured"] is False for p in body["providers"])
    assert "sample" not in keys


def test_search_unconfigured_provider_returns_502(client):
    """A real provider with no key surfaces an honest error — never fabricated data."""
    h = _auth(client)
    jid = _job_with_jd(client, h)
    r = client.post(f"/jobs/{jid}/sourcing/search", json={"provider": "apollo"}, headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "provider_unavailable"
    assert "not configured" in r.json()["error"]["message"].lower()


def test_auto_search_broadens_a_zero_result_from_pdl(client, monkeypatch):
    """Auto mode keeps the verified PDL provider and relaxes seniority after zero matches."""
    h = _auth(client)
    jid = _job_with_jd(client, h)
    queries = []

    class FakePdl:
        key = "pdl"

        def search(self, query):
            queries.append(query)
            if len(queries) == 1:
                return PeopleSearchResult([], total=0, page=query.page, has_more=False, provider="pdl")
            return PeopleSearchResult(
                [ExternalCandidate(source="pdl", source_id="person-1", full_name="Asha Rao")],
                total=1, page=query.page, has_more=False, provider="pdl",
            )

    monkeypatch.setattr("app.modules.sourcing.service.get_people_search_provider", lambda *_args, **_kwargs: FakePdl())
    monkeypatch.setattr(
        "app.modules.sourcing.service.SettingsService.provider_env",
        lambda _self, _org_id: {"PDL_API_KEY": "test-key"},
    )
    r = client.post(
        f"/jobs/{jid}/sourcing/search",
        json={"provider": "auto", "titles": ["Backend Engineer"], "seniorities": ["mid"]},
        headers=h,
    )

    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "pdl"
    assert r.json()["requested_provider"] == "auto"
    assert r.json()["candidates"][0]["full_name"] == "Asha Rao"
    assert "seniority" in (r.json()["notice"] or "").lower()
    assert r.json()["suggested_query"]["seniorities"] == ["mid"]
    assert r.json()["applied_query"]["seniorities"] == []
    assert len(queries) == 2
    assert queries[0].seniorities == ["mid"]
    assert queries[1].seniorities == []


def test_auto_search_requires_configured_pdl(client):
    h = _auth(client)
    jid = _job_with_jd(client, h)

    r = client.post(f"/jobs/{jid}/sourcing/search", json={"provider": "auto"}, headers=h)

    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "provider_unavailable"
    assert "people data labs" in r.json()["error"]["message"].lower()


def test_auto_search_explains_empty_result_without_relaxable_filters(client, monkeypatch):
    h = _auth(client)
    jid = _job_with_jd(client, h)
    calls = []

    class FakePdl:
        key = "pdl"

        def search(self, query):
            calls.append(query)
            return PeopleSearchResult([], total=0, page=query.page, has_more=False, provider="pdl")

    monkeypatch.setattr("app.modules.sourcing.service.get_people_search_provider", lambda *_args, **_kwargs: FakePdl())
    monkeypatch.setattr(
        "app.modules.sourcing.service.SettingsService.provider_env",
        lambda _self, _org_id: {"PDL_API_KEY": "test-key"},
    )
    r = client.post(f"/jobs/{jid}/sourcing/search", json={"provider": "auto"}, headers=h)

    assert r.status_code == 200, r.text
    assert len(calls) == 1
    assert "no matches found" in (r.json()["notice"] or "").lower()
    assert r.json()["applied_query"] == r.json()["suggested_query"]


def test_add_candidates_to_pipeline_and_dedup(client):
    h = _auth(client)
    jid = _job_with_jd(client, h)
    # Need an approved workflow so the sourced candidate gets a first stage.
    wf = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    client.post(f"/jobs/{jid}/workflow/versions/{wf['id']}/approve", headers=h)

    found = client.post(f"/jobs/{jid}/sourcing/search", json={}, headers=h).json()["candidates"][:2]
    payload = {"candidates": [
        {"source": c["source"], "source_id": c["source_id"], "full_name": c["full_name"],
         "title": c["title"], "company": c["company"], "location": c["location"],
         "linkedin_url": c["linkedin_url"]}
        for c in found
    ]}
    r = client.post(f"/jobs/{jid}/sourcing/add", json=payload, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["added"] == 2 and r.json()["skipped"] == 0

    # They appear in the job pipeline as SOURCED.
    listed = client.get(f"/jobs/{jid}/candidates", headers=h).json()
    assert len(listed) == 2
    assert all(item["pipeline_state"] == "SOURCED" for item in listed)

    # Re-adding the same profiles is idempotent (deduped by source+source_id).
    r2 = client.post(f"/jobs/{jid}/sourcing/add", json=payload, headers=h)
    assert r2.json()["added"] == 0 and r2.json()["skipped"] == 2
    assert len(client.get(f"/jobs/{jid}/candidates", headers=h).json()) == 2


def test_add_requires_selection(client):
    h = _auth(client)
    jid = _job_with_jd(client, h)
    assert client.post(f"/jobs/{jid}/sourcing/add", json={"candidates": []}, headers=h).status_code == 422


def test_archived_job_rejects_adding_sourced_candidates(client):
    h = _auth(client)
    jid = _job_with_ai_workflow(client, h)
    assert client.post(f"/jobs/{jid}/archive", headers=h).status_code == 200

    r = client.post(
        f"/jobs/{jid}/sourcing/add",
        json={"candidates": [{"source": "pdl", "source_id": "person-1", "full_name": "Asha Rao"}]},
        headers=h,
    )

    assert r.status_code == 409, r.text
    assert "inactive" in r.json()["error"]["message"].lower()


def _job_with_ai_workflow(client, h):
    """Job with a confirmed JD and an approved workflow whose first stage is AI (launchable)."""
    jid = _job_with_jd(client, h)
    wf = client.post(f"/jobs/{jid}/workflow/draft", headers=h).json()
    stages = {"stages": [
        {"name": "Outreach / Screening", "execution_type": "ai", "information_requirements": ["interest"], "criteria": []},
        {"name": "Recruiter Review", "execution_type": "human", "requires_human_approval": True},
    ]}
    client.put(f"/jobs/{jid}/workflow/versions/{wf['id']}/stages", json=stages, headers=h)
    client.post(f"/jobs/{jid}/workflow/versions/{wf['id']}/approve", headers=h)
    assert client.post(f"/jobs/{jid}/activate", headers=h).status_code == 200
    return jid


def _source_one(client, h, jid):
    found = client.post(f"/jobs/{jid}/sourcing/search", json={}, headers=h).json()["candidates"][0]
    client.post(f"/jobs/{jid}/sourcing/add", json={"candidates": [found]}, headers=h)
    return client.get(f"/jobs/{jid}/candidates", headers=h).json()[0]["id"]


def test_archived_job_rejects_launching_an_outreach_call(client):
    h = _auth(client)
    jid = _job_with_ai_workflow(client, h)
    jc_id = _source_one(client, h, jid)
    assert client.post(f"/job-candidates/{jc_id}/enrich", headers=h).status_code == 201
    assert client.post(f"/jobs/{jid}/archive", headers=h).status_code == 200

    r = client.post(f"/job-candidates/{jc_id}/launch", headers=h)

    assert r.status_code == 409, r.text
    assert "inactive" in r.json()["error"]["message"].lower()


def test_enrich_sample_then_outreach(client):
    h = _auth(client)
    jid = _job_with_ai_workflow(client, h)
    jc_id = _source_one(client, h, jid)

    # Sourced candidate has no phone yet.
    tl = client.get(f"/job-candidates/{jc_id}/timeline", headers=h).json()
    assert tl["candidate"]["phone"] is None

    # Enrich reveals a (sample) contact and moves the candidate to OUTREACH_PENDING.
    r = client.post(f"/job-candidates/{jc_id}/enrich", headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phone"] and body["is_sample"] is True
    assert body["already_had_contact"] is False
    assert body["pipeline_state"] == "OUTREACH_PENDING"

    # Idempotent: enriching again reports the existing contact.
    again = client.post(f"/job-candidates/{jc_id}/enrich", headers=h).json()
    assert again["already_had_contact"] is True and again["phone"] == body["phone"]

    # Outreach: launching the AI stage now succeeds and marks the candidate CONTACTED.
    launch = client.post(f"/job-candidates/{jc_id}/launch", headers=h)
    assert launch.status_code == 201, launch.text
    state = client.get(f"/jobs/{jid}/candidates", headers=h).json()[0]["pipeline_state"]
    assert state == "CONTACTED"


def test_enrich_unconfigured_provider_returns_502(client):
    """A candidate sourced from a real provider (apollo) with no key surfaces an honest error
    on enrich — the platform never fabricates a contact number."""
    h = _auth(client)
    jid = _job_with_ai_workflow(client, h)
    client.post(
        f"/jobs/{jid}/sourcing/add",
        json={"candidates": [{"source": "apollo", "source_id": "apollo-xyz", "full_name": "Real Person"}]},
        headers=h,
    )
    jc_id = client.get(f"/jobs/{jid}/candidates", headers=h).json()[0]["id"]
    r = client.post(f"/job-candidates/{jc_id}/enrich", headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "provider_unavailable"
