"""Paginated/filterable pipeline endpoint: bounded pages, stage filter, and search."""

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


def _job(client):
    client.post("/dev/bootstrap", json={"org_name": "Acme", "user_email": "r@acme.test", "password": "pw-123456"})
    client.post("/auth/login", json={"email": "r@acme.test", "password": "pw-123456"})
    return client.post("/jobs", json={"title": "Backend Engineer"}).json()["id"]


def _add(client, jid, name, phone):
    client.post(f"/jobs/{jid}/candidates", json={"full_name": name, "phone": phone})


def test_pipeline_paginates(client):
    jid = _job(client)
    for i in range(30):
        _add(client, jid, f"Cand {i:02d}", f"+9190000000{i:02d}")
    r = client.get(f"/jobs/{jid}/pipeline?page=1&page_size=25")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 30
    assert len(body["items"]) == 25
    assert body["page"] == 1
    r2 = client.get(f"/jobs/{jid}/pipeline?page=2&page_size=25")
    assert len(r2.json()["items"]) == 5


def test_pipeline_search_filters(client):
    jid = _job(client)
    _add(client, jid, "Asha Rao", "+919811111111")
    _add(client, jid, "Bo Li", "+919822222222")
    r = client.get(f"/jobs/{jid}/pipeline?q=asha")
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["candidate"]["full_name"] == "Asha Rao"
    # search matches phone too
    assert client.get(f"/jobs/{jid}/pipeline?q=982222").json()["total"] == 1


def test_pipeline_page_size_is_capped(client):
    jid = _job(client)
    _add(client, jid, "Solo", "+919800000000")
    r = client.get(f"/jobs/{jid}/pipeline?page_size=10000")
    assert r.json()["page_size"] == 100
