"""Alembic environment.

Django-app style: every module owns a `migrations/` folder (all registered as
`version_locations`). The active DB URL comes from `DATABASE_URL`. When generating each app's
initial migration, `ALEMBIC_MODULES` (comma-separated, cumulative) limits which models are
imported so autogenerate emits only that app's new tables; unset means all modules (used by
`upgrade`/runtime).
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the app package importable (prepend_sys_path=. covers cwd; be explicit too).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base  # noqa: E402
from app.modules import registry  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://recruitment:recruitment@localhost:5432/recruitment",
    )
    # SQLAlchemy needs an explicit psycopg (v3) driver.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# Import models: cumulative subset for per-app autogeneration, else all.
_subset = os.environ.get("ALEMBIC_MODULES")
registry.import_models([m.strip() for m in _subset.split(",") if m.strip()] if _subset else None)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", _database_url())
# version_locations is set statically in alembic.ini (read before env.py runs).


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
