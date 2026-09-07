"""Hunar key resolution, durable override, and health probe.

Key resolution order: DB override (`app_config.hunar_api_key`) → process `.env`
(`settings.hunar_api_key`). The override is durable (survives Redis flushes); only the health
result is cached in Redis. The raw key is never returned to clients.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.modules.organizations.models import AppConfig
from app.redis_client import cache_delete, cache_get, cache_set

from .client import HunarClient, HunarConfig, HunarError

HUNAR_KEY_CONFIG = "hunar_api_key"
HEALTH_CACHE_KEY = "hunar:health"
HEALTH_TTL_SECONDS = 60


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


def check_health(session: Session, *, refresh: bool = False) -> dict:
    """Return the Hunar health result, served from Redis unless ``refresh``.

    Probes the lightweight verified read ``GET /numbers/``. 401/403 means the key is
    invalid/expired (re-key needed); other errors mean the provider is unreachable (transient).
    """
    if not refresh:
        cached = cache_get(HEALTH_CACHE_KEY)
        if cached:
            try:
                return json.loads(cached)
            except ValueError:
                pass

    api_key, source = resolve_api_key(session)
    if not api_key:
        status = "unconfigured"
    else:
        try:
            build_client(api_key).list_numbers()
            status = "healthy"
        except HunarError as exc:
            status = "invalid" if exc.status_code in (401, 403) else "unreachable"

    result = {
        "status": status,
        "source": source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    # Only cache stable outcomes; unreachable is transient, so let it re-probe next time.
    if status != "unreachable":
        cache_set(HEALTH_CACHE_KEY, json.dumps(result), HEALTH_TTL_SECONDS)
    return result
