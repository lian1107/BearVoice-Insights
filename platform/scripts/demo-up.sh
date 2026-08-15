#!/usr/bin/env bash
set -euo pipefail

PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$PLATFORM_DIR/.." && pwd)"
DATA_REPO_DIR="$REPO_DIR"

# A Git worktree does not carry ignored analysis caches. Reuse the main checkout
# when it is available, while keeping a fresh clone fully runnable without it.
COMMON_GIT_DIR="$(git -C "$REPO_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "$COMMON_GIT_DIR" ]; then
  COMMON_REPO_DIR="$(cd "$COMMON_GIT_DIR/.." && pwd)"
  if [ -d "$COMMON_REPO_DIR/_build/analyze" ]; then
    DATA_REPO_DIR="$COMMON_REPO_DIR"
  fi
fi

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  echo "未检测到 Docker Compose，请先启动 Docker Desktop。" >&2
  exit 1
fi

cd "$PLATFORM_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建仅绑定本机的路演配置 platform/.env"
fi

echo "正在构建并启动 BearVoice 路演环境…"
"${COMPOSE[@]}" --env-file .env up -d --build \
  db cache temporal temporal-ui migrate api worker web

for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/ready >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:4173/api/ready >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "服务在 60 秒内没有就绪，请运行：cd '$PLATFORM_DIR' && ${COMPOSE[*]} --env-file .env logs api web" >&2
    exit 1
  fi
  sleep 1
done

EXTRACT_CACHE_COUNT="$(find "$DATA_REPO_DIR/_build/analyze" -maxdepth 1 -name 'extract-*.json' 2>/dev/null | wc -l | tr -d ' ')"
if [ "${EXTRACT_CACHE_COUNT:-0}" -ge 10 ] \
  && [ -f "$DATA_REPO_DIR/reports/improve-养生壶/聚类明细.json" ]; then
  echo "正在幂等载入养生壶路演基线（0 次模型调用）…"
  if ! "${COMPOSE[@]}" --env-file .env run --rm --no-deps \
    -v "$DATA_REPO_DIR:/workspace:ro" \
    api python -m bearvoice.cli import-legacy --repo-root /workspace; then
    echo "历史基线未能导入，服务仍可用；请从“数据接入与分析”上传 CSV。" >&2
  fi
else
  echo "未发现完整历史缓存，跳过基线导入；可从“数据接入与分析”上传 CSV。"
fi

echo ""
echo "BearVoice 已就绪："
echo "  产品界面  http://localhost:4173"
echo "  API 文档  http://localhost:8000/docs"
echo "  工作流    http://localhost:8233"
echo ""
echo "打开产品界面，点击“进入本地开发环境”；数据接入与分析入口可直接上传 UTF-8 CSV。"
