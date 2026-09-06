"""Test fixtures.

Provides an isolated SQLAlchemy Session bound to a transaction that is rolled back after each
test (no test pollution). Requires a reachable Postgres via DATABASE_URL; if unreachable, the
DB-backed tests are skipped rather than failing the suite.
"""

from __future__ import annotations

import os

# SAFETY: redirect the whole test process to a dedicated *_test database BEFORE anything
# imports app.config / app.db.session. The HTTP tests drive the real app (which builds its
# engine from DATABASE_URL) and TRUNCATE tables, so without this a plain `pytest` against the
# dev DATABASE_URL would wipe live/demo data (including saved provider API keys). Set
# TEST_DATABASE_URL to override; otherwise we append `_test` to the configured DB name.
_explicit = os.environ.get("TEST_DATABASE_URL")
if _explicit:
    os.environ["DATABASE_URL"] = _explicit
else:
    _base = os.environ.get("DATABASE_URL", "postgresql://recruitment:recruitment@localhost:5432/recruitment")
    _head, _sep, _db = _base.rpartition("/")
    if not _db.endswith("_test"):
        os.environ["DATABASE_URL"] = f"{_head}{_sep}{_db}_test"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import Base
from app.modules import registry

registry.import_models()  # populate Base.metadata with all tables


@pytest.fixture(autouse=True)
def _hermetic_external(monkeypatch):
    """Keep the suite hermetic: never make a real Claude call or a real Hunar call, even when
    keys / live-call flags are present in the environment or .env."""
    monkeypatch.setattr(settings, "platform_llm_api_key", "", raising=False)
    monkeypatch.setattr(settings, "hunar_live_calls_enabled", False, raising=False)
    monkeypatch.setattr(settings, "hunar_api_key", "", raising=False)
    monkeypatch.setattr(settings, "hunar_default_agent_id", "", raising=False)
    monkeypatch.setattr(settings, "public_base_url", "", raising=False)
    # People search: blank real keys and default to the offline sample provider so the suite
    # never makes a real people-search HTTP call (even if .env has APOLLO_API_KEY etc.).
    monkeypatch.setattr(settings, "apollo_api_key", "", raising=False)
    monkeypatch.setattr(settings, "pdl_api_key", "", raising=False)
    monkeypatch.setattr(settings, "proxycurl_api_key", "", raising=False)
    monkeypatch.setattr(settings, "coresignal_api_key", "", raising=False)
    monkeypatch.setattr(settings, "people_search_provider", "sample", raising=False)


def _url() -> str:
    """Resolve the test database URL — NEVER the dev database.

    The HTTP fixtures TRUNCATE tables, so pointing tests at the dev DB wipes live/demo data
    (including saved provider keys). To prevent that, we use TEST_DATABASE_URL if set, else
    derive a dedicated `<db>_test` database from DATABASE_URL. Create it once with:
      createdb recruitment_test && DATABASE_URL=…/recruitment_test alembic upgrade head
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        base = os.environ.get(
            "DATABASE_URL", "postgresql://recruitment:recruitment@localhost:5432/recruitment"
        )
        # Append _test to the database name unless it already targets a *_test DB.
        head, sep, dbname = base.rpartition("/")
        url = base if dbname.endswith("_test") else f"{head}{sep}{dbname}_test"
    return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(_url())
    try:
        conn = eng.connect()
    except OperationalError as exc:  # pragma: no cover
        pytest.skip(f"Postgres not reachable for DB tests: {exc}")
    else:
        conn.close()
    Base.metadata.create_all(eng)  # no-op for tables Alembic already created
    return eng


@pytest.fixture
def session(engine):
    conn = engine.connect()
    trans = conn.begin()
    s = Session(bind=conn, expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()
