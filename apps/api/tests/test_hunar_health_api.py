"""Hunar health + re-key API tests (network-free: the Hunar probe is monkeypatched)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.integrations.hunar import keystore
from app.integrations.hunar.client import HunarError
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE app_config RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE webhook_events RESTART IDENTITY CASCADE"))


class _FakeClient:
    def __init__(self, *, raise_exc=None):
        self._raise = raise_exc

    def list_numbers(self):
        if self._raise is not None:
            raise self._raise
        return {"results": []}


def _signup_admin(client, email="admin@acme.test"):
    r = client.post("/auth/signup", json={"name": "Admin", "email": email, "password": "pw-123456", "org_name": "Acme"})
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    monkeypatch.setattr(keystore, "cache_get", lambda k: None)
    monkeypatch.setattr(keystore, "cache_set", lambda k, v, ttl: None)
    monkeypatch.setattr(keystore, "cache_delete", lambda k: None)


def test_health_requires_auth(client):
    assert client.get("/hunar/health").status_code == 401


def test_health_unconfigured_by_default(client, monkeypatch):
    _signup_admin(client)
    # conftest already blanks hunar_api_key -> unconfigured, no probe.
    r = client.get("/hunar/health")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "unconfigured"


def test_health_healthy_with_env_key(client, monkeypatch):
    from app.config import settings as app_settings

    _signup_admin(client)
    monkeypatch.setattr(app_settings, "hunar_api_key", "env-key", raising=False)
    monkeypatch.setattr(keystore, "build_client", lambda api_key: _FakeClient())
    r = client.get("/hunar/health?refresh=1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "healthy"
    assert body["source"] == "env"
