# BearVoice 企业平台系统架构审查

> 日期：2026-08-15  
> 对象：`platform/` 当前本地纵向链路  
> 结论：架构主干成立，经本轮修订后适合作为企业接入前的可验证底座；不能据此声称已满足生产上线条件或产生业务效果。

## 审查对象与服务的决策

本次审查回答：当前平台是否能在不制造“假成功”、不破坏证据审计、不过早暴露生产攻击面的前提下，继续进入 GitHub 合并、业务定标和企业集成阶段。边界包括 React/Nginx、FastAPI、PostgreSQL/pgvector、Temporal、对象存储接口、身份权限、模型外发门禁和 Compose 运维；不把正式 SSO、Kubernetes、PLM 或企业 S3 尚未提供的外部条件冒充为已完成。

## 站得住的部分

- **事实证据**：模块化单体与统一 PostgreSQL 真相源适合当前规模，领域关系、证据下钻、人工审核和历史修订没有被过早拆成分布式服务。
- **事实证据**：模型外发默认拒绝，提供商、用途和隐私门禁三者必须同时通过；本轮依赖审计未发现已知漏洞。
- **事实证据**：本地浏览器只经同源 Nginx 访问 API，服务端口只绑定回环地址，开发会话使用短期 HttpOnly Cookie。
- **事实证据**：机会审核、黄金样本双人定标、模型发布门禁和数据基线均有自动测试，真实 Compose 浏览器链路不拦截 API。
- **机制推断**：在单机、单产品线、开发环境边界内，当前复杂度与可恢复性之间的取舍合理；此判断不自动外推到企业生产环境。

## 重要发现、修改和复查

### P1 · Temporal Activity 会制造“假成功”——已修复

- **状态**：事实证据。
- **证据**：原 `execute_analysis_phase` 对所有阶段直接返回 `completed`，不读取分析运行、信号、隐私状态、向量、聚类成员或机会证据；失败诊断函数也未接入 Activity。
- **后果**：工作流时间线可能显示成功，但真实数据产物不存在，赛事演示和故障恢复都会给出错误信号。
- **修改**：Activity 改为锁定真实 `AnalysisRun`，校验输入哈希与阶段顺序，逐阶段核对持久化数据，写入幂等阶段账本；缺少真实产物时非重试失败，不能用默认成功掩盖。已验证的历史导入明确标记“不需要重新生成向量”，而不是伪造向量。
- **复查**：新增幂等、哈希漂移和缺少真实产物的失败关闭测试；工作流编排重试测试继续通过。

### P1 · 审计与关键并发规则只存在于应用代码——已修复

- **状态**：事实证据。
- **证据**：`audit_events` 原来只有主键，可被更新或删除；重复导入、同一评测重复发布及多个 active 模型没有数据库级约束。
- **后果**：并发或误操作可破坏幂等、产生两个活跃模型，或者改写追责记录，应用层先查后写不足以封住竞争窗口。
- **修改**：迁移 `0003` 增加审计表 UPDATE/DELETE 拒绝触发器、来源文件哈希唯一约束、黄金样本顺序唯一约束、评测发布唯一约束和单 active 部分唯一索引；发布与回滚分两次 flush 释放唯一槽位。
- **复查**：数据库行为测试真实尝试修改审计记录并确认失败，同时检查全部约束和索引存在。

### P1 · “进程活着”被当成“系统可用”——已修复

- **状态**：事实证据。
- **证据**：原健康接口不检查数据库或生产配置，API、Web、Temporal 缺少容器健康检查，依赖关系只等待进程启动。
- **后果**：数据库不可用、生产 OIDC/S3 未配置或 Temporal 尚未服务时，编排仍可能把实例当成可接流量。
- **修改**：保留轻量 liveness，新增数据库与生产配置 readiness；生产缺少 HTTPS OIDC、批准的 S3 或误开开发认证时返回 not-ready。Compose 增加 Temporal/API/Web 健康检查、健康依赖、重启策略、init 和 no-new-privileges。未使用的 Valkey 不再成为 API 启动前置条件。
- **复查**：真实栈中数据库、缓存、Temporal、API、Web 均进入 healthy，Nginx 代理的 readiness 返回空问题清单。

### P1 · 浏览器认证链存在可避免的令牌与跨站面——已修复

- **状态**：事实证据。
- **证据**：前端保留从 `sessionStorage` 读取 Bearer token 的路径；开发登录允许缺少 Origin；Nginx 未设置 CSP、反嵌入、内容类型和权限策略响应头。
- **后果**：一旦出现前端脚本注入，存储中的令牌可被读取；缺少来源校验扩大本机浏览器跨站请求面。
- **修改**：前端改为 Cookie/BFF 方向，不再读取浏览器存储令牌；Cookie 认证的写操作必须同源且来自回环主机；开发登录强制 Origin；OIDC JWKS 客户端增加缓存与超时；生产关闭 OpenAPI/Docs；Nginx 与 API 补齐安全响应头。
- **复查**：缺 Origin 登录和 Cookie 跨站写入均被拒绝；真实浏览器登录、页面内联样式和 API 读取在 CSP 下继续通过。

### P1 · 应用工厂配置与数据库连接不是同一来源——已修复

- **状态**：机制推断，依据代码路径确认。
- **证据**：原 `create_app(custom_settings)` 只替换认证设置，数据库依赖仍使用模块导入时创建的全局引擎。
- **后果**：测试、迁移工具和多环境部署可能展示一套配置、连接另一套数据库，健康检查也无法代表业务请求的真实连接。
- **修改**：应用工厂按活动配置创建引擎与会话工厂，API 依赖和 readiness 共用同一实例；CLI 保留显式全局工厂作为独立入口。
- **复查**：后端完整测试和真实容器迁移、导入、读取均通过。

## 最强反例

把当前 Compose 原样搬进多用户生产网络，并认为“有 OIDC 字段和健康检查就等于生产安全”。这种情况下，Temporal 信号端仍需要企业网络隔离、命名空间权限与传输认证；数据源管理员的跨产品线统计范围、保留策略执行和企业备份一致性也尚未关闭。这个反例说明本轮结论只覆盖企业接入前底座，不覆盖正式上线验收。

## 结论翻转边界

在单机回环网络、开发会话、单品类真实数据和人工演示边界内，结论为“架构连贯且关键缺陷已修订”。一旦进入多用户、跨产品线、外部对象存储或允许模型外发的环境，如果正式 SSO、Temporal 内网认证、密钥管理、产品线数据范围和恢复演练没有同时完成，结论立即翻转为“不具备生产上线条件”。

## 需要真人校准的假设

- **角色模拟假设**：产品经理更在意机会证据与负责人闭环，而不是工作流技术拓扑；需由小熊产品、品控和客服运营共同校准。
- **角色模拟假设**：系统管理员能提供 OIDC、企业 S3、内部 DNS/TLS、Temporal 网络策略和备份目标；需由企业 IT 给出真实约束。
- **角色模拟假设**：审核量增长不会超过业务团队可处理能力；需用真实双人标注耗时、争议率和机会积压验证，不能由当前自动测试推出。

## 系统回路与杠杆顺序

- R1（机制推断，短期）：自动抽取覆盖增加 → 候选机会增加 → 审核负荷增加 → 积压增加 → 结论时效下降。
- B1（事实机制，短期）：证据门禁和双人定标增强 → 不可靠发布减少 → 返工与错误扩散减少。
- B2（机制推断，中期）：审核结果进入黄金集 → 回归门禁更强 → 模型退化减少 → 审核返工下降。

建议杠杆顺序是：先完成真实业务定标并量出审核能力，再扩产品线；正式接入前完成身份与网络信任边界；最后才开启外部模型或自动写回。反证信号是审核积压持续增长、同类机会重复出现或安全样本漏检，此时应暂停扩张而不是增加自动生成量。

## 残余风险与取舍

- 正式 SSO/OIDC、Kubernetes、企业 S3、Secret Manager、Temporal mTLS/命名空间权限和 PLM 写回仍是企业落地项。
- `source_admin` 的产品线/渠道范围目前没有足够细的批次级数据模型；接入多产品、多管理员前必须补齐，不能只依赖前端隐藏。
- 数据保留天数目前是配置与展示，尚无真实清理任务和法务保留例外；生产前需要明确数据所有者、删除审批和审计策略。
- 数据库与 Temporal 在本地共用 PostgreSQL 实例及开发凭据，适合单机验证，不应复制为生产的最小权限方案。
- 本轮只能证明内部一致性、失败关闭和真实栈可运行，不能证明机会准确率、节省时间或改善产品质量。

## 修订清单与验证证据

- 代码与迁移：`platform/backend/src/bearvoice/`、`platform/backend/alembic/versions/0003_architecture_hardening.py`。
- 部署与边界：`platform/compose.yaml`、`platform/frontend/nginx.conf`、`platform/scripts/test-compose-browser.sh`。
- 自动验证：后端 49 条、前端 6 条、模拟浏览器 6 条、真实 Compose 浏览器 1 条全部通过；Ruff、前后端构建、Compose 配置、Nginx 配置、gitleaks、Python 与 Bun 依赖审计通过。
- 数据对账：真实 PostgreSQL 仍为 370 条原声、254 条可行动原声、10 个聚类、9 条机会，历史导入保持 0 次模型调用。

```json
{
  "contract": "minerva-skill-output/1",
  "skill": "review-with-perspectives",
  "verification": "partial",
  "input_digest": {
    "quoted_numbers": [
      {"value": "49 backend tests", "basis": "computed", "derived_from": ["pytest output"]},
      {"value": "6 frontend tests", "basis": "computed", "derived_from": ["bun test output"]},
      {"value": "6 mocked browser tests", "basis": "computed", "derived_from": ["playwright output"]},
      {"value": "1 real compose browser test", "basis": "computed", "derived_from": ["compose playwright output"]},
      {"value": "370/254/10/9 and 0 model calls", "basis": "computed", "derived_from": ["idempotent legacy import output", "real database projection"]}
    ],
    "sensitive_present": false
  },
  "risk": {
    "domain": "privacy",
    "named_human_owner": "本地仓库负责人 lian；生产上线前由小熊书面指定企业责任人"
  },
  "data_boundary": {
    "excluded_data": ["未脱敏客户原文", "生产凭据", "访问令牌", "私钥"]
  },
  "refusal_rules": [
    "生产 OIDC 或企业 S3 未就绪时 readiness 必须失败",
    "未通过隐私门禁和提供商用途白名单时禁止模型外发"
  ],
  "object_and_decision": "审查企业客户原声平台能否安全进入合并、业务定标和企业集成阶段。",
  "what_holds": [
    "模块化单体与统一真相源适合当前边界。",
    "证据、人工审核和模型外发默认拒绝机制成立。",
    "本地同源真实数据链可重复运行。"
  ],
  "material_findings": [
    {
      "finding": "工作流阶段原来会在没有真实产物时报告成功。",
      "status": "fact",
      "consequence": "运行历史可能误导审核与恢复判断。",
      "revision": "改为校验真实持久化产物并记录幂等阶段账本。",
      "recheck": "缺少真实产物时失败关闭，正常编排回归通过。"
    },
    {
      "finding": "审计不可变与关键并发规则原来只靠应用约定。",
      "status": "evidence",
      "consequence": "并发或误操作可能破坏发布唯一性和追责记录。",
      "revision": "增加数据库触发器、唯一约束和部分唯一索引。",
      "recheck": "真实数据库拒绝审计修改并保留原值。"
    },
    {
      "finding": "健康检查、浏览器令牌路径和容器依赖未覆盖生产失效模式。",
      "status": "mechanism-inference",
      "consequence": "错误配置或依赖未就绪时可能提前接流量，并扩大浏览器攻击面。",
      "revision": "增加 readiness、同源写校验、安全头、应用级数据库工厂和容器健康依赖。",
      "recheck": "真实栈健康且真实浏览器链继续通过。"
    }
  ],
  "strongest_counterexample": "把本地 Compose 直接当成多用户生产部署，会遗漏 Temporal 内网认证、细粒度数据范围和保留策略执行。",
  "boundary_where_conclusion_flips": "从单机开发边界进入多用户、跨产品线、模型外发或外部系统写回时，缺少企业身份与网络控制会使上线结论翻转。",
  "simulated_claims_needing_validation": [
    "真实审核能力是否足以承接候选机会增长。",
    "企业 IT 是否能提供所需身份、存储、网络和恢复能力。",
    "业务人员是否认可当前证据与机会工作流。"
  ],
  "revised_artifact": "已修订后端阶段账本、数据库硬约束、应用工厂、浏览器安全边界、反向代理和 Compose 编排。",
  "residual_risks": [
    "正式企业身份、网络和对象存储尚未接通。",
    "跨产品线来源管理和保留策略执行仍需企业阶段实现。",
    "业务效果与审核能力仍需真人定标。"
  ],
  "conclusion": "coherent-with-revisions"
}
```
