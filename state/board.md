# BearVoice Insights · 当前状态板

> 当前状态只记录已验证事实、尚未接通项和发布入口；历史演化见 `state/changelog.md`。

## 当前结论（2026-08-15）

**路演纵向链路已完成并通过真实 Compose 验证。**

- 数据接入已支持内存预检、字段映射、数据质量、去重、隐私脱敏和业务属性保存。
- 中国模型入口已覆盖 DeepSeek、GLM、MiniMax、通义千问和自定义 OpenAI-compatible 模型；默认外发关闭。
- 外部 AI 已升级为 Temporal 异步批处理、并发控制、指数退避、逐条检查点、未解析显式转人工和逐次预算硬上限。
- 信号已扩展生命周期、问题、场景、潜在需求、风险、根因假设、缺失信息、改进方向和验证计划。
- 产品决策洞察已提供多维切片、高价值模式、Top 决策卡、证据边界、禁止结论和人工责任人。
- 产品机会已贯通证据审核、行动负责人/协作人、状态机、结果指标和人工复盘。
- 本地认证使用 localhost 限定的短期 HttpOnly 会话；生产必须关闭并接入 OIDC。
- Nginx 同源 API、PostgreSQL/pgvector、Valkey、Temporal、API、Worker 和 Web 已在真实 Compose 中健康运行。

## DeepSeek V4 Pro 验证快照

- 正式批次：370/370 完成，逐条检查点 370，未解析 0。
- 最新运行：363 条去重原声、537 个信号、126 个候选聚类、126 个待审核机会。
- 风险：critical 6、high 54、medium 127、low 350。
- “底座冒烟并伴随烧塑料味”已作为 critical/P0 候选进入人工复核。
- 当前覆盖仅 4 天、单一天猫渠道；禁止趋势、总体外推、因果和 ROI 结论。

该数据库快照和 API Key 不进入 Git。全新克隆默认使用 0 次模型调用的本地规则基线，或由评审者上传自有 CSV。

## 验证证据

- 后端：80 项测试通过，Ruff 通过。
- 前端：9 项测试通过，TypeScript 与 Vite 生产构建通过。
- 真实 Compose 浏览器：3 项通过，不模拟 API。
- API、Web、Worker 健康；Alembic 为 `0007 (head)`。
- `git diff --check` 通过；`.env` 被 Git 忽略。

## 尚未接通（企业生产阶段）

- 正式企业 SSO/OIDC、生产 Kubernetes、企业对象存储和网络出口策略。
- Temporal 生产 mTLS/命名空间权限、多产品线来源管理员范围和数据保留执行任务。
- 外部 PLM/任务系统写回，以及淘宝等新增平台数据源。
- 100 条分层样本的真实双人标注/仲裁；当前队列和门禁不等于黄金真相。
- 销量、订单、退货、维修和成本分母；未接入前不计算发生率、损失金额或 ROI。

## 发布状态

- 当前分支：`codex/roadshow-upload-deploy`。
- GitHub 仓库：`lian1107/BearVoice-Insights`，当前为 Private。
- 路演入口：`README.md` 与 `docs/ROADSHOW.md`。
- 生产运维入口：`platform/README.md`。
