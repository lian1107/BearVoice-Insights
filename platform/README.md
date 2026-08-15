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

## 本地验证

```bash
cd platform/backend
uv sync --python 3.12
uv run pytest

cd ../frontend
bun install
bun test

cd ..
docker-compose --env-file .env.example config --quiet
```

本地启动、数据迁移、工作流恢复、备份和回退流程会随相应任务逐步补齐。
