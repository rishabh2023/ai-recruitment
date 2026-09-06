"""Sourcing (People Search & Outreach — Flow B) API tests.

Covers: JD-derived suggested query, sample-provider search + filtering, apollo requested but
plan-gated → sample fallback flagged, and adding selected candidates to the pipeline
(including de-duplication). Network-free: the sample provider is offline; the apollo path is
forced to fail via a monkeypatched registry so no real HTTP is attempted.
"""

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
    # Broad search returns sample profiles, clearly flagged as sample.
    r = client.post(f"/jobs/{jid}/sourcing/search", json={}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "sample" and body["is_sample"] is True
    assert body["notice"]
    assert len(body["candidates"]) > 0
    # Search never returns contact details (mirrors real providers — enrichment required).
    assert all(c["has_contact"] is False for c in body["candidates"])

    # Filtered search narrows results.
    r2 = client.post(f"/jobs/{jid}/sourcing/search", json={"titles": ["Account Executive"]}, headers=h)
    cands = r2.json()["candidates"]
    assert cands and all("account executive" in (c["title"] or "").lower() for c in cands)


def test_apollo_requested_falls_back_to_sample(client, monkeypatch):
    h = _auth(client)
    jid = _job_with_jd(client, h)

    # Force the configured provider to apollo and make provider construction fail (plan gate).
    from app.api.routers import sourcing as sourcing_router

    monkeypatch.setattr(sourcing_router.settings, "people_search_provider", "apollo")

    def _boom(*_a, **_k):
        raise RuntimeError("Apollo /mixed_people/api_search HTTP 403: not on your plan")

    monkeypatch.setattr("app.modules.sourcing.service.get_people_search_provider", _boom)

    r = client.post(f"/jobs/{jid}/sourcing/search", json={}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requested_provider"] == "apollo"
    assert body["provider"] == "sample" and body["is_sample"] is True
    assert "403" in body["notice"] or "not available" in body["notice"].lower()


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
