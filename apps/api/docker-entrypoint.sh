#!/usr/bin/env sh
set -e

# Optionally apply migrations on startup (compose sets RUN_MIGRATIONS=1).
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
