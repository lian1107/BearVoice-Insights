#!/usr/bin/env bash
set -euo pipefail

PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$PLATFORM_DIR/.." && pwd)"

cd "$PLATFORM_DIR"
docker-compose --env-file .env.example up -d --build \
  db cache temporal temporal-ui migrate api worker web

for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "API 在 30 秒内没有就绪" >&2
    exit 1
  fi
  sleep 1
done

cd "$PLATFORM_DIR/backend"
BEARVOICE_DATABASE_URL="postgresql+asyncpg://bearvoice:local-only-change-me@127.0.0.1:55432/bearvoice" \
  uv run python -m bearvoice.cli import-legacy --repo-root "$REPO_DIR"

cd "$PLATFORM_DIR/frontend"
bun run test:e2e:compose
