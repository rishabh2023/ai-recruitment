# Hunar Key Health Check & Re-Key Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a global "Voice AI" health signal on every authenticated screen and let an admin paste a new live Hunar key (validated before saving, stored durably in the DB) so an expired key can be recovered without a redeploy.

**Architecture:** The Hunar API key resolves **DB override → `.env`**. The override lives in a new global single-row `app_config` table (durable). Health is computed by a lightweight `GET /numbers/` probe and cached ~60s in Redis (disposable; degrades to a live recompute if Redis is down). Two new endpoints (`GET /hunar/health`, `PUT /hunar/key`) back a sidebar badge + admin re-key modal in the Next.js shell.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Postgres + Redis (`redis` package) on the API; Next.js + React + TypeScript on the web app; `httpx` for the Hunar call; `pytest` + `TestClient` for tests.

## Global Constraints

- Secrets are server-side only. The Hunar key is **never** returned to any client; the API exposes only status/source. No `NEXT_PUBLIC_*` secret.
- Thin Hunar adapter — only the VERIFIED `GET /numbers/` endpoint is used as the probe (see `docs/vendor-capability-matrix.md`). Never invent vendor behavior.
- Scope is **global**, not per-org. One Hunar account → one key.
- Frontend uses product language only: "Voice AI" — never "Hunar", agent IDs, prompts, queues, or telephony.
- Admin gate: mutating the key requires `role == "admin"` (mirror `_require_admin` in `app/api/routers/settings.py`). Reading health is allowed for any authenticated user.
- Distinguish an **invalid/expired key** (HTTP 401/403 → re-key needed) from an **unreachable provider** (transport/timeout/5xx → transient, do NOT demand a re-key).
- Every consequential mutation writes an audit event via `app.modules.audit.log.write_audit` and never logs the key value.
- Tests are hermetic: the Hunar HTTP call is always mocked; nothing dials a real number. `conftest.py` already blanks `hunar_api_key`/live-calls per test.
- Current Alembic head is `e7c1d2f3a4b5`; the new migration's `down_revision` is `e7c1d2f3a4b5`.

---

## File Structure

**Backend (`apps/api`):**
- Create `app/redis_client.py` — tiny lazy Redis accessor + safe get/set/delete for the health cache. Never raises on Redis outage.
- Modify `app/modules/organizations/models.py` — add global `AppConfig` key/value model. (Placed in the organizations module to reuse its migrations/version_locations; it is a global table, no `org_id`.)
- Create `app/modules/organizations/migrations/<rev>_app_config.py` — creates `app_config`.
- Create `app/integrations/hunar/keystore.py` — key resolution (DB override → env), set/clear override, and `check_health` (probe + Redis cache). Exposes an injectable `build_client(api_key)` for tests.
- Modify `app/api/schemas.py` — add `HunarHealthOut`, `HunarKeyUpdateIn`.
- Create `app/api/routers/hunar.py` — `GET /hunar/health`, `PUT /hunar/key`.
- Modify `app/main.py` — register the hunar router.
- Tests: `tests/test_hunar_keystore.py`, `tests/test_hunar_health_api.py`.

**Frontend (`apps/web`):**
- Modify `lib/api.ts` — `HunarHealth` type + `getHunarHealth`, `updateHunarKey`.
- Create `components/HunarHealthBadge.tsx` — badge (fetch + poll + states) and the re-key modal.
- Modify `components/AppShell.tsx` — render the badge in the sidebar footer.
- Modify `app/globals.css` — badge + modal styling (follow existing class conventions).

---

## Task 1: Global `AppConfig` table (durable key store)

**Files:**
- Modify: `apps/api/app/modules/organizations/models.py`
- Create: `apps/api/app/modules/organizations/migrations/f8a1c2d3e4b5_app_config.py`
- Test: `apps/api/tests/test_hunar_keystore.py`

**Interfaces:**
- Produces: SQLAlchemy model `AppConfig` with columns `key: str` (PK), `value: str | None`, `updated_at`, `updated_by: UUID | None`. Table name `app_config`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_hunar_keystore.py`:

```python
"""Global app_config store + Hunar key resolution/health (network-free)."""
from __future__ import annotations

from app.modules.organizations.models import AppConfig


def test_app_config_row_roundtrips(session):
    session.add(AppConfig(key="hunar_api_key", value="k-live-123"))
    session.flush()
    row = session.get(AppConfig, "hunar_api_key")
    assert row is not None
    assert row.value == "k-live-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py::test_app_config_row_roundtrips -v`
Expected: FAIL with `ImportError: cannot import name 'AppConfig'`.

- [ ] **Step 3: Add the model**

Append to `apps/api/app/modules/organizations/models.py` (imports `Column`, `Text`, `UUID`, `updated_at` are already present at the top of the file):

```python
class AppConfig(Base):
    """Global (non-org-scoped) key/value configuration.

    A single durable store for platform-wide settings that are not per-organization. First
    use: the Hunar voice-AI API key override (`key='hunar_api_key'`), which takes precedence
    over the `.env` key so an admin can rotate it in-app without a redeploy. `value` may hold a
    secret and is NEVER returned to clients.
    """

    __tablename__ = "app_config"

    key = Column(Text, primary_key=True)
    value = Column(Text)
    updated_at = updated_at()
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
```

- [ ] **Step 4: Create the migration**

Create `apps/api/app/modules/organizations/migrations/f8a1c2d3e4b5_app_config.py`:

```python
"""app_config global key/value store

Revision ID: f8a1c2d3e4b5
Revises: e7c1d2f3a4b5
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f8a1c2d3e4b5"
down_revision: Union[str, None] = "e7c1d2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_app_config_updated_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_config")),
    )


def downgrade() -> None:
    op.drop_table("app_config")
```

- [ ] **Step 5: Apply the migration to the test DB and run the test**

Run: `cd apps/api && DATABASE_URL="postgresql://recruitment:recruitment@localhost:5432/recruitment_test" alembic upgrade head && pytest tests/test_hunar_keystore.py::test_app_config_row_roundtrips -v`
Expected: PASS. (If Postgres is unreachable the DB test skips — that is acceptable per conftest.)

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/modules/organizations/models.py apps/api/app/modules/organizations/migrations/f8a1c2d3e4b5_app_config.py apps/api/tests/test_hunar_keystore.py
git commit -m "feat(api): global app_config table for durable Hunar key override

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Redis health-cache helper (degrades gracefully)

**Files:**
- Create: `apps/api/app/redis_client.py`
- Test: `apps/api/tests/test_hunar_keystore.py` (append)

**Interfaces:**
- Produces: `cache_get(key: str) -> str | None`, `cache_set(key: str, value: str, ttl_seconds: int) -> None`, `cache_delete(key: str) -> None`. All swallow Redis errors: `cache_get` returns `None` on any failure; `cache_set`/`cache_delete` are no-ops on failure.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_hunar_keystore.py`:

```python
def test_cache_get_returns_none_when_redis_unavailable(monkeypatch):
    from app import redis_client

    def boom():
        raise RuntimeError("no redis")

    monkeypatch.setattr(redis_client, "_client", boom)
    # Must not raise even though Redis is unreachable.
    assert redis_client.cache_get("hunar:health") is None
    redis_client.cache_set("hunar:health", "x", 60)  # no-op, no raise
    redis_client.cache_delete("hunar:health")  # no-op, no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py::test_cache_get_returns_none_when_redis_unavailable -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.redis_client'`.

- [ ] **Step 3: Implement the helper**

Create `apps/api/app/redis_client.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py::test_cache_get_returns_none_when_redis_unavailable -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/redis_client.py apps/api/tests/test_hunar_keystore.py
git commit -m "feat(api): graceful Redis cache helper for ephemeral state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Hunar keystore — key resolution (DB override → env)

**Files:**
- Create: `apps/api/app/integrations/hunar/keystore.py`
- Test: `apps/api/tests/test_hunar_keystore.py` (append)

**Interfaces:**
- Consumes: `AppConfig` (Task 1), `HunarClient`/`HunarConfig`/`HunarError` from `app/integrations/hunar/client.py`.
- Produces:
  - `HUNAR_KEY_CONFIG = "hunar_api_key"` (the `app_config.key`).
  - `resolve_api_key(session) -> tuple[str, str | None]` → `(api_key, source)` where `source ∈ {"override", "env", None}`; `api_key` is `""` when neither is set.
  - `set_override(session, api_key: str, *, actor_user_id) -> None` and `clear_override(session, *, actor_user_id) -> None`.
  - `build_client(api_key: str) -> HunarClient` — module-level factory (monkeypatched in tests).

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_hunar_keystore.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py::test_resolve_prefers_override_then_env -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.hunar.keystore'`.

- [ ] **Step 3: Implement resolution + override writers + client factory**

Create `apps/api/app/integrations/hunar/keystore.py` (health added in Task 4):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py::test_resolve_prefers_override_then_env -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/integrations/hunar/keystore.py apps/api/tests/test_hunar_keystore.py
git commit -m "feat(api): resolve Hunar key DB-override-then-env with durable writers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Hunar health probe + Redis caching

**Files:**
- Modify: `apps/api/app/integrations/hunar/keystore.py`
- Test: `apps/api/tests/test_hunar_keystore.py` (append)

**Interfaces:**
- Consumes: `resolve_api_key`, `build_client` (Task 3); `cache_get`/`cache_set` (Task 2); `HunarError` from `client.py`.
- Produces: `check_health(session, *, refresh: bool = False) -> dict` returning `{"status": str, "source": str | None, "checked_at": str}` where `status ∈ {"healthy", "invalid", "unconfigured", "unreachable"}`. Also `HEALTH_CACHE_KEY = "hunar:health"` and `HEALTH_TTL_SECONDS = 60`.
- Status mapping: no key → `unconfigured` (no probe); probe 2xx → `healthy`; `HunarError` with `status_code in (401, 403)` → `invalid`; any other `HunarError` (transport/timeout/5xx) → `unreachable`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_hunar_keystore.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py -k health -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'check_health'`.

- [ ] **Step 3: Implement `check_health` + cache wiring**

Edit `apps/api/app/integrations/hunar/keystore.py`. Add these imports near the top (after the existing imports):

```python
import json
from datetime import datetime, timezone

from app.redis_client import cache_get, cache_set
from .client import HunarError
```

Add these constants under `HUNAR_KEY_CONFIG = "hunar_api_key"`:

```python
HEALTH_CACHE_KEY = "hunar:health"
HEALTH_TTL_SECONDS = 60
```

Append the function:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py -k health -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/integrations/hunar/keystore.py apps/api/tests/test_hunar_keystore.py
git commit -m "feat(api): Hunar health probe with Redis caching and 401/403 vs unreachable split

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `GET /hunar/health` endpoint + schemas

**Files:**
- Modify: `apps/api/app/api/schemas.py`
- Create: `apps/api/app/api/routers/hunar.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_hunar_health_api.py`

**Interfaces:**
- Consumes: `keystore.check_health`, `keystore.set_override` (Task 6 uses this); `get_principal`/`Principal` from `app/api/deps.py`; `get_session` from `app/db/session.py`; `DomainError` from `app/api/errors.py`.
- Produces: `HunarHealthOut { status: str, source: str | None, checked_at: str }`, `HunarKeyUpdateIn { api_key: str }`; router at prefix `/hunar`; endpoint `GET /hunar/health` (query `refresh: bool = False`).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_hunar_health_api.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_hunar_health_api.py -k "requires_auth or unconfigured or healthy_with_env" -v`
Expected: FAIL (404 on `/hunar/health` — router not registered).

- [ ] **Step 3: Add schemas**

Append to `apps/api/app/api/schemas.py` (it already uses Pydantic `BaseModel`; match the file's existing import/style):

```python
class HunarHealthOut(BaseModel):
    status: str  # healthy | invalid | unconfigured | unreachable
    source: str | None  # override | env | None
    checked_at: str


class HunarKeyUpdateIn(BaseModel):
    api_key: str
```

- [ ] **Step 4: Create the router (health only for now)**

Create `apps/api/app/api/routers/hunar.py`:

```python
"""Hunar voice-AI health + key management.

- GET /hunar/health  → current health (cached ~60s; ?refresh=1 forces a live probe). Any
  authenticated user may read. Never returns the key.
- PUT /hunar/key     → admin-only; validates the key against Hunar before saving it durably.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import HunarHealthOut, HunarKeyUpdateIn
from app.db.session import get_session
from app.integrations.hunar import keystore
from app.integrations.hunar.client import HunarError
from app.modules.audit.log import write_audit

router = APIRouter(prefix="/hunar", tags=["hunar"])


@router.get("/health", response_model=HunarHealthOut)
def get_health(
    refresh: bool = False,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    return keystore.check_health(session, refresh=refresh)
```

- [ ] **Step 5: Register the router**

In `apps/api/app/main.py`, add `hunar` to the routers import (line 12) and add an `include_router` call next to the others:

```python
from app.api.routers import assistant, auth, candidates, dashboard, funnels, hunar, interviews, jobs, settings as settings_router, sourcing, system, webhooks
```
```python
    app.include_router(hunar.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_hunar_health_api.py -k "requires_auth or unconfigured or healthy_with_env" -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/schemas.py apps/api/app/api/routers/hunar.py apps/api/app/main.py apps/api/tests/test_hunar_health_api.py
git commit -m "feat(api): GET /hunar/health endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `PUT /hunar/key` — admin re-key (validate → save → audit → bust cache)

**Files:**
- Modify: `apps/api/app/api/routers/hunar.py`
- Test: `apps/api/tests/test_hunar_health_api.py` (append)

**Interfaces:**
- Consumes: `keystore.build_client`, `keystore.set_override`, `keystore.HEALTH_CACHE_KEY`; `cache_delete` from `app.redis_client`; `write_audit`; `HunarError`.
- Produces: `PUT /hunar/key` returning `HunarHealthOut` (status `healthy`, source `override`) on success.
- Behavior: admin-only (403 otherwise); empty key → 422; candidate key probed with `GET /numbers/` before saving — 401/403 → 422 "rejected by the voice-AI provider" (not saved); other error → 502 (not saved); success → save override, bust `hunar:health`, audit `hunar.key.updated` (no key value in the audit).

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_hunar_health_api.py`:

```python
def _accept_invite_as_recruiter(client):
    """Create a recruiter session in the same org via the invite→accept flow."""
    inv = client.post("/settings/invites", json={"email": "rec@acme.test", "role": "recruiter", "name": "Rec"})
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_url"].split("token=")[1]
    # Accepting the invite logs the new user in (sets the session cookie on this client).
    acc = client.post("/auth/accept-invite", json={"token": token, "password": "pw-123456"})
    assert acc.status_code in (200, 201), acc.text


def test_put_key_admin_validates_and_saves(client, monkeypatch):
    _signup_admin(client)
    monkeypatch.setattr(keystore, "build_client", lambda api_key: _FakeClient())
    r = client.put("/hunar/key", json={"api_key": "k-live-new"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "healthy"
    assert body["source"] == "override"
    with engine.connect() as conn:
        val = conn.execute(text("SELECT value FROM app_config WHERE key='hunar_api_key'")).scalar_one()
        actions = conn.execute(text("SELECT action FROM audit_events")).scalars().all()
    assert val == "k-live-new"
    assert "hunar.key.updated" in actions


def test_put_key_rejects_invalid_key_without_saving(client, monkeypatch):
    _signup_admin(client)
    monkeypatch.setattr(keystore, "build_client",
                        lambda api_key: _FakeClient(raise_exc=HunarError("no", status_code=401)))
    r = client.put("/hunar/key", json={"api_key": "bad"})
    assert r.status_code == 422, r.text
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM app_config WHERE key='hunar_api_key'")).scalar_one()
    assert n == 0


def test_put_key_rejects_empty(client):
    _signup_admin(client)
    r = client.put("/hunar/key", json={"api_key": "   "})
    assert r.status_code == 422, r.text


def test_put_key_forbidden_for_non_admin(client, monkeypatch):
    _signup_admin(client)
    _accept_invite_as_recruiter(client)  # client is now the recruiter
    monkeypatch.setattr(keystore, "build_client", lambda api_key: _FakeClient())
    r = client.put("/hunar/key", json={"api_key": "k-live-new"})
    assert r.status_code == 403, r.text
```

Note: verify the accept-invite route path/body while implementing — inspect `app/api/routers/auth.py`. If the route differs, adjust `_accept_invite_as_recruiter` to match the real endpoint (the assertion that a non-admin gets 403 is what matters).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_hunar_health_api.py -k put_key -v`
Expected: FAIL (405/404 — PUT not defined).

- [ ] **Step 3: Implement the endpoint**

Add to `apps/api/app/api/routers/hunar.py` — extend imports and append the route:

```python
from app.redis_client import cache_delete
```

```python
def _require_admin(principal: Principal) -> None:
    if principal.role != "admin":
        raise DomainError("Only an admin can update the voice-AI key.", code="forbidden", status_code=403)


@router.put("/key", response_model=HunarHealthOut)
def update_key(
    body: HunarKeyUpdateIn,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    _require_admin(principal)
    candidate = (body.api_key or "").strip()
    if not candidate:
        raise DomainError("Enter a voice-AI key.", code="validation_error", status_code=422)

    # Validate BEFORE persisting: a bad key must never be saved.
    try:
        keystore.build_client(candidate).list_numbers()
    except HunarError as exc:
        if exc.status_code in (401, 403):
            raise DomainError("That key was rejected by the voice-AI provider.", code="validation_error", status_code=422)
        raise DomainError("Couldn't reach the voice-AI provider to verify the key. Try again.", code="bad_gateway", status_code=502)

    keystore.set_override(session, candidate, actor_user_id=principal.user_id)
    write_audit(
        session,
        org_id=principal.org_id,
        action="hunar.key.updated",
        entity_type="hunar_key",
        entity_id=principal.org_id,  # global config; anchor the event to the acting org
        actor_user_id=principal.user_id,
        reason="voice-ai key rotated in-app",
    )
    cache_delete(keystore.HEALTH_CACHE_KEY)
    return keystore.check_health(session, refresh=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_hunar_health_api.py -k put_key -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the whole new backend suite**

Run: `cd apps/api && pytest tests/test_hunar_keystore.py tests/test_hunar_health_api.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/routers/hunar.py apps/api/tests/test_hunar_health_api.py
git commit -m "feat(api): PUT /hunar/key admin re-key with validate-before-save + audit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Web API client — health + re-key methods

**Files:**
- Modify: `apps/web/lib/api.ts`

**Interfaces:**
- Produces: `export type HunarHealth = { status: "healthy" | "invalid" | "unconfigured" | "unreachable"; source: "override" | "env" | null; checked_at: string }`; `api.getHunarHealth(refresh?: boolean): Promise<HunarHealth>`; `api.updateHunarKey(apiKey: string): Promise<HunarHealth>`.

- [ ] **Step 1: Add the type**

Near the other exported types in `apps/web/lib/api.ts` (e.g. after `AuditPageResult`):

```typescript
export type HunarHealth = {
  status: "healthy" | "invalid" | "unconfigured" | "unreachable";
  source: "override" | "env" | null;
  checked_at: string;
};
```

- [ ] **Step 2: Add the methods**

Inside the `export const api = { ... }` object (next to `getSettings`/`updateSettings` around line 214), add:

```typescript
  getHunarHealth: (refresh = false) =>
    req<HunarHealth>(`/hunar/health${refresh ? "?refresh=1" : ""}`),
  updateHunarKey: (apiKey: string) =>
    req<HunarHealth>("/hunar/key", { method: "PUT", body: JSON.stringify({ api_key: apiKey }) }),
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/api.ts
git commit -m "feat(web): API client methods for Hunar health + re-key

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Health badge component + admin re-key modal

**Files:**
- Create: `apps/web/components/HunarHealthBadge.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- Consumes: `api.getHunarHealth`, `api.updateHunarKey`, `HunarHealth` (Task 7); `useAuth` from `@/lib/auth` (for `me.role`).
- Produces: default export `HunarHealthBadge` (a `"use client"` component, self-contained: fetches on mount, polls every 60s, and — for admins — opens a re-key modal).

- [ ] **Step 1: Implement the component**

Create `apps/web/components/HunarHealthBadge.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type HunarHealth } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const LABEL: Record<HunarHealth["status"], string> = {
  healthy: "Voice AI connected",
  invalid: "Voice AI key expired",
  unconfigured: "Voice AI not configured",
  unreachable: "Voice AI unreachable",
};

export default function HunarHealthBadge() {
  const { me } = useAuth();
  const [health, setHealth] = useState<HunarHealth | null>(null);
  const [open, setOpen] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      setHealth(await api.getHunarHealth(refresh));
    } catch {
      /* leave prior state; badge shows "checking" until first success */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => load(), 60_000);
    return () => clearInterval(t);
  }, [load]);

  const isAdmin = me?.role === "admin";
  const needsFix = health?.status === "invalid" || health?.status === "unconfigured";
  const tone = !health
    ? "checking"
    : health.status === "healthy"
      ? "ok"
      : health.status === "unreachable"
        ? "warn"
        : "bad";
  const label = health ? LABEL[health.status] : "Checking voice AI…";

  async function submit() {
    if (!keyInput.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      const updated = await api.updateHunarKey(keyInput.trim());
      setHealth(updated);
      setOpen(false);
      setKeyInput("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="hunar-badge">
      <button
        type="button"
        className={`hunar-badge-pill ${tone}`}
        onClick={() => isAdmin && needsFix && setOpen(true)}
        aria-label={`Voice AI status: ${label}`}
        disabled={!(isAdmin && needsFix)}
      >
        <span className="hunar-dot" aria-hidden="true" />
        <span>{label}</span>
      </button>
      {needsFix && !isAdmin && (
        <small className="hunar-badge-hint">Ask an admin to update the voice-AI key.</small>
      )}
      {needsFix && isAdmin && !open && (
        <button type="button" className="linklike" onClick={() => setOpen(true)}>
          Update key
        </button>
      )}

      {open && (
        <div className="hunar-modal-backdrop" role="dialog" aria-modal="true" aria-label="Update voice AI key">
          <div className="hunar-modal">
            <h3>Update voice-AI key</h3>
            <p className="muted">Paste a new live key from the voice-AI provider. It is verified before it is saved.</p>
            <input
              type="password"
              autoFocus
              placeholder="Paste new live key…"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
            />
            {err && <p className="error">{err}</p>}
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button className="secondary" onClick={() => { setOpen(false); setErr(null); }} disabled={saving}>
                Cancel
              </button>
              <button onClick={submit} disabled={saving || !keyInput.trim()}>
                {saving ? "Verifying…" : "Save key"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add styling**

Append to `apps/web/app/globals.css` (reuse existing color variables where the file defines them; these class names are new):

```css
.hunar-badge { display: flex; flex-direction: column; gap: 4px; padding: 8px 0; }
.hunar-badge-pill { display: inline-flex; align-items: center; gap: 8px; border: none; background: transparent; color: inherit; font: inherit; cursor: default; padding: 4px 0; }
.hunar-badge-pill:disabled { cursor: default; }
.hunar-badge-pill:not(:disabled) { cursor: pointer; }
.hunar-dot { width: 8px; height: 8px; border-radius: 50%; background: #888; }
.hunar-badge-pill.ok .hunar-dot { background: #22c55e; }
.hunar-badge-pill.bad .hunar-dot { background: #ef4444; }
.hunar-badge-pill.warn .hunar-dot { background: #9ca3af; }
.hunar-badge-pill.checking .hunar-dot { background: #f59e0b; }
.hunar-badge-hint { font-size: 11px; opacity: 0.7; }
.hunar-modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 50; }
.hunar-modal { background: var(--surface, #12121a); color: inherit; border-radius: 12px; padding: 20px; width: min(420px, 92vw); display: flex; flex-direction: column; gap: 12px; }
.hunar-modal input { width: 100%; }
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/HunarHealthBadge.tsx apps/web/app/globals.css
git commit -m "feat(web): voice-AI health badge + admin re-key modal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Wire the badge into the app shell

**Files:**
- Modify: `apps/web/components/AppShell.tsx`

**Interfaces:**
- Consumes: `HunarHealthBadge` (Task 8).

- [ ] **Step 1: Import and render the badge**

In `apps/web/components/AppShell.tsx`, add the import near the other component imports:

```tsx
import HunarHealthBadge from "./HunarHealthBadge";
```

Render it in the sidebar footer — between the `sidebar-foot` div and the sign-out button (after line 81, before `<button className="secondary signout" ...>`):

```tsx
        <HunarHealthBadge />
```

- [ ] **Step 2: Verify in the browser**

Run the app (`cd apps/web && npm run dev`, and the API per its README). Log in as the demo admin.
Expected: the sidebar footer shows "Voice AI not configured" (no key in dev) with an "Update key" action; pasting a key opens the modal. With a valid `hunar_api_key` in the API `.env`, it shows green "Voice AI connected".

Take a screenshot for the handoff.

- [ ] **Step 3: Typecheck + commit**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no new errors.

```bash
git add apps/web/components/AppShell.tsx
git commit -m "feat(web): show voice-AI health badge in the app shell

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: Docs + handoff

**Files:**
- Modify: `docs/interfaces.md` (document the two endpoints)
- Modify: `docs/vendor-capability-matrix.md` (note `/numbers/` used as health probe)
- Modify: `docs/work/active-feature.md` (handoff per the non-negotiables)

- [ ] **Step 1: Document the endpoints in `docs/interfaces.md`**

Add a short subsection under the API section:

```markdown
### Voice-AI (Hunar) health & key

- `GET /hunar/health` — any authenticated user. `{ status, source, checked_at }` where
  `status ∈ {healthy, invalid, unconfigured, unreachable}` and `source ∈ {override, env, null}`.
  Result cached ~60s in Redis; `?refresh=1` forces a live probe (`GET /numbers/`). Never
  returns the key.
- `PUT /hunar/key` — admin only. Body `{ api_key }`. Validates the key against Hunar before
  saving it durably (global `app_config` row); 401/403 → 422 (rejected, not saved), transport
  error → 502 (not saved). On success busts the health cache and audit-logs `hunar.key.updated`
  (never the key value). Resolution order for the effective key: DB override → `.env`.
```

- [ ] **Step 2: Note the probe in `docs/vendor-capability-matrix.md`**

Add a line noting `GET /numbers/` (already VERIFIED) doubles as the key-validity/health probe (2xx = valid, 401/403 = invalid/expired).

- [ ] **Step 3: Update the handoff in `docs/work/active-feature.md`**

Record: feature (Hunar key health + in-app re-key), what shipped (global `app_config` durable override, DB-override→env resolution, `/hunar/health` + `/hunar/key`, sidebar badge + admin modal), verification (backend suite `tests/test_hunar_keystore.py` + `tests/test_hunar_health_api.py`, web typecheck, browser screenshot), remaining/risks (Redis is cache-only; a real Hunar account key is needed to see "healthy" live), branch, and the exact next action.

- [ ] **Step 4: Commit**

```bash
git add docs/interfaces.md docs/vendor-capability-matrix.md docs/work/active-feature.md
git commit -m "docs: document Hunar health/re-key endpoints and update handoff

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Backend: `cd apps/api && pytest tests/test_hunar_keystore.py tests/test_hunar_health_api.py -v` → all pass (or skip if no Postgres).
- [ ] Full backend regression: `cd apps/api && pytest -q` → no new failures.
- [ ] Web: `cd apps/web && npx tsc --noEmit && npm run build` → clean.
- [ ] Browser: badge shows correct state for unconfigured / healthy; admin can re-key; non-admin sees the hint, not the modal.
```
