#!/usr/bin/env bash
#
# Idempotent deploy for the AI Recruitment API on the EC2 host.
# Invoked by CI (.github/workflows/deploy-api.yml) and safe to run by hand.
#
# It fast-forwards the checkout to origin/main, rebuilds the compose stack, prunes
# dangling images, and waits for the API health check. Untracked files (notably the
# git-ignored .env holding secrets) are preserved — this never touches them.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/ai-recruitment}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"

cd "$APP_DIR"

echo "[deploy] fetching origin/main"
git fetch --prune origin
git reset --hard origin/main   # only tracked files; .env (untracked) is left intact

echo "[deploy] building + starting containers"
docker compose up -d --build

echo "[deploy] pruning dangling images"
docker image prune -f >/dev/null 2>&1 || true

echo "[deploy] waiting for API health at $HEALTH_URL"
for i in $(seq 1 30); do
  if curl -fsS -m 5 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy] API is healthy"
    docker compose ps
    exit 0
  fi
  sleep 3
done

echo "[deploy] ERROR: API did not become healthy in time" >&2
docker compose logs api --tail 60 || true
exit 1
