# BearVoice Enterprise Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前私有仓库中建立可长期运营的 BearVoice 企业私有化平台，并用养生壶 370 条既有结果贯通原声证据、聚类治理、产品机会、人工审核、质量回归和赛事决策驾驶舱。

**Architecture:** 新增一个 `platform/` 顶层目录承载 React 前端、FastAPI 模块化后端和本地私有化运行编排，现有 `scripts/` 与 `reports/` 保持兼容。PostgreSQL/pgvector 是业务和向量真相源，Temporal 是耐久工作流真相源，Redis 只用于缓存与限流；所有 AI 输出均先进入人工审核，既有 Claude 缓存只读导入且禁止缺失时回退到模型调用。

**Tech Stack:** Python 3.12、uv、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、PostgreSQL 16、pgvector、Temporal、Redis、S3 兼容对象存储、React 19、TypeScript、Vite、TanStack Query、Apache ECharts、Vitest、Playwright、Docker Compose/Colima。

## Global Constraints

- 单企业私有化部署；不建设多租户、计费、公开注册或 SaaS 客户管理。
- 新顶层目录只新增 `platform/`：作品验证由后端、前端、端到端和数据对账测试共同完成；数据库迁移、领域规则与 OpenAPI 是平台真相源，`reports/` 是可重建派生产物。
- 使用 `uv python install 3.12` 管理项目 Python，不修改 macOS 自带 Python 3.9。
- 复用养生壶 370 条原声、10 个 `extract-*.json` 缓存、10 个聚类和 9 条建议；迁移路径任何缓存缺失都必须失败，禁止调用 `claude -p` 或其他模型补算。
- 原始原声不可修改；纠错、改名、合并、拆分和人工判断通过新版本或审计事件表达。
- 一段对话允许多个信号；低置信度、异常项、未归类项不得被强制塞入 Top10。
- AI 只生成候选；机会发布、聚类修订、模型发布和安全结论必须由有权限的人确认。
- 当前 3 天单渠道数据只支持截面描述，不生成趋势、同比、环比或因果结论。
- 不直接复制 AGPL 项目代码；依赖锁文件和许可证清单必须入库。
- 密钥只从环境、企业凭据系统或本地配置读取；`.env`、令牌、客户个人信息不得入库或写入审计正文。
- 所有新行为使用 TDD：先看到目标测试因功能缺失而失败，再写最小实现并运行全量回归。
- 每个逻辑单元独立提交并包含仓库要求的五行提交链；不推送远端，除非用户另行授权。

---

## File Structure

```text
platform/
  README.md                         # 新顶层目录协议、开发与验证入口
  .env.example                     # 仅变量名和安全默认值
  compose.yaml                     # PostgreSQL/pgvector、Temporal、Redis、API、Web
  backend/
    Dockerfile
    pyproject.toml                  # Python 3.12 依赖与 pytest/ruff 配置
    uv.lock                         # 可复现后端依赖
    alembic.ini
    alembic/
      env.py
      versions/0001_enterprise_foundations.py
    src/bearvoice/
      main.py                       # FastAPI 应用工厂
      config.py                     # 环境配置与安全默认值
      db.py                         # 异步数据库会话
      domain/enums.py               # 共享状态与权限枚举
      domain/models.py              # SQLAlchemy 领域模型
      domain/schemas.py             # API/命令 Pydantic 契约
      modules/ingest/legacy.py      # 既有原声和缓存的只读迁移
      modules/ingest/adapter.py     # 数据源适配协议和 CSV 实现
      modules/ingest/privacy.py     # 中文隐私识别与脱敏门禁
      modules/analysis/cache.py     # 内容哈希和严格缓存读取
      modules/analysis/workflow.py  # Temporal 分析工作流
      modules/review/service.py     # 分类法修订和人工审核
      modules/opportunities/service.py # 机会证据门槛与状态机
      modules/evaluation/service.py # 分层样本、黄金集、版本门禁
      modules/reporting/queries.py  # 驾驶舱投影与历史对账
      security/auth.py              # OIDC Principal 与权限依赖
      security/model_gateway.py     # 默认禁用外发的模型适配层
      api/routes/*.py               # sources、runs、taxonomy、opportunities、evaluation、dashboard、admin
    tests/
      unit/
      integration/
      workflow/
  frontend/
    Dockerfile
    package.json
    bun.lock
    vite.config.ts
    src/
      app/App.tsx
      app/router.tsx
      api/client.ts
      api/types.ts
      pages/DashboardPage.tsx
      pages/TaxonomyPage.tsx
      pages/OpportunityPage.tsx
      pages/EvaluationPage.tsx
      components/*.tsx
      styles/tokens.css
    tests/
    e2e/
```

---

### Task 1: 建立平台骨架和可重复工具链

**Files:**
- Create: `platform/README.md`
- Create: `platform/.env.example`
- Create: `platform/compose.yaml`
- Create: `platform/backend/pyproject.toml`
- Create: `platform/backend/Dockerfile`
- Create: `platform/backend/src/bearvoice/__init__.py`
- Create: `platform/backend/src/bearvoice/config.py`
- Create: `platform/backend/src/bearvoice/main.py`
- Create: `platform/backend/tests/unit/test_health.py`
- Create: `platform/frontend/package.json`
- Create: `platform/frontend/Dockerfile`
- Create: `platform/frontend/src/app/App.tsx`
- Create: `platform/frontend/tests/App.test.tsx`

**Interfaces:**
- Consumes: 设计规格中的私有化边界和 `platform/` 顶层目录协议。
- Produces: `bearvoice.main:create_app() -> FastAPI`、`GET /api/health`、可渲染的前端应用壳、统一的 `platform/` 验证命令。

- [ ] **Step 1: 写后端健康检查失败测试**

```python
from fastapi.testclient import TestClient
from bearvoice.main import create_app


def test_health_reports_service_and_no_model_egress():
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "service": "bearvoice",
        "status": "ok",
        "model_egress": "disabled",
    }
```

- [ ] **Step 2: 运行测试并确认因应用尚不存在而失败**

Run: `cd platform/backend && uv run --python 3.12 pytest tests/unit/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bearvoice'`.

- [ ] **Step 3: 创建最小后端应用和安全配置**

```python
from fastapi import FastAPI
from bearvoice.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active = settings or Settings()
    app = FastAPI(title="BearVoice", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "service": "bearvoice",
            "status": "ok",
            "model_egress": "enabled" if active.model_egress_enabled else "disabled",
        }

    return app
```

`Settings` 使用 `pydantic-settings`，`model_egress_enabled` 默认 `False`；`.env.example` 只写本地非敏感地址和变量名，不写凭据值。

- [ ] **Step 4: 写前端应用壳失败测试**

```tsx
import { render, screen } from "@testing-library/react";
import { App } from "../src/app/App";

test("shows the enterprise product opportunity workspace", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "产品机会决策平台" })).toBeVisible();
  expect(screen.getByText("模型外发默认关闭")).toBeVisible();
});
```

- [ ] **Step 5: 运行前端测试并确认因应用尚不存在而失败**

Run: `cd platform/frontend && bun test tests/App.test.tsx`
Expected: FAIL because `../src/app/App` cannot be resolved.

- [ ] **Step 6: 创建前端应用壳、依赖锁和平台运行说明**

`App.tsx` 先提供可测试的产品壳：

```tsx
export function App() {
  return (
    <main>
      <h1>产品机会决策平台</h1>
      <p role="status">模型外发默认关闭</p>
    </main>
  );
}
```

`platform/README.md` 明确：

```text
作品怎么验证：uv run pytest、bun test、bunx playwright test、docker compose config、历史数据对账。
真相源是谁：Alembic 数据库迁移 + 领域规则 + OpenAPI；reports/ 是派生产物。
```

两个 Dockerfile 固定非 root 运行用户；后端镜像使用 Python 3.12 与锁定的 `uv.lock`，前端构建产物由非 root 静态服务进程提供。Compose 只引用官方或项目已核验许可证的镜像。

- [ ] **Step 7: 运行任务级验证**

Run: `cd platform/backend && uv run --python 3.12 pytest tests/unit/test_health.py -v`
Expected: PASS, 1 test.

Run: `cd platform/frontend && bun test tests/App.test.tsx`
Expected: PASS, 1 test.

Run: `cd platform && docker compose config --quiet`
Expected: exit 0; if Docker CLI is absent, install open-source Colima、Docker CLI and Compose from Homebrew before rerunning, then start Colima.

- [ ] **Step 8: 提交平台骨架**

```bash
git add platform
git commit -m "feat: 建立企业平台骨架" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 2: 建立统一领域模型和数据库迁移

**Files:**
- Create: `platform/backend/src/bearvoice/db.py`
- Create: `platform/backend/src/bearvoice/domain/enums.py`
- Create: `platform/backend/src/bearvoice/domain/models.py`
- Create: `platform/backend/src/bearvoice/domain/schemas.py`
- Create: `platform/backend/alembic.ini`
- Create: `platform/backend/alembic/env.py`
- Create: `platform/backend/alembic/versions/0001_enterprise_foundations.py`
- Create: `platform/backend/tests/integration/test_migrations.py`
- Create: `platform/backend/tests/unit/test_domain_rules.py`

**Interfaces:**
- Consumes: Task 1 `Settings.database_url`。
- Produces: `Base`、`async_session_factory`、`VoiceRecord`、`Signal`、`TaxonomyVersion`、`TaxonomyRevision`、`Opportunity`、`OpportunityEvidence`、`CompetitorEvidence`、`ActionItem`、`OutcomeMeasurement`、`GoldenExample`、`EvaluationRun`、`AuditEvent`、`OpportunityStatus`、`ReviewDecisionType`、`Permission` 和数据库首版迁移。

- [ ] **Step 1: 写数据库结构失败测试**

```python
REQUIRED_TABLES = {
    "sources", "ingestion_batches", "voice_records", "conversation_turns",
    "privacy_findings", "analysis_runs", "signals", "embeddings",
    "taxonomy_versions", "clusters", "cluster_memberships", "taxonomy_revisions",
    "opportunities", "opportunity_evidence", "review_decisions",
    "competitor_evidence", "action_items", "outcome_measurements",
    "golden_examples", "evaluation_runs", "model_releases", "audit_events",
}


async def test_initial_migration_creates_enterprise_foundation_tables(db_inspector):
    assert REQUIRED_TABLES <= set(await db_inspector.table_names())
```

- [ ] **Step 2: 运行迁移测试并确认因迁移不存在而失败**

Run: `cd platform/backend && uv run pytest tests/integration/test_migrations.py -v`
Expected: FAIL because Alembic configuration or required tables do not exist.

- [ ] **Step 3: 写领域状态失败测试**

```python
import pytest
from bearvoice.domain.enums import OpportunityStatus
from bearvoice.domain.schemas import OpportunityDraft


def test_new_product_draft_requires_five_independent_evidence_items():
    with pytest.raises(ValueError, match="新品型机会至少需要 5 条独立证据"):
        OpportunityDraft(
            opportunity_type="new_product",
            title="一人份免看管早餐壶",
            evidence_record_ids=["a", "b", "c", "d"],
        )


def test_opportunity_cannot_skip_human_review():
    assert OpportunityStatus.DRAFT.can_transition_to(OpportunityStatus.ACCEPTED) is False
```

- [ ] **Step 4: 运行领域测试并确认缺少规则实现**

Run: `cd platform/backend && uv run pytest tests/unit/test_domain_rules.py -v`
Expected: FAIL because enums and schemas do not exist.

- [ ] **Step 5: 实现模型、约束和首版迁移**

在 `models.py` 中使用 UUID 主键、UTC 时间、外键、唯一键和 JSONB 元数据；`embeddings.vector` 使用 pgvector。关键数据库约束包括：

```python
UniqueConstraint("source_id", "external_id", name="uq_voice_source_external")
UniqueConstraint("analysis_run_id", "voice_record_id", "signal_index", name="uq_run_voice_signal")
CheckConstraint("evidence_direction IN ('support', 'oppose')")
```

状态转换由 `OpportunityStatus.can_transition_to()` 的显式映射控制；新品型和改进型证据门槛在 Pydantic 命令校验与服务层事务中各检查一次。

- [ ] **Step 6: 运行数据库和领域测试**

Run: `cd platform/backend && uv run alembic upgrade head && uv run pytest tests/unit/test_domain_rules.py tests/integration/test_migrations.py -v`
Expected: PASS; PostgreSQL 中存在全部必需表和 `vector` 扩展。

- [ ] **Step 7: 提交领域底座**

```bash
git add platform/backend
git commit -m "feat: 建立企业原声领域模型" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 3: 只读迁移既有养生壶缓存和报告结果

**Files:**
- Modify: `scripts/analyze.py`
- Create: `platform/backend/src/bearvoice/modules/analysis/cache.py`
- Create: `platform/backend/src/bearvoice/modules/ingest/adapter.py`
- Create: `platform/backend/src/bearvoice/modules/ingest/privacy.py`
- Create: `platform/backend/src/bearvoice/modules/ingest/legacy.py`
- Create: `platform/backend/tests/unit/test_strict_cache.py`
- Create: `platform/backend/tests/unit/test_privacy_gate.py`
- Create: `platform/backend/tests/integration/test_csv_adapter.py`
- Create: `platform/backend/tests/integration/test_legacy_import.py`

**Interfaces:**
- Consumes: Task 2 ORM；`vault/raw/20260815-赛题资料/天猫咨询原声-1500条.csv`；`_build/analyze/extract-*.json`；`reports/improve-养生壶/聚类明细.json`。
- Produces: `SourceAdapter`、`CsvVoiceAdapter`、`sanitize_voice_text()`、`strict_cache_path(prompt: str, tag: str) -> Path`、`load_cached_json(prompt, tag) -> list|dict`、`load_legacy_snapshot(repo_root: Path) -> LegacySnapshot`、`import_legacy_snapshot(session, snapshot) -> UUID`。

- [ ] **Step 1: 写严格缓存失败测试**

```python
import pytest
from bearvoice.modules.analysis.cache import CacheMiss, load_cached_json


def test_cache_only_loader_never_calls_a_model(tmp_path):
    with pytest.raises(CacheMiss, match="禁止补算"):
        load_cached_json("not-cached", "extract", build_dir=tmp_path)
```

- [ ] **Step 2: 运行并确认缓存接口缺失**

Run: `cd platform/backend && uv run pytest tests/unit/test_strict_cache.py -v`
Expected: FAIL because `bearvoice.modules.analysis.cache` does not exist.

- [ ] **Step 3: 实现内容哈希路径和严格只读加载**

```python
class CacheMiss(RuntimeError):
    pass


def load_cached_json(prompt: str, tag: str, build_dir: Path) -> object:
    path = strict_cache_path(prompt, tag, build_dir)
    if not path.exists():
        raise CacheMiss(f"缓存缺失，禁止补算：{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))
```

把 `scripts/analyze.py` 的缓存路径计算提取为兼容函数，但不改变现有普通运行行为；迁移模块只调用严格加载器。

- [ ] **Step 4: 写历史迁移对账失败测试**

```python
async def test_imports_verified_kettle_baseline_once(db_session, repo_root):
    snapshot = load_legacy_snapshot(repo_root)
    run_id = await import_legacy_snapshot(db_session, snapshot)
    await import_legacy_snapshot(db_session, snapshot)

    assert snapshot.extract_cache_count == 10
    assert await count_rows(db_session, VoiceRecord) == 370
    assert await count_rows(db_session, Signal) == 370
    assert await count_rows(db_session, Cluster) == 10
    assert await count_rows(db_session, Opportunity) == 9
    assert await count_actionable_signals(db_session, run_id) == 254
    assert await count_analysis_runs(db_session, provider="legacy-claude-cache") == 1
```

- [ ] **Step 5: 写 CSV 适配和隐私门禁失败测试**

```python
async def test_csv_adapter_is_idempotent_and_never_persists_raw_address(session, kettle_csv):
    adapter = CsvVoiceAdapter(source_name="天猫咨询", product_column="商品标题")
    first = await adapter.import_file(session, kettle_csv)
    second = await adapter.import_file(session, kettle_csv)
    assert first.batch_id == second.batch_id
    assert await count_rows(session, VoiceRecord) == 1109
    assert "省榆县街市场门口" not in await all_normalized_voice_text(session)
    assert "[地址已脱敏]" in await all_normalized_voice_text(session)
```

`SourceAdapter` 协议固定为 `validate → normalize → dedupe → privacy_gate → persist`，后续平台适配器不得绕过隐私门禁。

- [ ] **Step 6: 运行并确认迁移、适配和隐私服务缺失**

Run: `cd platform/backend && uv run pytest tests/unit/test_privacy_gate.py tests/integration/test_csv_adapter.py tests/integration/test_legacy_import.py -v`
Expected: FAIL because ingest and legacy import functions do not exist.

- [ ] **Step 7: 实现适配协议、隐私门禁和确定性缓存映射**

隐私门禁先复用现有地址规则，再通过可注册识别器扩展手机号、订单号和自定义实体；`PrivacyFinding` 只保存实体类型、位置、识别器和处理动作，不保存命中的原值。迁移模块使用现有 `EXTRACT_RULES`、产品筛选和 40 条批次规则重建每批提示词哈希，将缓存中的相对索引映射回原声 ID。导入前一次性验证 10 个预期缓存全部存在；任何一个缺失时事务回滚且不调用模型。历史聚类无法恢复校准置信度，统一写 `confidence=None`、`confidence_status="uncalibrated"`。

```python
def load_legacy_snapshot(repo_root: Path) -> LegacySnapshot:
    rows = load_kettle_rows(repo_root)
    batches = [rows[i:i + 40] for i in range(0, len(rows), 40)]
    cached_batches = [
        load_cached_json(build_extract_prompt(batch), "extract", repo_root / "_build/analyze")
        for batch in batches
    ]
    if sum(len(batch) for batch in cached_batches) != 370:
        raise LegacyBaselineMismatch("抽取缓存没有完整覆盖 370 条养生壶原声")
    return LegacySnapshot.from_verified_inputs(rows, cached_batches, load_cluster_detail(repo_root))
```

- [ ] **Step 8: 运行迁移、隐私、旧测试和数据库对账**

Run: `cd platform/backend && uv run pytest tests/unit/test_strict_cache.py tests/unit/test_privacy_gate.py tests/integration/test_csv_adapter.py tests/integration/test_legacy_import.py -v`
Expected: PASS.

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS, existing 4 tests.

- [ ] **Step 9: 提交数据接入和历史迁移**

```bash
git add scripts/analyze.py platform/backend
git commit -m "feat: 建立数据接入并迁移养生壶结果" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 4: 建立可恢复的 Temporal 分析工作流

**Files:**
- Create: `platform/backend/src/bearvoice/modules/analysis/workflow.py`
- Create: `platform/backend/src/bearvoice/modules/analysis/activities.py`
- Create: `platform/backend/src/bearvoice/observability.py`
- Create: `platform/backend/src/bearvoice/worker.py`
- Create: `platform/backend/tests/workflow/test_analysis_workflow.py`
- Create: `platform/backend/tests/integration/test_analysis_run_history.py`
- Create: `platform/backend/tests/unit/test_trace_redaction.py`

**Interfaces:**
- Consumes: `AnalysisRun`、严格缓存服务、数据库会话。
- Produces: `AnalysisWorkflow.run(input: AnalysisWorkflowInput) -> AnalysisWorkflowResult`、`approve_taxonomy` signal、可查询阶段历史。

- [ ] **Step 1: 写失败恢复和人工暂停测试**

```python
async def test_workflow_retries_activity_and_waits_for_human_approval(temporal_env):
    handle = await temporal_env.start_workflow(
        AnalysisWorkflow.run,
        AnalysisWorkflowInput(run_id="run-1", cache_only=True),
        id="analysis-run-1",
    )
    await temporal_env.wait_until_query(handle, "current_phase", "pending_review")
    assert await handle.query(AnalysisWorkflow.current_phase) == "pending_review"
    await handle.signal(AnalysisWorkflow.approve_taxonomy, reviewer_id="reviewer-1")
    result = await handle.result()
    assert result.status == "succeeded"
    assert temporal_env.activity_attempts("extract_signals") == 2
```

- [ ] **Step 2: 运行并确认工作流缺失**

Run: `cd platform/backend && uv run pytest tests/workflow/test_analysis_workflow.py -v`
Expected: FAIL because `AnalysisWorkflow` does not exist.

- [ ] **Step 3: 实现显式阶段、重试、查询和人工 signal**

```python
@workflow.defn
class AnalysisWorkflow:
    def __init__(self) -> None:
        self.phase = "pending"
        self.approved_by: str | None = None

    @workflow.query
    def current_phase(self) -> str:
        return self.phase

    @workflow.signal
    def approve_taxonomy(self, reviewer_id: str) -> None:
        self.approved_by = reviewer_id
```

主流程阶段固定为 `validate → privacy_gate → extract → embed → cluster → draft_opportunities → quality_gate → pending_review → publish`。每个 Activity 使用 `run_id + phase + input_hash` 幂等键；`cache_only=True` 时任何缓存缺失立即失败。

- [ ] **Step 4: 运行工作流测试并确认最小实现通过**

Run: `cd platform/backend && uv run pytest tests/workflow/test_analysis_workflow.py -v`
Expected: PASS; the workflow retries once, pauses for review and resumes after the signal.

- [ ] **Step 5: 写运行历史失败测试**

```python
async def test_failed_run_records_redacted_machine_readable_diagnostics(session, failed_cluster_activity):
    run = await load_analysis_run(session, failed_cluster_activity.run_id)
    assert run.phase == "cluster"
    assert run.error_code == "invalid_output"
    assert run.completed_phases == ["validate", "privacy_gate", "extract", "embed"]
    assert "sk-test-secret" not in run.redacted_message


def test_trace_attributes_exclude_prompt_and_customer_text():
    attributes = build_trace_attributes(
        run_id="run-1",
        phase="extract",
        provider="cache-only",
        model=None,
        input_hash="sha256:abc",
    )
    assert set(attributes) == {"run_id", "phase", "provider", "model", "input_hash"}
```

- [ ] **Step 6: 运行并确认诊断记录尚未实现**

Run: `cd platform/backend && uv run pytest tests/integration/test_analysis_run_history.py tests/unit/test_trace_redaction.py -v`
Expected: FAIL because failure diagnostics are not persisted.

- [ ] **Step 7: 实现机器可读诊断**

失败运行保存 `phase`、`error_code`、`provider`、`model`、`attempts` 和已完成阶段；错误正文在写入前脱敏。OpenTelemetry span 只携带运行 ID、阶段、提供商、模型和输入哈希，可导出到企业批准的自托管可观测平台，不记录提示词或客户文本。

```python
await record_run_failure(
    session,
    RunFailure(
        run_id=run_id,
        phase="cluster",
        error_code="invalid_output",
        provider="cache-only",
        model=None,
        attempts=1,
        completed_phases=["validate", "privacy_gate", "extract", "embed"],
        redacted_message="聚类结果不符合结构契约",
    ),
)
```

- [ ] **Step 8: 运行工作流和运行历史测试**

Run: `cd platform/backend && uv run pytest tests/workflow tests/integration/test_analysis_run_history.py tests/unit/test_trace_redaction.py -v`
Expected: PASS; workflow can resume without repeating completed cache-backed extraction.

- [ ] **Step 9: 提交耐久工作流**

```bash
git add platform/backend
git commit -m "feat: 增加耐久分析工作流" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 5: 实现聚类治理和产品机会审核状态机

**Files:**
- Create: `platform/backend/src/bearvoice/modules/review/service.py`
- Create: `platform/backend/src/bearvoice/modules/opportunities/service.py`
- Create: `platform/backend/tests/unit/test_taxonomy_revision.py`
- Create: `platform/backend/tests/unit/test_opportunity_review.py`
- Create: `platform/backend/tests/unit/test_action_outcome.py`
- Create: `platform/backend/tests/integration/test_review_audit.py`

**Interfaces:**
- Consumes: Task 2 领域模型和状态枚举。
- Produces: `apply_taxonomy_revision(session, command) -> TaxonomyVersion`、`review_opportunity(session, command) -> Opportunity`、`transition_opportunity(session, command) -> Opportunity`。

- [ ] **Step 1: 写分类法不可变性失败测试**

```python
async def test_merge_creates_new_taxonomy_version_without_mutating_source(session, seeded_taxonomy):
    revised = await apply_taxonomy_revision(
        session,
        MergeClustersCommand(
            taxonomy_id=seeded_taxonomy.id,
            cluster_ids=["c1", "c2"],
            new_name="加热与测温异常",
            actor_id="reviewer-1",
            reason="同一加热控制根因",
        ),
    )
    assert revised.parent_id == seeded_taxonomy.id
    assert await original_cluster_names(session, seeded_taxonomy.id) == ["原类一", "原类二"]
```

- [ ] **Step 2: 运行并确认修订服务缺失**

Run: `cd platform/backend && uv run pytest tests/unit/test_taxonomy_revision.py -v`
Expected: FAIL because review service does not exist.

- [ ] **Step 3: 实现改名、合并、拆分、移出和恢复命令**

所有命令在单个事务中创建 `TaxonomyVersion`、`TaxonomyRevision` 和新成员映射；不更新父版本。成员主归属在一个版本内唯一，异常成员可没有主聚类。

```python
async def apply_taxonomy_revision(session, command):
    source = await lock_taxonomy(session, command.taxonomy_id)
    revised = source.fork(actor_id=command.actor_id)
    command.apply(revised)
    session.add_all([revised, command.to_audit_revision(revised.id)])
    await session.flush()
    return revised
```

- [ ] **Step 4: 运行分类法修订测试并确认通过**

Run: `cd platform/backend && uv run pytest tests/unit/test_taxonomy_revision.py -v`
Expected: PASS; source taxonomy remains unchanged.

- [ ] **Step 5: 写机会证据与安全覆盖失败测试**

```python
async def test_safety_opportunity_bypasses_volume_ranking_but_still_requires_review(session):
    opportunity = await create_opportunity(
        session,
        OpportunityDraft(
            opportunity_type="improvement",
            title="玻璃壶身炸裂",
            safety_level="critical",
            evidence_record_ids=["v1", "v2", "v3"],
        ),
    )
    assert opportunity.priority_override == "safety"
    assert opportunity.status == OpportunityStatus.PENDING_REVIEW
```

- [ ] **Step 6: 运行并确认机会服务尚未实现**

Run: `cd platform/backend && uv run pytest tests/unit/test_opportunity_review.py -v`
Expected: FAIL because evidence gates and safety override are missing.

- [ ] **Step 7: 实现证据门槛、审核决定和状态转换**

改进型必须至少 3 个独立原声键，新品型至少 5 个且跨场景或人群；证据不足只能保存为 `draft`。接受、重大修改和驳回都要求理由并写 `AuditEvent`。

```python
async def review_opportunity(session, command: ReviewOpportunityCommand) -> Opportunity:
    opportunity = await lock_opportunity(session, command.opportunity_id)
    opportunity.assert_evidence_gate_for(command.decision)
    opportunity.apply_review(command.decision, command.reason, command.actor_id)
    session.add(ReviewDecision.from_command(command))
    session.add(AuditEvent.from_opportunity_review(opportunity, command))
    return opportunity
```

- [ ] **Step 8: 运行机会审核测试并确认通过**

Run: `cd platform/backend && uv run pytest tests/unit/test_opportunity_review.py tests/integration/test_review_audit.py -v`
Expected: PASS; reviews require reasons and create audit events.

- [ ] **Step 9: 写行动结果闭环失败测试**

```python
async def test_completed_action_requires_outcome_measurement(session, accepted_opportunity):
    action = await create_action_item(session, accepted_opportunity.id, owner_id="pm-1")
    with pytest.raises(InvalidTransition, match="完成行动前必须记录结果和限制"):
        await complete_action_item(session, action.id, outcome=None)
```

- [ ] **Step 10: 运行并确认行动完成门禁尚未实现**

Run: `cd platform/backend && uv run pytest tests/unit/test_action_outcome.py -v`
Expected: FAIL because `complete_action_item()` does not enforce outcome evidence.

- [ ] **Step 11: 实现行动结果闭环**

```python
async def complete_action_item(session, action_id: UUID, outcome: OutcomeDraft | None):
    if outcome is None or not outcome.result or not outcome.limitations:
        raise InvalidTransition("完成行动前必须记录结果和限制")
    action = await lock_action_item(session, action_id)
    measurement = OutcomeMeasurement.from_draft(action_id, outcome)
    action.status = ActionStatus.COMPLETED
    session.add_all([measurement, AuditEvent.from_action_completion(action, outcome)])
    return action
```

- [ ] **Step 12: 运行治理、审核、行动和审计测试**

Run: `cd platform/backend && uv run pytest tests/unit/test_taxonomy_revision.py tests/unit/test_opportunity_review.py tests/unit/test_action_outcome.py tests/integration/test_review_audit.py -v`
Expected: PASS; original taxonomy remains unchanged and every decision has one audit event.

- [ ] **Step 13: 提交治理闭环**

```bash
git add platform/backend
git commit -m "feat: 增加聚类治理与机会审核" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 6: 建立 100 条人工定标样本和模型发布门禁

**Files:**
- Create: `platform/backend/src/bearvoice/modules/evaluation/service.py`
- Create: `platform/backend/tests/unit/test_stratified_sample.py`
- Create: `platform/backend/tests/unit/test_golden_review.py`
- Create: `platform/backend/tests/integration/test_release_gate.py`

**Interfaces:**
- Consumes: 历史分析运行、信号、聚类、人工审核。
- Produces: `build_stratified_sample(session, run_id, size=100, seed=20260815) -> list[GoldenExample]`、`submit_golden_review()`、`adjudicate_golden_example()`、`evaluate_release()`、`rollback_release()`。

- [ ] **Step 1: 写分层抽样失败测试**

```python
async def test_sample_is_deterministic_and_covers_signals_clusters_and_hard_cases(session, legacy_run):
    first = await build_stratified_sample(session, legacy_run.id, size=100, seed=20260815)
    second = await build_stratified_sample(session, legacy_run.id, size=100, seed=20260815)
    assert [x.voice_record_id for x in first] == [x.voice_record_id for x in second]
    assert len(first) == 100
    assert {x.primary_signal for x in first} == {"缺陷", "认知", "预期", "咨询"}
    assert len({x.cluster_id for x in first}) == 10
    assert any(x.hard_case == "multi_turn" for x in first)
    assert any(x.hard_case == "safety" for x in first)
```

- [ ] **Step 2: 运行并确认评测服务缺失**

Run: `cd platform/backend && uv run pytest tests/unit/test_stratified_sample.py -v`
Expected: FAIL because evaluation service does not exist.

- [ ] **Step 3: 实现确定性分层抽样**

先按安全样本、多轮难例、四类信号和 10 个聚类分配最低配额，再按固定种子从剩余记录补足 100 条；相同运行和种子必须返回相同 ID 顺序。所有样本状态初始为 `pending_human_review`。

```python
def choose_stratified_rows(rows, size: int, seed: int):
    selected = take_required_strata(rows, strata=("safety", "multi_turn", "signal", "cluster"))
    remaining = sorted(set(rows) - set(selected), key=lambda row: row.voice_record_id)
    random.Random(seed).shuffle(remaining)
    return (selected + remaining)[:size]
```

- [ ] **Step 4: 运行分层抽样测试并确认通过**

Run: `cd platform/backend && uv run pytest tests/unit/test_stratified_sample.py -v`
Expected: PASS with deterministic 100-record coverage.

- [ ] **Step 5: 写双人审核与发布门禁失败测试**

```python
async def test_model_release_is_blocked_when_safety_regresses(session, approved_golden_set):
    evaluation = await evaluate_release(session, candidate="model-v2", golden_set=approved_golden_set)
    evaluation.safety_false_negatives = 1
    release = await decide_release(session, evaluation.id, actor_id="model-reviewer")
    assert release.status == "blocked"
    assert release.reason_code == "safety_regression"


async def test_rollback_reactivates_previous_approved_release(session, active_release, previous_release):
    rolled_back = await rollback_release(
        session,
        target_release_id=previous_release.id,
        actor_id="model-reviewer",
        reason="线上安全样本退化",
    )
    assert rolled_back.status == "active"
    assert active_release.status == "rolled_back"
    assert await has_audit_event(session, "model_release.rolled_back")
```

- [ ] **Step 6: 运行并确认发布门禁尚未实现**

Run: `cd platform/backend && uv run pytest tests/unit/test_golden_review.py tests/integration/test_release_gate.py -v`
Expected: FAIL because dual review, adjudication and blocking gates are missing.

- [ ] **Step 7: 实现审核、仲裁和门禁**

两名审核者独立提交；一致时可进入 `approved`，不一致时进入 `disputed` 并要求第三人仲裁。证据引用不可解析、隐私泄漏、聚类成员重复或安全样本退化均为阻断门禁。`rollback_release()` 只允许回到曾通过门禁的版本，并在同一事务中停用当前版本、启用目标版本和写审计事件。

```python
BLOCKING_GATES = {
    "unresolved_evidence": lambda result: result.unresolved_evidence > 0,
    "privacy_leak": lambda result: result.privacy_leaks > 0,
    "duplicate_membership": lambda result: result.duplicate_primary_memberships > 0,
    "safety_regression": lambda result: result.safety_false_negatives > 0,
}
```

- [ ] **Step 8: 运行评测测试并导出待审核清单**

Run: `cd platform/backend && uv run pytest tests/unit/test_stratified_sample.py tests/unit/test_golden_review.py tests/integration/test_release_gate.py -v`
Expected: PASS; 100 records remain pending human review and are not labeled as golden truth.

- [ ] **Step 9: 提交质量中心后端**

```bash
git add platform/backend
git commit -m "feat: 建立黄金样本与发布门禁" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 7: 实现企业身份、产品线权限和模型外发网关

**Files:**
- Create: `platform/backend/src/bearvoice/security/auth.py`
- Create: `platform/backend/src/bearvoice/security/model_gateway.py`
- Create: `platform/backend/tests/unit/test_permissions.py`
- Create: `platform/backend/tests/unit/test_model_gateway.py`
- Create: `platform/backend/tests/integration/test_product_scope.py`

**Interfaces:**
- Consumes: `Settings`、`Permission`、产品线字段、审计事件。
- Produces: `Principal`、`require_permission(permission)`、`assert_product_scope()`、`ModelGateway.generate(request)`。

- [ ] **Step 1: 写默认拒绝模型外发失败测试**

```python
import pytest
from bearvoice.security.model_gateway import ModelEgressDisabled, ModelGateway


async def test_model_gateway_denies_egress_without_admin_configuration():
    with pytest.raises(ModelEgressDisabled):
        await ModelGateway.from_settings().generate({"purpose": "cluster_label", "text": "脱敏文本"})
```

- [ ] **Step 2: 运行并确认网关缺失**

Run: `cd platform/backend && uv run pytest tests/unit/test_model_gateway.py -v`
Expected: FAIL because model gateway does not exist.

- [ ] **Step 3: 实现提供商白名单、用途白名单和脱敏前置检查**

只有 `model_egress_enabled=True`、提供商在批准名单、用途在批准名单、载荷通过隐私门禁时才调用适配器。网关日志只保存哈希、提供商、模型、用途、令牌计数和运行 ID。

```python
async def generate(self, request: ModelRequest) -> ModelResponse:
    if not self.settings.model_egress_enabled:
        raise ModelEgressDisabled()
    self.policy.assert_provider(request.provider)
    self.policy.assert_purpose(request.purpose)
    self.privacy_gate.assert_sanitized(request.payload)
    return await self.adapters[request.provider].generate(request)
```

- [ ] **Step 4: 运行模型网关测试并确认通过**

Run: `cd platform/backend && uv run pytest tests/unit/test_model_gateway.py -v`
Expected: PASS; egress is denied by default.

- [ ] **Step 5: 写角色与产品线越权失败测试**

```python
async def test_product_manager_cannot_read_another_product_line(api_client, product_manager_token):
    response = await api_client.get(
        "/api/opportunities?product_line=洗衣机",
        headers={"Authorization": f"Bearer {product_manager_token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "无权访问该产品线"
```

- [ ] **Step 6: 运行并确认权限检查尚未实现**

Run: `cd platform/backend && uv run pytest tests/unit/test_permissions.py tests/integration/test_product_scope.py -v`
Expected: FAIL because Principal and product scope checks are missing.

- [ ] **Step 7: 实现 OIDC Principal、权限矩阵和数据范围检查**

生产只接受经配置 issuer/audience 验证的 OIDC JWT；测试和本地开发使用独立 `dev_auth_enabled` 配置与固定测试签名，不存在无认证的生产回退。所有列表查询先应用产品线范围，再执行聚合。

```python
def require_product_scope(product_line: str, principal: Principal) -> None:
    if Permission.READ_ALL_PRODUCT_LINES in principal.permissions:
        return
    if product_line not in principal.product_lines:
        raise HTTPException(status_code=403, detail="无权访问该产品线")
```

- [ ] **Step 8: 运行安全测试**

Run: `cd platform/backend && uv run pytest tests/unit/test_permissions.py tests/unit/test_model_gateway.py tests/integration/test_product_scope.py -v`
Expected: PASS; unauthorized and out-of-scope access return 401/403 without disclosing object existence.

- [ ] **Step 9: 提交安全与模型网关**

```bash
git add platform/backend
git commit -m "feat: 增加企业权限与模型外发控制" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 8: 提供企业 API、赛事投影和历史报告对账

**Files:**
- Create: `platform/backend/src/bearvoice/modules/reporting/queries.py`
- Create: `platform/backend/src/bearvoice/api/router.py`
- Create: `platform/backend/src/bearvoice/api/routes/dashboard.py`
- Create: `platform/backend/src/bearvoice/api/routes/sources.py`
- Create: `platform/backend/src/bearvoice/api/routes/taxonomy.py`
- Create: `platform/backend/src/bearvoice/api/routes/opportunities.py`
- Create: `platform/backend/src/bearvoice/api/routes/evaluation.py`
- Create: `platform/backend/src/bearvoice/api/routes/admin.py`
- Create: `platform/backend/tests/integration/test_dashboard_api.py`
- Create: `platform/backend/tests/integration/test_evidence_api.py`
- Create: `platform/backend/tests/integration/test_legacy_reconciliation.py`

**Interfaces:**
- Consumes: Tasks 2-7 领域服务与权限依赖。
- Produces: `/api/dashboard`、`/api/taxonomies`、`/api/opportunities`、`/api/evidence/{id}`、`/api/evaluations`、`DashboardSnapshot`。

- [ ] **Step 1: 写赛事驾驶舱对账失败测试**

```python
async def test_kettle_dashboard_reconciles_with_verified_legacy_report(api_client, management_token):
    response = await api_client.get(
        "/api/dashboard?product=养生壶&view=competition",
        headers={"Authorization": f"Bearer {management_token}"},
    )
    payload = response.json()
    assert payload["total_voices"] == 370
    assert payload["actionable_voices"] == 254
    assert len(payload["top_clusters"]) == 10
    assert len(payload["opportunities"]) == 9
    assert payload["coverage"] == {"channel": "天猫", "days": 3, "trend_allowed": False}
```

- [ ] **Step 2: 运行并确认 API 缺失**

Run: `cd platform/backend && uv run pytest tests/integration/test_dashboard_api.py -v`
Expected: FAIL with 404 or missing route.

- [ ] **Step 3: 实现统一查询投影和路由**

`DashboardSnapshot` 同时返回绝对数、占比、分母、时间范围、来源和数据限制。赛事视图与企业视图共用查询，只改变显示字段和权限，不维护第二套数字。

```python
class DashboardSnapshot(BaseModel):
    total_voices: int
    actionable_voices: int
    signals: list[SignalMetric]
    top_clusters: list[ClusterMetric]
    opportunities: list[OpportunitySummary]
    coverage: CoverageBoundary


@router.get("/dashboard", response_model=DashboardSnapshot)
async def dashboard(product: str, view: DashboardView, principal=Depends(current_principal)):
    require_product_scope(product, principal)
    return await get_dashboard_snapshot(product=product, view=view, principal=principal)
```

- [ ] **Step 4: 运行驾驶舱 API 测试并确认通过**

Run: `cd platform/backend && uv run pytest tests/integration/test_dashboard_api.py -v`
Expected: PASS with 370/254/10/9 and explicit data boundary.

- [ ] **Step 5: 写证据下钻失败测试**

```python
async def test_evidence_response_contains_sanitized_quote_and_provenance(api_client, reviewer_token):
    response = await api_client.get(
        "/api/evidence/fixture-evidence",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    body = response.json()
    assert body["quote"] == "[地址已脱敏]"
    assert body["voice_record_id"]
    assert body["source"] == "天猫咨询"
    assert body["analysis_run_id"]
```

- [ ] **Step 6: 运行并确认证据 API 与对账尚未实现**

Run: `cd platform/backend && uv run pytest tests/integration/test_evidence_api.py tests/integration/test_legacy_reconciliation.py -v`
Expected: FAIL because evidence projection and reconciliation are missing.

- [ ] **Step 7: 实现证据和修订 API，并完成 Markdown 对账**

历史对账逐项比较 API 投影与 `聚类明细.json`；差异输出具体字段并使测试失败。API 不返回未脱敏原文或对象存储内部路径。

```python
def reconcile_legacy_baseline(snapshot: DashboardSnapshot) -> None:
    expected = {"total": 370, "actionable": 254, "clusters": 10, "opportunities": 9}
    actual = snapshot.model_dump(include={"total_voices", "actionable_voices"})
    if (snapshot.total_voices, snapshot.actionable_voices, len(snapshot.top_clusters), len(snapshot.opportunities)) != (370, 254, 10, 9):
        raise ReconciliationError(expected=expected, actual=actual)
```

`sources` 路由返回批次质量、隔离数和来源健康度；`admin` 路由只返回无密钥的 OIDC、模型外发和保留策略状态。

- [ ] **Step 8: 运行 API 与对账测试**

Run: `cd platform/backend && uv run pytest tests/integration/test_dashboard_api.py tests/integration/test_evidence_api.py tests/integration/test_legacy_reconciliation.py -v`
Expected: PASS with exact 370/254/10/9 baseline.

- [ ] **Step 9: 提交 API 和投影**

```bash
git add platform/backend
git commit -m "feat: 提供机会决策与证据 API" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 9: 构建赛事决策驾驶舱和企业导航

**Files:**
- Create: `platform/frontend/src/api/client.ts`
- Create: `platform/frontend/src/api/types.ts`
- Create: `platform/frontend/src/app/router.tsx`
- Create: `platform/frontend/src/pages/DashboardPage.tsx`
- Create: `platform/frontend/src/pages/SourcesPage.tsx`
- Create: `platform/frontend/src/components/KpiStrip.tsx`
- Create: `platform/frontend/src/components/SignalComposition.tsx`
- Create: `platform/frontend/src/components/ClusterRanking.tsx`
- Create: `platform/frontend/src/components/OpportunityList.tsx`
- Create: `platform/frontend/src/components/DataBoundaryNotice.tsx`
- Create: `platform/frontend/src/pages/SystemPage.tsx`
- Create: `platform/frontend/src/styles/tokens.css`
- Create: `platform/frontend/tests/DashboardPage.test.tsx`
- Create: `platform/frontend/e2e/competition-dashboard.spec.ts`

**Interfaces:**
- Consumes: Task 8 `DashboardSnapshot` JSON。
- Produces: 可切换赛事/企业视图的 `DashboardPage`，以及可点击的聚类和机会入口。

- [ ] **Step 1: 写首屏决策信息失败测试**

```tsx
test("competition view leads with evidence-backed decision context", async () => {
  render(<DashboardPage initialView="competition" />);
  expect(await screen.findByText("370")).toBeVisible();
  expect(screen.getByText("254 条含改进信号")).toBeVisible();
  expect(screen.getByText("仅天猫咨询 · 2026-08-01 至 08-03 · 不支持趋势判断")).toBeVisible();
  expect(screen.getByRole("heading", { name: "产品机会" })).toBeVisible();
});
```

- [ ] **Step 2: 运行并确认页面缺失**

Run: `cd platform/frontend && bun test tests/DashboardPage.test.tsx`
Expected: FAIL because dashboard components do not exist.

- [ ] **Step 3: 实现 API 类型、KPI、信号构成和横向排序条形图**

`ClusterRanking` 使用从零开始的横向条形图，直接标注条数和占比；不为单类别轴创建冗余图例。`SignalComposition` 同时显示绝对数和占比。所有图表标题为中性描述，副标题包含分母、时间和来源。

```tsx
const clusterOption = {
  xAxis: { type: "value", min: 0, name: "原声条数" },
  yAxis: { type: "category", data: clusters.map((item) => item.name) },
  series: [{ type: "bar", data: clusters.map((item) => item.count), itemStyle: { color: "#356AE6" } }],
};
```

- [ ] **Step 4: 实现机会列表和数据边界提示**

机会按安全覆盖、审核状态、影响面和实施难度分组，不用咨询量单独决定顺序。三天数据限制固定显示在首屏与图表副标题。

```tsx
<DataBoundaryNotice
  channel="天猫咨询"
  dateRange="2026-08-01 至 08-03"
  sampleSize={370}
  message="仅支持截面分析，不支持趋势、同比或环比判断"
/>
```

同一任务补充 `SourcesPage` 的批次质量表和 `SystemPage` 的只读安全状态；两页不显示凭据、原文件路径或模型提示正文。

`router.tsx` 固定六个企业入口：驾驶舱、原声数据、聚类治理、机会中心、质量中心和系统管理；无权限页面不出现在导航中，直接访问仍由后端 403 兜底。

- [ ] **Step 5: 运行前端单元和端到端首屏测试**

Run: `cd platform/frontend && bun test tests/DashboardPage.test.tsx`
Expected: PASS.

Run: `cd platform/frontend && bunx playwright test e2e/competition-dashboard.spec.ts --project=chromium`
Expected: PASS; screenshot shows KPI, Top10, opportunities and data boundary without clipping at 1440×900 and 390×844.

- [ ] **Step 6: 提交决策驾驶舱**

```bash
git add platform/frontend
git commit -m "feat: 构建赛事与企业决策驾驶舱" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 10: 构建证据下钻、聚类治理、机会审核和质量中心界面

**Files:**
- Create: `platform/frontend/src/pages/TaxonomyPage.tsx`
- Create: `platform/frontend/src/pages/OpportunityPage.tsx`
- Create: `platform/frontend/src/pages/EvaluationPage.tsx`
- Create: `platform/frontend/src/components/EvidenceDrawer.tsx`
- Create: `platform/frontend/src/components/TaxonomyRevisionForm.tsx`
- Create: `platform/frontend/src/components/OpportunityReviewPanel.tsx`
- Create: `platform/frontend/src/components/GoldenReviewQueue.tsx`
- Create: `platform/frontend/tests/ReviewFlows.test.tsx`
- Create: `platform/frontend/e2e/review-opportunity.spec.ts`

**Interfaces:**
- Consumes: Task 8 taxonomy、opportunity、evidence、evaluation API。
- Produces: 人工可操作的治理、审核、证据和评测工作区。

- [ ] **Step 1: 写证据与审核失败测试**

```tsx
test("reviewer can inspect evidence before accepting an opportunity", async () => {
  render(<OpportunityPage opportunityId="glass-crack" />);
  await userEvent.click(await screen.findByRole("button", { name: "查看 13 条证据" }));
  expect(screen.getByText("亲，我买的玻璃壶炸了一个")).toBeVisible();
  expect(screen.getByText("来源：天猫咨询")).toBeVisible();
  expect(screen.getByRole("button", { name: "接受机会" })).toBeDisabled();
  await userEvent.type(screen.getByLabelText("审核理由"), "涉及人身安全，转品控复核");
  expect(screen.getByRole("button", { name: "接受机会" })).toBeEnabled();
});
```

- [ ] **Step 2: 运行并确认审核界面缺失**

Run: `cd platform/frontend && bun test tests/ReviewFlows.test.tsx`
Expected: FAIL because pages and components do not exist.

- [ ] **Step 3: 实现证据抽屉和聚类治理表单**

证据抽屉显示脱敏原声、来源、日期、运行版本和支持/反对方向。治理表单要求选择改名/合并/拆分/移出/恢复、填写理由并预览新版本；不提供“覆盖当前版本”操作。

```tsx
<EvidenceDrawer
  quote={evidence.quote}
  source={evidence.source}
  occurredAt={evidence.occurredAt}
  analysisRunId={evidence.analysisRunId}
  direction={evidence.direction}
/>
```

- [ ] **Step 4: 实现机会审核和黄金样本队列**

接受、重大修改和驳回都必须填写理由；安全机会显示品控复核提醒。黄金样本页面明确区分“模型建议”“审核者一”“审核者二”“仲裁结果”，待审核样本不显示为黄金真相。

```tsx
<OpportunityReviewPanel
  requiresReason
  safetyEscalation={opportunity.safetyLevel === "critical"}
  decisions={["accept", "revise", "reject"]}
  actionItemFields={["owner", "dueDate", "externalReference"]}
  competitorEvidence={opportunity.competitorEvidence}
/>
```

- [ ] **Step 5: 运行单元和端到端审核测试**

Run: `cd platform/frontend && bun test tests/ReviewFlows.test.tsx`
Expected: PASS.

Run: `cd platform/frontend && bunx playwright test e2e/review-opportunity.spec.ts --project=chromium`
Expected: PASS; audit timeline contains the review decision and actor.

- [ ] **Step 6: 提交人工治理界面**

```bash
git add platform/frontend
git commit -m "feat: 增加证据与人工治理工作区" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

### Task 11: 完成全链路验证、兼容导出和运维交接

**Files:**
- Modify: `platform/README.md`
- Modify: `README.md`
- Modify: `scripts/README.md`
- Modify: `.gitignore`
- Modify: `state/board.md`
- Modify: `state/changelog.md`
- Create: `platform/backend/tests/e2e/test_kettle_vertical_slice.py`
- Create: `platform/backend/src/bearvoice/modules/reporting/export.py`
- Create: `platform/backend/src/bearvoice/modules/reporting/templates/kettle_report.md.j2`
- Create: `platform/backend/src/bearvoice/storage.py`
- Create: `platform/backend/tests/integration/test_markdown_export.py`
- Create: `platform/backend/tests/unit/test_storage.py`
- Create: `platform/frontend/e2e/mobile-and-print.spec.ts`
- Create: `platform/licenses.md`

**Interfaces:**
- Consumes: Tasks 1-10 所有可运行单元。
- Produces: 一条经验证的养生壶纵向链路、兼容 Markdown 报告、依赖许可证清单、运行与恢复手册。

- [ ] **Step 1: 写纵向链路失败测试**

```python
async def test_kettle_vertical_slice_without_model_calls(system_client, legacy_repo):
    run = await system_client.import_legacy(legacy_repo, cache_only=True)
    assert run.extract_cache_hits == 10
    assert run.model_calls == 0

    dashboard = await system_client.dashboard(product="养生壶")
    assert (dashboard.total_voices, dashboard.actionable_voices) == (370, 254)

    opportunity = await system_client.accept_opportunity(
        slug="玻璃壶身开裂炸裂",
        reason="涉及安全风险，转品控复核",
    )
    assert opportunity.status == "accepted"
    assert opportunity.audit_events[-1].action == "opportunity.accepted"
```

- [ ] **Step 2: 运行并确认完整链路尚未贯通**

Run: `cd platform/backend && uv run pytest tests/e2e/test_kettle_vertical_slice.py -v`
Expected: FAIL at the first unimplemented integration boundary, not by calling an external model.

- [ ] **Step 3: 写兼容导出和对象存储失败测试**

先写兼容导出和本地对象存储的失败测试：

```python
def test_markdown_export_reconciles_with_dashboard_snapshot(tmp_path, kettle_snapshot):
    path = export_markdown(kettle_snapshot, tmp_path / "报告.md")
    text = path.read_text(encoding="utf-8")
    assert "本品类 **370 条**" in text
    assert "产品改进信号 **254 条" in text


def test_filesystem_object_store_rejects_path_escape(tmp_path):
    store = FilesystemObjectStore(root=tmp_path / "objects")
    with pytest.raises(UnsafeObjectKey):
        store.put("../outside.txt", b"secret")
```

- [ ] **Step 4: 运行并确认导出和对象存储尚未实现**

Run: `cd platform/backend && uv run pytest tests/integration/test_markdown_export.py tests/unit/test_storage.py -v`
Expected: FAIL because export and storage adapters do not exist.

- [ ] **Step 5: 实现运行入口、兼容报告、本地对象存储和许可证记录**

`platform/README.md` 写明本地启动、数据迁移、工作流恢复、模型外发开启条件、备份和回退。根 `README.md` 增加企业平台入口但不复制设计全文。`platform/licenses.md` 记录直接依赖名称、版本、许可证和用途；发现 AGPL 依赖时阻止合入并替换。

```python
def export_markdown(snapshot: DashboardSnapshot, destination: Path) -> Path:
    rendered = render_template("kettle_report.md.j2", snapshot=snapshot)
    destination.write_text(rendered.rstrip() + "\n", encoding="utf-8")
    return destination
```

开发环境对象存储使用 `FilesystemObjectStore` 并限制在 `platform/.data/`；生产配置只接受企业批准的 S3 端点。`platform/.data/` 加入 `.gitignore`，不引入 MinIO 或其他 AGPL 服务。

- [ ] **Step 6: 运行纵向链路、导出和对象存储测试**

Run: `cd platform/backend && uv run pytest tests/e2e/test_kettle_vertical_slice.py tests/integration/test_markdown_export.py tests/unit/test_storage.py -v`
Expected: PASS; the vertical slice makes zero model calls and the export reconciles.

- [ ] **Step 7: 运行完整自动验证**

Run: `python3 -m unittest discover -s tests -v`
Expected: existing 4 tests PASS.

Run: `cd platform/backend && uv run pytest -v`
Expected: all backend unit, integration, workflow and e2e tests PASS with zero failures.

Run: `cd platform/frontend && bun test`
Expected: all frontend unit tests PASS.

Run: `cd platform/frontend && bunx playwright test --project=chromium`
Expected: all desktop, mobile, evidence, review and print tests PASS.

Run: `cd platform && docker compose config --quiet`
Expected: exit 0.

Run: `gitleaks detect --source . --redact --no-banner`
Expected: no leaks found.

- [ ] **Step 8: 进行最终视觉检查**

启动本地平台，分别截取 1440×900、390×844 和打印预览。人工检查：Top10 长标签不截断、条形图零起点、样本分母和三天限制可见、颜色不是唯一状态通道、证据抽屉可读、移动端无横向溢出。任何一项失败都先修正并重跑 Playwright。

- [ ] **Step 9: 更新状态和变更记录**

`state/board.md` 只保留当前已完成、剩余和阻塞事项；`state/changelog.md` 记录平台从报告管线升级到企业机会闭环的原因和对使用者的影响。不得写入密钥、令牌或客户个人信息。

```text
board 当前状态：企业纵向链路已验证；正式 SSO、生产 Kubernetes、外部 PLM 和新增平台数据源仍未接通。
changelog 里程碑：从报告生成管线升级为证据—审核—机会—行动—评测闭环。
```

- [ ] **Step 10: 提交经验证的纵向链路**

```bash
git add README.md scripts/README.md platform state/board.md state/changelog.md
git commit -m "feat: 贯通企业产品机会纵向链路" -m "Change-By:      ai\nAgent:          Codex\nModel:          GPT-5\nSuggested-By:   human\nCo-authored-by: lian <lian@liandeMacBook-Air.local>"
```

---

## Spec Coverage Self-Review

| 设计规格要求 | 计划任务 |
|---|---|
| 单企业私有化、模块化单体和可重复工具链 | Task 1、Task 2、Task 11 |
| 统一来源、原声、信号、分类法、机会、审核、行动和评测模型 | Task 2 |
| 文件接入、幂等去重、中文隐私门禁和现有缓存迁移 | Task 3 |
| 可暂停、恢复、重试、缓存复用和机器可读诊断 | Task 4 |
| OpenTelemetry 运行关联且不记录提示词或客户文本 | Task 4 |
| 聚类改名、合并、拆分、异常项和历史不可变 | Task 5 |
| 机会证据门槛、安全覆盖、审核、负责人和结果回收 | Task 5、Task 10 |
| 100 条待人工定标、双人审核、仲裁、发布和回退门禁 | Task 6、Task 10 |
| OIDC、角色、产品线数据范围和模型外发控制 | Task 7 |
| 来源健康、证据下钻、竞品证据和企业 API | Task 8、Task 10 |
| 赛事 A/B/C 决策视图和企业运营导航 | Task 8、Task 9 |
| 数据边界、诚实图表、桌面/移动/打印视觉验证 | Task 9、Task 11 |
| Markdown 兼容、S3 接口、本地安全存储、许可证和运维交接 | Task 11 |

未纳入本轮实现的正式 SSO 联调、生产 Kubernetes、PLM 写回、其他平台连接器和自动竞品采集，均与设计规格第 13 节边界一致；本轮提供对应接口和安全默认值，不伪装成已接通。

---

## Plan Completion Criteria

计划只有在以下条件全部满足时才算执行完成：

- 11 个任务均按红—绿—重构流程执行，并保留目标测试先失败的证据。
- 养生壶迁移严格命中 10 个抽取缓存，模型调用数为 0。
- 数据库与驾驶舱对账为 370 条原声、254 条改进信号、10 个聚类、9 条历史建议。
- 聚类治理不修改历史版本；机会审核和状态变化均有审计事件。
- 100 条样本保持待人工定标，双人审核与安全回归门禁可运行。
- 未配置管理员批准的模型提供商时，任何外发请求都被拒绝。
- 后端、前端、Temporal 工作流、端到端、权限、数据对账、敏感信息和视觉检查均取得当次运行证据。
- 现有 CLI 和 Markdown 报告继续可用，且没有推送远端。
