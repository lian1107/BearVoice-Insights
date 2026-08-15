# BearVoice 直接依赖许可证清单

> 核对日期：2026-08-15。版本来自 `uv.lock`、`bun.lock` 和容器镜像标签；许可证来自已安装包元数据或对应项目的许可证声明。这里只列直接依赖，完整传递依赖以锁文件和镜像 SBOM 为准。

## 后端运行依赖

| 依赖 | 锁定版本 | 许可证 | 用途 |
|---|---:|---|---|
| Alembic | 1.19.1 | MIT | 数据库迁移 |
| asyncpg | 0.31.0 | Apache-2.0 | PostgreSQL 异步驱动 |
| FastAPI | 0.141.1 | MIT | 企业 API |
| Jinja2 | 3.1.6 | BSD-3-Clause | 兼容 Markdown 导出 |
| pgvector | 0.5.0 | MIT | 向量字段与查询 |
| PyJWT | 2.13.0 | MIT | OIDC/JWT 校验 |
| pydantic-settings | 2.15.0 | MIT | 安全配置 |
| SQLAlchemy | 2.0.52 | MIT | 领域持久化 |
| Temporal Python SDK | 1.31.0 | MIT | 耐久工作流 |
| Uvicorn | 0.52.3 | BSD-3-Clause | ASGI 运行时 |

## 后端开发依赖

| 依赖 | 锁定版本 | 许可证 | 用途 |
|---|---:|---|---|
| HTTPX | 0.28.1 | BSD-3-Clause | API 测试 |
| HTTPX2 | 2.10.0 | BSD-3-Clause | HTTP/2 测试支持 |
| pytest | 9.1.1 | MIT | 测试框架 |
| pytest-asyncio | 1.4.0 | Apache-2.0 | 异步测试 |
| Ruff | 0.16.3 | MIT | Python 静态检查 |

## 前端直接依赖

| 依赖 | 锁定版本 | 许可证 | 用途 |
|---|---:|---|---|
| React / React DOM | 19.2.8 | MIT | 企业界面 |
| Vite | 8.2.1 | MIT | 构建与开发服务器 |
| TypeScript | 7.0.2 | Apache-2.0 | 类型检查 |
| Playwright Test | 1.62.1 | Apache-2.0 | 浏览器端到端验证 |
| Testing Library React | 16.3.2 | MIT | 组件行为测试 |
| Happy DOM / Global Registrator | 20.11.2 | MIT | 单元测试 DOM |
| Vite React Plugin | 6.0.5 | MIT | React 构建集成 |
| `@types/bun` | 1.3.14 | MIT | Bun 类型 |
| `@types/react` | 19.2.18 | MIT | React 类型 |
| `@types/react-dom` | 19.2.4 | MIT | React DOM 类型 |

## 容器运行依赖

| 镜像 | 版本 | 许可证 | 用途 |
|---|---:|---|---|
| pgvector/pgvector | 0.8.6-pg16 | PostgreSQL | PostgreSQL 16 + pgvector |
| valkey/valkey | 9.1.1-alpine | BSD-3-Clause | 缓存与限流协议 |
| temporalio/auto-setup | 1.29.7 | MIT | Temporal 服务 |
| temporalio/ui | 2.53.3 | MIT | 本地工作流查看 |
| Python | 3.12-slim-bookworm | PSF-2.0 | API/Worker 基础镜像 |
| nginxinc/nginx-unprivileged | 1.29-alpine | BSD-2-Clause | 前端静态服务 |
| oven/bun | 1.3.14-alpine | MIT | 前端构建镜像 |
| astral-sh/uv | python3.12-bookworm-slim | Apache-2.0 OR MIT | 后端构建与依赖锁定 |

## 合规结论

- 直接依赖中未发现 AGPL 许可证；本地缓存使用 Valkey，不引入 MinIO。
- 发布或升级依赖前，必须重新生成版本与许可证清单，并对完整 SBOM 做一次 AGPL/SSPL/未知许可证阻断检查。
- 本清单不是第三方许可证正文；对外交付镜像时应随 SBOM 一并提供各依赖的原始 LICENSE/NOTICE。
