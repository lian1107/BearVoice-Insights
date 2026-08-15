# BearVoice 企业平台

`platform/` 是小熊电器内部私有化的客户原声产品机会平台。它承载企业前端、业务 API、耐久工作流和本地运行编排；现有 `scripts/` 与 `reports/` 继续作为兼容入口和可重建产物。

## 顶层目录协议

- **作品怎么验证**：后端 `uv run pytest`、前端 `bun test`、端到端 `bunx playwright test`、`docker-compose config` 和养生壶历史基线对账。
- **真相源是谁**：Alembic 数据库迁移、后端领域规则与 OpenAPI。`reports/` 是由同一数据投影生成的派生产物。

## 安全默认值

- 模型外发默认关闭，必须由管理员显式配置批准的提供商和用途。
- 开发数据卷与本地对象存储位于 `platform/.data/`，不进入 Git。
- `.env` 不入库；从 `.env.example` 创建本地配置后再替换本地密码。
- 开发缓存使用 Valkey 的 Redis 兼容协议，避免引入 AGPL 服务依赖。

## 首次启动

前提：Docker Compose、uv、Bun 已安装。下面的历史导入只读取 10 个既有缓存；任一缓存缺失会停止，不会调用模型补算。

```bash
cd platform
cp .env.example .env
docker-compose --env-file .env up -d db cache temporal temporal-ui

cd backend
uv sync --frozen --python 3.12
uv run alembic upgrade head
uv run python -m bearvoice.cli import-legacy --repo-root ../../

cd ..
docker-compose --env-file .env up --build -d
docker-compose --env-file .env ps
```

`migrate` 是一次性服务；迁移成功后 API 和 worker 才启动。首次导入的命令输出必须为 10 次缓存命中、0 次模型调用、370/254/10/9。Web 默认位于 `http://localhost:4173`，Temporal UI 位于 `http://localhost:8233`。

正式 OIDC 未接通前，本地身份模式必须在未入库的 `.env` 中设置独立的 32 字符以上签名密钥；不得把测试令牌或密钥写入 README、浏览器源码或 Git。前端只从当前浏览器会话的 `bearvoice_access_token` 读取短期令牌。

## 日常运行与报告兼容

```bash
cd platform
docker-compose --env-file .env up -d
docker-compose --env-file .env logs -f api worker

cd backend
uv run python -m bearvoice.cli export-markdown ../../_tmp/20260815-bearvoice-export/报告.md
```

Markdown 报告由数据库统一投影生成，不是第二套真相源。旧的 `scripts/analyze.py` 仍可只读回放历史 CLI 管线；新数据、审核、机会与行动以平台数据库、审计事件和 Temporal 为准。

## 工作流暂停与恢复

- 自动阶段结束后工作流停在 `pending_review`；只有带审核人身份的批准 signal 才进入发布。
- worker 中断时不要删除 workflow 或更换 workflow ID；执行 `docker-compose --env-file .env restart worker`，Temporal 会从已记录事件恢复。
- Activity 重试沿用同一幂等键；缓存只读运行禁止在失败后改成模型补算。
- 先在 Temporal UI 核对运行 ID、当前阶段和尝试次数；日志只允许记录脱敏诊断，不记录提示词或客户原文。

## 模型外发开启条件

必须同时满足以下条件才可把 `BEARVOICE_MODEL_EGRESS_ENABLED` 改为 `true`：管理员批准提供商和具体用途；提供商与用途进入 allowlist；载荷通过隐私门禁；OIDC、审计和企业网络出口已配置。只打开布尔开关不会绕过模型网关的默认拒绝。

## 备份、恢复与回退

备份写入根目录 `_tmp/<日期>-bearvoice-backup/`，该目录不进 Git。先创建目标目录，再执行：

```bash
cd platform
docker-compose --env-file .env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > ../_tmp/20260815-bearvoice-backup/bearvoice.dump
ditto .data/objects ../_tmp/20260815-bearvoice-backup/objects
shasum -a 256 ../_tmp/20260815-bearvoice-backup/bearvoice.dump
```

恢复会覆盖数据库，必须先停 API/worker、保留当前备份并取得人工确认，再用 `pg_restore --clean --if-exists` 恢复；对象文件用 `ditto` 从同一时间点备份还原。迁移代码回退前先在副本执行 `uv run alembic downgrade -1`，验证数据兼容后才能用于生产。模型版本只回滚到曾通过全部发布门禁的版本。

## 生产边界

- 正式 SSO、生产 Kubernetes、外部 PLM 写回和新增平台数据源尚未接通。
- 开发环境使用 `platform/.data/objects`；生产仅接受管理员 allowlist 中的 HTTPS S3 端点，不内置 MinIO。
- 直接依赖与容器许可证见 `platform/licenses.md`；升级依赖后必须重新核对完整 SBOM。

## 本地验证

```bash
cd platform/backend
uv sync --python 3.12
uv run pytest
uv run ruff check src tests

cd ../frontend
bun install
bun run test
bun run build
bun run test:e2e

cd ..
docker-compose --env-file .env.example config --quiet
```
