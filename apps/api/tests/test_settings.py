"""Settings API tests — org-scoped provider config + admin gate.

Network-free: only settings mutations/reads are exercised (no people-search HTTP).
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


def _signup_admin(client, email="admin@acme.test"):
    r = client.post("/auth/signup", json={"name": "Admin", "email": email, "password": "pw-123456", "org_name": "Acme"})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_settings_read_defaults(client):
    _signup_admin(client)
    r = client.get("/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_admin"] is True
    assert body["org_name"] == "Acme"
    assert {p["key"] for p in body["providers"]} >= {"apollo", "pdl", "proxycurl", "coresignal"}
    assert all(p["configured"] is False for p in body["providers"])  # no keys in test env
    assert any(u["role"] == "admin" for u in body["users"])


def test_admin_sets_provider_key_and_default(client):
    _signup_admin(client)
    r = client.put("/settings", json={"default_provider": "pdl", "provider_keys": {"pdl": "pdl-test-key"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_provider"] == "pdl"
    pdl = next(p for p in body["providers"] if p["key"] == "pdl")
    assert pdl["configured"] is True
    # The raw key is never returned anywhere in the payload.
    assert "pdl-test-key" not in r.text

    # Clearing the key un-configures the provider.
    r2 = client.put("/settings", json={"provider_keys": {"pdl": ""}})
    pdl2 = next(p for p in r2.json()["providers"] if p["key"] == "pdl")
    assert pdl2["configured"] is False


def test_live_calls_toggle(client):
    _signup_admin(client)
    r = client.put("/settings", json={"live_calls_enabled": True})
    assert r.json()["live_calls_enabled"] is True


def test_non_admin_cannot_update(client):
    # dev bootstrap creates a recruiter (non-admin).
    client.post("/dev/bootstrap", json={"org_name": "Bee", "user_email": "rec@bee.test", "password": "pw-123456"})
    client.post("/auth/login", json={"email": "rec@bee.test", "password": "pw-123456"})
    r = client.put("/settings", json={"live_calls_enabled": True})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    # ...but reading is allowed.
    assert client.get("/settings").json()["is_admin"] is False


def test_org_provider_key_makes_sourcing_configured(client):
    """A key saved in Settings makes that provider usable for sourcing (org-scoped)."""
    _signup_admin(client)
    jid = client.post("/jobs", json={"title": "FDE"}).json()["id"]
    # Before: nothing configured.
    assert all(p["configured"] is False for p in client.get(f"/jobs/{jid}/sourcing/providers").json()["providers"])
    # Save an Apollo key in Settings.
    client.put("/settings", json={"default_provider": "apollo", "provider_keys": {"apollo": "sk-test"}})
    prov = client.get(f"/jobs/{jid}/sourcing/providers").json()
    apollo = next(p for p in prov["providers"] if p["key"] == "apollo")
    assert apollo["configured"] is True and prov["default"] == "apollo"


def test_invite_create_list_revoke_and_accept(client):
    _signup_admin(client, email="boss@acme.test")
    # Create an invite.
    r = client.post("/settings/invites", json={"email": "New Hire@Acme.test", "role": "recruiter", "name": "New Hire"})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["email"] == "new hire@acme.test"  # normalized
    assert "accept-invite?token=" in inv["accept_url"]
    token = inv["accept_url"].split("token=")[1]

    # It shows up as pending in settings.
    assert any(i["email"] == "new hire@acme.test" for i in client.get("/settings").json()["invites"])

    # Preview (public) works.
    prev = client.get(f"/auth/invite?token={token}")
    assert prev.status_code == 200 and prev.json()["role"] == "recruiter"

    # Accept in a separate client (no admin cookie) → becomes a logged-in recruiter.
    with TestClient(app) as c2:
        acc = c2.post("/auth/accept-invite", json={"token": token, "password": "newpass1"})
        assert acc.status_code == 201, acc.text
        assert acc.json()["role"] == "recruiter" and acc.json()["email"] == "new hire@acme.test"
        assert c2.get("/auth/me").json()["email"] == "new hire@acme.test"

    # Used token can't be reused, and the invite is no longer pending.
    assert client.get(f"/auth/invite?token={token}").status_code == 404
    assert not any(i["email"] == "new hire@acme.test" for i in client.get("/settings").json()["invites"])
    # The new user appears on the team.
    assert any(u["email"] == "new hire@acme.test" and u["role"] == "recruiter" for u in client.get("/settings").json()["users"])


def test_invite_admin_only_and_validation(client):
    # non-admin cannot invite
    client.post("/dev/bootstrap", json={"org_name": "Cee", "user_email": "rec@cee.test", "password": "pw-123456"})
    client.post("/auth/login", json={"email": "rec@cee.test", "password": "pw-123456"})
    assert client.post("/settings/invites", json={"email": "x@cee.test"}).status_code == 403

    # admin: inviting an existing email is rejected
    _signup_admin(client, email="own@dee.test")
    assert client.post("/settings/invites", json={"email": "own@dee.test"}).status_code == 422
    # bad role rejected
    assert client.post("/settings/invites", json={"email": "z@dee.test", "role": "wizard"}).status_code == 422


def test_accept_invalid_token(client):
    with TestClient(app) as c2:
        assert c2.post("/auth/accept-invite", json={"token": "nope", "password": "secret1"}).status_code == 422
