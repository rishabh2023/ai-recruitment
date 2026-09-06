"""Auth: password hashing (pure) + session service (DB) + login/logout/me (HTTP)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app
from app.modules.organizations.auth import (
    authenticate,
    create_session,
    resolve_session,
    revoke_session,
)
from app.modules.organizations.models import Organization, User
from app.security.passwords import hash_password, verify_password


# --- pure: password hashing (no DB) ---
def test_password_roundtrip():
    encoded = hash_password("correct horse")
    assert verify_password("correct horse", encoded) is True
    assert verify_password("wrong", encoded) is False


def test_password_salted_differently_each_time():
    assert hash_password("same") != hash_password("same")


def test_verify_handles_missing_or_malformed():
    assert verify_password("x", None) is False
    assert verify_password("x", "") is False
    assert verify_password("x", "not-a-valid-hash") is False


def test_hash_rejects_empty_password():
    with pytest.raises(ValueError):
        hash_password("")


# --- DB-backed: session service ---
def _make_user(session, *, password="pw-123456", email="u@test.dev"):
    org = Organization(name="Org")
    session.add(org)
    session.flush()
    user = User(org_id=org.id, email=email, role="recruiter", password_hash=hash_password(password))
    session.add(user)
    session.flush()
    return user


def test_authenticate_success_and_failure(session):
    user = _make_user(session)
    assert authenticate(session, email="u@test.dev", password="pw-123456").id == user.id
    assert authenticate(session, email="U@TEST.DEV", password="pw-123456").id == user.id  # case-insensitive
    assert authenticate(session, email="u@test.dev", password="nope") is None
    assert authenticate(session, email="missing@test.dev", password="pw-123456") is None


def test_authenticate_rejects_user_without_password(session):
    org = Organization(name="Org")
    session.add(org)
    session.flush()
    user = User(org_id=org.id, email="np@test.dev", role="recruiter")  # no password_hash
    session.add(user)
    session.flush()
    assert authenticate(session, email="np@test.dev", password="anything") is None


def test_session_create_resolve_revoke(session):
    user = _make_user(session)
    token = create_session(session, user=user)
    authed = resolve_session(session, token)
    assert authed is not None
    assert authed.user_id == user.id and authed.org_id == user.org_id and authed.role == "recruiter"

    revoke_session(session, token)
    assert resolve_session(session, token) is None


def test_resolve_rejects_expired_and_unknown(session):
    user = _make_user(session)
    expired = create_session(session, user=user, ttl=timedelta(seconds=-1))
    assert resolve_session(session, expired) is None
    assert resolve_session(session, "totally-bogus-token") is None
    assert resolve_session(session, None) is None


# --- HTTP: login / me / logout ---
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))


def _bootstrap(client):
    r = client.post(
        "/dev/bootstrap",
        json={"org_name": "Acme", "user_email": "rec@acme.test", "password": "pw-123456"},
    )
    assert r.status_code == 201, r.text


def test_login_sets_cookie_and_me_works(client):
    _bootstrap(client)
    r = client.post("/auth/login", json={"email": "rec@acme.test", "password": "pw-123456"})
    assert r.status_code == 200, r.text
    assert "session" in r.cookies
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "recruiter"


def test_login_wrong_password_401(client):
    _bootstrap(client)
    r = client.post("/auth/login", json={"email": "rec@acme.test", "password": "WRONG"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401


def test_logout_revokes_session(client):
    _bootstrap(client)
    client.post("/auth/login", json={"email": "rec@acme.test", "password": "pw-123456"})
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout").status_code == 204
    # Cookie cleared client-side AND session revoked server-side.
    assert client.get("/auth/me").status_code == 401
