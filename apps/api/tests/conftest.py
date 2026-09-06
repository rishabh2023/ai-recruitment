"""Test fixtures.

Provides an isolated SQLAlchemy Session bound to a transaction that is rolled back after each
test (no test pollution). Requires a reachable Postgres via DATABASE_URL; if unreachable, the
DB-backed tests are skipped rather than failing the suite.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules import registry

registry.import_models()  # populate Base.metadata with all tables


def _url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://recruitment:recruitment@localhost:5432/recruitment"
    )
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
