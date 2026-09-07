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
