"""Tiny Redis accessor for ephemeral caches (currently the Hunar health probe result).

Redis is disposable coordination, never a source of truth. Every helper swallows connection
errors: a read becomes a cache miss and a write becomes a no-op, so a Redis outage degrades to
recomputing rather than failing a request.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=1)
def _client():
    import redis  # imported lazily so a missing/broken Redis never breaks import

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def cache_get(key: str) -> str | None:
    try:
        return _client().get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    try:
        _client().set(key, value, ex=ttl_seconds)
    except Exception:
        pass


def cache_delete(key: str) -> None:
    try:
        _client().delete(key)
    except Exception:
        pass
