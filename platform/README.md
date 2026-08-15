# BearVoice 企业平台

`platform/` 是小熊电器内部私有化的客户原声产品机会平台。它承载企业前端、业务 API、耐久工作流和本地运行编排；现有 `scripts/` 与 `reports/` 继续作为兼容入口和可重建产物。

面向路演官方的产品定位、验证快照和建议评审路径见根目录 `docs/ROADSHOW.md`。本文只维护可复现的启动、配置、部署、恢复和验证步骤。

## 顶层目录协议

- **作品怎么验证**：后端 `uv run pytest`、前端 `bun test`、端到端 `bunx playwright test`、`docker-compose config` 和养生壶历史基线对账。
- **真相源是谁**：Alembic 数据库迁移、后端领域规则与 OpenAPI。`reports/` 是由同一数据投影生成的派生产物。

## 安全默认值

- 模型外发默认关闭，必须由管理员显式配置批准的提供商和用途。
- 开发数据卷与本地对象存储位于 `platform/.data/`，不进入 Git。
- `.env` 不入库；从 `.env.example` 创建本地配置后再替换本地密码。
- 开发缓存使用 Valkey 的 Redis 兼容协议，避免引入 AGPL 服务依赖。
- 本地开发服务仅绑定 `127.0.0.1`；短期登录会话使用 HttpOnly、SameSite Cookie，API 重启后自动失效。
- Cookie 写操作强制校验同源 Origin；前端不在 Web Storage 保存访问令牌。
- `/api/health` 只表示进程存活；流量与自动化必须使用会检查数据库和生产配置的 `/api/ready`。

## 首次启动

### 路演一键启动（推荐）

前提仅需 Docker Desktop。脚本会创建本地开发配置、构建镜像、执行迁移、启动全部服务，并幂等载入养生壶路演基线；不会调用外部模型。

```bash
cd platform
bash scripts/demo-up.sh
```

启动完成后打开 `http://localhost:4173`，点击“进入本地开发环境”。“数据接入与分析”会先在内存中预检 UTF-8 CSV，再由用户确认原声、产品、SKU、批次、版本等字段映射。默认使用 0 次外部调用的本地规则基线；管理员完成安全配置后，也可选择 DeepSeek、智谱 GLM、MiniMax、通义千问或自定义兼容模型。所有模型产出均保持“待人工复核”。

### 手动启动

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

`migrate` 是一次性服务；迁移成功后 API 和 worker 才启动。首次导入历史规则基线时，命令输出必须为 10 次缓存命中、0 次模型调用、370/254/10/9；这是回归基线，不是 DeepSeek V4 Pro 运行快照。Web 默认位于 `http://localhost:4173`，Temporal UI 位于 `http://localhost:8233`。

打开 Web 后点击“进入本地开发环境”。该入口只在 `runtime_environment=development`、显式启用本地会话且请求来自 localhost 时开放；不把签名密钥或令牌写入前端，生产默认关闭。正式部署必须关闭 `BEARVOICE_LOCAL_DEV_SESSION_ENABLED` 并接入 OIDC。保留的 Bearer 开发令牌模式仅供后端自动测试，不是浏览器默认入口。

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

必须同时满足以下条件才可把 `BEARVOICE_MODEL_EGRESS_ENABLED` 改为 `true`：管理员批准提供商和具体用途；提供商、用途和完整 HTTPS 端点分别进入 allowlist；载荷通过隐私门禁；OIDC、审计和企业网络出口已配置。只打开布尔开关不会绕过模型网关的默认拒绝。

以 DeepSeek 为例，在不入库的 `platform/.env` 中配置：

```dotenv
BEARVOICE_MODEL_EGRESS_ENABLED=true
BEARVOICE_MODEL_PROVIDER_ALLOWLIST=["deepseek"]
BEARVOICE_MODEL_PURPOSE_ALLOWLIST=["voice_semantic_analysis"]
BEARVOICE_MODEL_ENDPOINT_ALLOWLIST=["https://api.deepseek.com"]
BEARVOICE_DEEPSEEK_API_KEY=
BEARVOICE_DEEPSEEK_MODEL=deepseek-v4-pro
```

API key 只从运行环境读取，不在页面、数据库或日志中展示。自定义入口使用 `BEARVOICE_CUSTOM_AI_API_KEY`、`BEARVOICE_CUSTOM_AI_BASE_URL`和 `BEARVOICE_CUSTOM_AI_MODEL`，同样必须通过端点白名单。完整官方来源与配置表见 `backend/docs/china-model-api-sources.md`。

### 异步批处理与预算门禁

外部 AI 不再占用上传请求。导入成功后 API 返回 `202` 和任务 ID，Temporal Worker 按批次并发处理；页面轮询任务状态，本地规则基线仍即时完成。

- `BEARVOICE_SEMANTIC_BATCH_SIZE`：每个处理批次的原声数，默认 20。
- `BEARVOICE_SEMANTIC_MAX_CONCURRENCY`：批次内最大并发，默认 4。
- `BEARVOICE_SEMANTIC_RETRY_MAX_ATTEMPTS`：临时网络或输出契约失败的最大尝试次数，默认 3。
- `BEARVOICE_MODEL_JOB_MAX_CALLS` / `BEARVOICE_MODEL_DAILY_MAX_CALLS`：单任务和单日调用硬上限。
- `BEARVOICE_MODEL_JOB_BUDGET_RMB` / `BEARVOICE_MODEL_DAILY_BUDGET_RMB`：入队前的金额硬上限。
- `BEARVOICE_MODEL_RESERVED_COST_PER_CALL_RMB`：管理员设置的保守预留估值，不是供应商账单价格。

预算在数据库中按“日期 + 提供商”原子预留；预留调用数包含有界重试额度，并受单任务上限截断，每次外部调用前都会再次检查任务硬上限。同一批次、产品、模型重复提交会复用同一任务，不会重复占用预算。最终账单仍应以模型供应商控制台为准。

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
- 多产品线来源管理员范围、数据保留执行任务与 Temporal 生产网络认证必须在企业接入时补齐。
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

# 启动真实 Compose、幂等导入历史基线，并用浏览器走完整登录和数据链路
bash scripts/test-compose-browser.sh
```

最后一条测试不拦截或伪造 API：它验证浏览器经 Nginx 同源代理建立本地会话，再从真实 PostgreSQL 读取当前最新分析运行，并验证 CSV 预检、模型批准状态和产品决策边界。普通 `bun run test:e2e` 继续负责快速组件与多视口回归，两类测试必须都通过。
