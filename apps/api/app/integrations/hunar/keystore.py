"""Hunar key resolution, durable override, and health probe.

Key resolution order: DB override (`app_config.hunar_api_key`) → process `.env`
(`settings.hunar_api_key`). The override is durable (survives Redis flushes); only the health
result is cached in Redis. The raw key is never returned to clients.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.modules.audit.log import write_audit
from app.modules.organizations.models import AppConfig

from .client import HunarClient, HunarConfig

HUNAR_KEY_CONFIG = "hunar_api_key"


def build_client(api_key: str) -> HunarClient:
    """Factory so tests can monkeypatch the outbound Hunar call in one place."""
    return HunarClient(HunarConfig(api_key=api_key, base_url=app_settings.hunar_api_base_url))


def resolve_api_key(session: Session) -> tuple[str, str | None]:
    row = session.get(AppConfig, HUNAR_KEY_CONFIG)
    if row and (row.value or "").strip():
        return row.value, "override"
    env = (app_settings.hunar_api_key or "").strip()
    if env:
        return env, "env"
    return "", None


def set_override(session: Session, api_key: str, *, actor_user_id: UUID | None) -> None:
    row = session.get(AppConfig, HUNAR_KEY_CONFIG)
    if row is None:
        row = AppConfig(key=HUNAR_KEY_CONFIG, value=api_key, updated_by=actor_user_id)
        session.add(row)
    else:
        row.value = api_key
        row.updated_by = actor_user_id
    session.flush()


def clear_override(session: Session, *, actor_user_id: UUID | None) -> None:
    row = session.get(AppConfig, HUNAR_KEY_CONFIG)
    if row is not None:
        session.delete(row)
        session.flush()
