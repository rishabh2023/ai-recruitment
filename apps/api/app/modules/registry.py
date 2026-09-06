"""Module registry.

Declares the domain modules in dependency order (Django-app style). Each entry maps a module
name → its models import path → its migrations directory. Used by Alembic to (a) know all
`version_locations` and (b) import models incrementally when generating each app's initial
migration.
"""

from __future__ import annotations

import importlib
from pathlib import Path

# Order matters: later modules may hold foreign keys into earlier ones.
MODULES: list[str] = [
    "organizations",
    "jobs",
    "workflows",
    "candidates",
    "interviews",
    "webhooks",
    "audit",
    "sourcing",
]

_MODULES_ROOT = Path(__file__).resolve().parent


def models_import_path(module: str) -> str:
    return f"app.modules.{module}.models"


def migrations_dir(module: str) -> Path:
    return _MODULES_ROOT / module / "migrations"


def all_version_locations() -> list[str]:
    return [str(migrations_dir(m)) for m in MODULES]


def import_models(modules: list[str] | None = None) -> None:
    """Import the given modules' models (default: all) so Base.metadata is populated."""
    for module in modules if modules is not None else MODULES:
        importlib.import_module(models_import_path(module))
