"""Global app_config store + Hunar key resolution/health (network-free)."""
from __future__ import annotations

from app.modules.organizations.models import AppConfig


def test_app_config_row_roundtrips(session):
    session.add(AppConfig(key="hunar_api_key", value="k-live-123"))
    session.flush()
    row = session.get(AppConfig, "hunar_api_key")
    assert row is not None
    assert row.value == "k-live-123"
