"""Global app_config store + Hunar key resolution/health (network-free)."""
from __future__ import annotations

from app.modules.organizations.models import AppConfig


def test_app_config_row_roundtrips(session):
    session.add(AppConfig(key="hunar_api_key", value="k-live-123"))
    session.flush()
    row = session.get(AppConfig, "hunar_api_key")
    assert row is not None
    assert row.value == "k-live-123"


def test_cache_get_returns_none_when_redis_unavailable(monkeypatch):
    from app import redis_client

    def boom():
        raise RuntimeError("no redis")

    monkeypatch.setattr(redis_client, "_client", boom)
    # Must not raise even though Redis is unreachable.
    assert redis_client.cache_get("hunar:health") is None
    redis_client.cache_set("hunar:health", "x", 60)  # no-op, no raise
    redis_client.cache_delete("hunar:health")  # no-op, no raise


def test_resolve_prefers_override_then_env(session, monkeypatch):
    from app.config import settings as app_settings
    from app.integrations.hunar import keystore
    from app.modules.organizations.models import AppConfig

    # No override, env set -> env.
    monkeypatch.setattr(app_settings, "hunar_api_key", "env-key", raising=False)
    assert keystore.resolve_api_key(session) == ("env-key", "env")

    # No override, no env -> empty/None.
    monkeypatch.setattr(app_settings, "hunar_api_key", "", raising=False)
    assert keystore.resolve_api_key(session) == ("", None)

    # Override present -> override wins over env.
    session.add(AppConfig(key=keystore.HUNAR_KEY_CONFIG, value="override-key"))
    session.flush()
    monkeypatch.setattr(app_settings, "hunar_api_key", "env-key", raising=False)
    assert keystore.resolve_api_key(session) == ("override-key", "override")


import json

import pytest

from app.integrations.hunar.client import HunarError


class _FakeClient:
    def __init__(self, *, raise_exc=None):
        self._raise = raise_exc

    def list_numbers(self):
        if self._raise is not None:
            raise self._raise
        return {"results": []}


@pytest.fixture
def _no_cache(monkeypatch):
    """Disable Redis caching so each check_health call probes freshly."""
    from app.integrations.hunar import keystore

    monkeypatch.setattr(keystore, "cache_get", lambda k: None)
    monkeypatch.setattr(keystore, "cache_set", lambda k, v, ttl: None)


def _use_key(monkeypatch, key="k"):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "hunar_api_key", key, raising=False)


def test_health_healthy(session, monkeypatch, _no_cache):
    from app.integrations.hunar import keystore

    _use_key(monkeypatch)
    monkeypatch.setattr(keystore, "build_client", lambda api_key: _FakeClient())
    out = keystore.check_health(session, refresh=True)
    assert out["status"] == "healthy"
    assert out["source"] == "env"


def test_health_invalid_on_401(session, monkeypatch, _no_cache):
    from app.integrations.hunar import keystore

    _use_key(monkeypatch)
    monkeypatch.setattr(keystore, "build_client",
                        lambda api_key: _FakeClient(raise_exc=HunarError("no", status_code=401)))
    assert keystore.check_health(session, refresh=True)["status"] == "invalid"


def test_health_unreachable_on_transport_error(session, monkeypatch, _no_cache):
    from app.integrations.hunar import keystore

    _use_key(monkeypatch)
    monkeypatch.setattr(keystore, "build_client",
                        lambda api_key: _FakeClient(raise_exc=HunarError("timeout")))
    assert keystore.check_health(session, refresh=True)["status"] == "unreachable"


def test_health_unconfigured_when_no_key(session, monkeypatch, _no_cache):
    from app.config import settings as app_settings
    from app.integrations.hunar import keystore

    monkeypatch.setattr(app_settings, "hunar_api_key", "", raising=False)
    called = {"n": 0}
    monkeypatch.setattr(keystore, "build_client",
                        lambda api_key: called.__setitem__("n", called["n"] + 1) or _FakeClient())
    assert keystore.check_health(session, refresh=True)["status"] == "unconfigured"
    assert called["n"] == 0  # never probes when there is no key


def test_health_uses_cache(session, monkeypatch):
    from app.integrations.hunar import keystore

    _use_key(monkeypatch)
    cached = json.dumps({"status": "healthy", "source": "env", "checked_at": "2026-09-07T00:00:00Z"})
    monkeypatch.setattr(keystore, "cache_get", lambda k: cached)

    def _boom(api_key):
        raise AssertionError("should not probe when cache hits")

    monkeypatch.setattr(keystore, "build_client", _boom)
    assert keystore.check_health(session)["status"] == "healthy"  # no refresh -> served from cache
