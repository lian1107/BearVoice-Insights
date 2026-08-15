import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.models import (
    AnalysisRun,
    AuditEvent,
    Cluster,
    ClusterMembership,
    IngestionBatch,
    Opportunity,
    OpportunityEvidence,
    Signal,
    Source,
    TaxonomyVersion,
    VoiceRecord,
)


@dataclass(frozen=True)
class BaselineResult:
    analysis_run_id: uuid.UUID
    signal_count: int
    cluster_count: int
    opportunity_count: int
    status: str
    reused: bool = False


@dataclass(frozen=True)
class ThemeRule:
    name: str
    signal_type: str
    object_name: str
    keywords: tuple[str, ...]
    opportunity_title: str
    recommended_action: str
    safety: bool = False


THEME_RULES = (
    ThemeRule(
        "安全与高温风险",
        "缺陷",
        "安全防护",
        ("炸", "爆", "漏电", "冒烟", "起火", "烫伤", "烧焦", "危险"),
        "优先排查高温与电气安全风险",
        "建立失效样本复核，核查温控、绝缘、防干烧与高温接触防护。",
        True,
    ),
    ThemeRule(
        "故障与可靠性",
        "缺陷",
        "核心功能",
        ("故障", "坏了", "失灵", "不工作", "不启动", "报错", "错误码", "e0", "e1", "e2", "e3"),
        "提升核心功能可靠性与故障可诊断性",
        "按故障模式回溯批次与部件，并补齐错误码解释和安全复位指引。",
    ),
    ThemeRule(
        "清洗与异味",
        "体验",
        "清洁结构",
        ("清洗", "清洁", "洗不", "污垢", "水垢", "异味", "味道", "发臭"),
        "降低清洗死角与材料异味",
        "复核可拆洗结构、密封件和材料气味，给出按部件拆洗指引。",
    ),
    ThemeRule(
        "加热与性能",
        "缺陷",
        "加热性能",
        ("加热", "不热", "烧不开", "煮不", "太慢", "保温", "温度"),
        "改善加热、烹煮与保温表现",
        "按场景验证升温时间、温控偏差和保温曲线，明确容量与程序边界。",
    ),
    ThemeRule(
        "使用与操作理解",
        "咨询",
        "交互与说明",
        ("怎么用", "如何用", "怎么操作", "说明书", "按键", "预约", "功能键", "不会用"),
        "降低首次使用和功能操作成本",
        "优化面板反馈，并提供按型号匹配的一页式快速上手说明。",
    ),
    ThemeRule(
        "容量与选购预期",
        "需求",
        "容量规格",
        ("容量", "几升", "多大", "尺寸", "够用", "几个人", "型号"),
        "让容量与适用人数更容易判断",
        "统一商品页、包装和说明书的容量口径，并增加人数与场景建议。",
    ),
    ThemeRule(
        "配件与结构",
        "需求",
        "配件结构",
        ("配件", "壶盖", "盖子", "滤网", "底座", "密封圈", "电源线"),
        "完善易损配件和关键结构体验",
        "核查配件耐久、拆装与补购路径，统一型号兼容信息。",
    ),
    ThemeRule(
        "噪音与感知体验",
        "体验",
        "运行体验",
        ("噪音", "声音大", "太响", "震动", "晃动"),
        "降低运行噪音与异常振动",
        "复核运行工况、装配公差和减振结构，并明确正常声响边界。",
    ),
    ThemeRule(
        "售后与物流",
        "售后",
        "服务履约",
        ("退货", "换货", "退款", "客服", "售后", "物流", "快递", "破损"),
        "缩短售后判断与问题闭环时间",
        "按问题类型提供明确凭证、处理时限和备件或换货路径。",
    ),
)

FALLBACK_RULE = ThemeRule(
    "其他产品反馈",
    "咨询",
    "未分类",
    (),
    "复核未分类反馈并补充主题规则",
    "由产品与客服共同抽样复核，判断是否需要新增主题或调整现有口径。",
)


def _classify(text: str) -> ThemeRule:
    lowered = text.lower()
    return next(
        (rule for rule in THEME_RULES if any(word in lowered for word in rule.keywords)),
        FALLBACK_RULE,
    )


async def _result_for_run(
    session: AsyncSession,
    run: AnalysisRun,
    *,
    reused: bool,
) -> BaselineResult:
    signal_count = int(
        await session.scalar(
            select(func.count()).select_from(Signal).where(Signal.analysis_run_id == run.id)
        )
        or 0
    )
    cluster_count = int(
        await session.scalar(
            select(func.count(func.distinct(ClusterMembership.cluster_id)))
            .select_from(ClusterMembership)
            .join(Signal, Signal.id == ClusterMembership.signal_id)
            .where(Signal.analysis_run_id == run.id)
        )
        or 0
    )
    opportunity_count = int(
        await session.scalar(
            select(func.count(func.distinct(OpportunityEvidence.opportunity_id)))
            .select_from(OpportunityEvidence)
            .join(Signal, Signal.id == OpportunityEvidence.signal_id)
            .where(Signal.analysis_run_id == run.id)
        )
        or 0
    )
    return BaselineResult(
        analysis_run_id=run.id,
        signal_count=signal_count,
        cluster_count=cluster_count,
        opportunity_count=opportunity_count,
        status=str((run.stage_status or {}).get("status", "pending_review")),
        reused=reused,
    )


async def run_local_baseline(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    product: str,
    actor_id: str,
) -> BaselineResult:
    """Create a transparent, offline baseline for an uploaded CSV.

    This intentionally does not claim model inference. Every signal is assigned by
    a versioned keyword rule and every generated opportunity remains pending review.
    """

    batch = await session.get(IngestionBatch, batch_id)
    if batch is None:
        raise LookupError("导入批次不存在")
    previous_runs = list(
        await session.scalars(
            select(AnalysisRun)
            .where(
                AnalysisRun.dataset_hash == batch.file_hash,
                AnalysisRun.model_version == "local-rule-baseline-v1",
            )
            .order_by(AnalysisRun.created_at.desc())
        )
    )
    for previous in previous_runs:
        parameters = previous.parameters or {}
        if (
            parameters.get("product") == product
            and parameters.get("ingestion_batch_id") == str(batch.id)
        ):
            return await _result_for_run(session, previous, reused=True)

    records = list(
        await session.scalars(
            select(VoiceRecord)
            .where(
                VoiceRecord.ingestion_batch_id == batch.id,
                VoiceRecord.product == product,
            )
            .order_by(VoiceRecord.id)
        )
    )
    if not records:
        raise ValueError("该批次没有可供分析的新原声，请检查产品名称或重复数据")

    started = time.monotonic()
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash=batch.file_hash,
        code_version="local-baseline-v1",
        model_version="local-rule-baseline-v1",
        prompt_version=None,
        parameters={
            "ingestion_batch_id": str(batch.id),
            "product": product,
            "analysis_mode": "offline_keyword_rules",
            "model_calls": 0,
        },
        stage_status={"status": "running", "current_phase": "extract"},
        cost_amount=0,
    )
    session.add(run)
    await session.flush()

    taxonomy = TaxonomyVersion(
        id=uuid.uuid4(),
        product_scope=product,
        origin="local_rule_baseline",
        status="draft",
    )
    session.add(taxonomy)
    await session.flush()

    rules_by_name = {rule.name: rule for rule in (*THEME_RULES, FALLBACK_RULE)}
    assignments: dict[str, list[tuple[VoiceRecord, Signal]]] = defaultdict(list)
    for record in records:
        rule = _classify(record.normalized_text)
        signal = Signal(
            id=uuid.uuid4(),
            analysis_run_id=run.id,
            voice_record_id=record.id,
            signal_index=0,
            signal_type=rule.signal_type,
            object_name=rule.object_name,
            evidence_text=record.normalized_text,
            confidence=0.72 if rule is not FALLBACK_RULE else 0.35,
            calibration_status="rule_baseline_pending_review",
            is_outlier=rule is FALLBACK_RULE,
        )
        session.add(signal)
        assignments[rule.name].append((record, signal))
    await session.flush()

    clusters_by_name: dict[str, Cluster] = {}
    for name, members in sorted(assignments.items(), key=lambda item: -len(item[1])):
        rule = rules_by_name[name]
        cluster = Cluster(
            id=uuid.uuid4(),
            taxonomy_version_id=taxonomy.id,
            original_name=name,
            current_name=name,
            description=f"由本地规则基线识别，{len(members)} 条原声，发布前需人工复核。",
            primary_signal_type=rule.signal_type,
            keywords=list(rule.keywords),
            representative_record_ids=[str(record.id) for record, _ in members[:3]],
            is_outlier=rule is FALLBACK_RULE,
            status="active",
        )
        session.add(cluster)
        clusters_by_name[name] = cluster
        session.add_all(
            ClusterMembership(
                id=uuid.uuid4(),
                taxonomy_version_id=taxonomy.id,
                cluster_id=cluster.id,
                signal_id=signal.id,
                assignment_status="rule_baseline_pending_review",
            )
            for _, signal in members
        )
    await session.flush()

    ranked = sorted(
        assignments.items(),
        key=lambda item: (not rules_by_name[item[0]].safety, -len(item[1])),
    )
    opportunity_count = 0
    for name, members in ranked[:6]:
        rule = rules_by_name[name]
        count = len(members)
        percentage = round(count / len(records) * 100, 1)
        severity = "P0" if rule.safety else ("P1" if percentage >= 10 else "P2")
        opportunity = Opportunity(
            id=uuid.uuid4(),
            opportunity_type="improvement",
            title=rule.opportunity_title,
            problem=f"{count} 条原声命中“{name}”，占本批次 {percentage}%。",
            scenario="上传批次的离线规则基线分析",
            audience="产品、研发、质量与客服团队",
            product=product,
            component=rule.object_name,
            impact_scope=f"{count} 条，占 {percentage}%",
            severity=severity,
            safety_level="critical" if rule.safety else "normal",
            recommended_action=rule.recommended_action,
            priority_override="safety" if rule.safety else None,
            status="pending_review",
        )
        session.add(opportunity)
        await session.flush()
        session.add_all(
            OpportunityEvidence(
                id=uuid.uuid4(),
                opportunity_id=opportunity.id,
                voice_record_id=record.id,
                signal_id=signal.id,
                evidence_direction="support",
                reviewed=False,
            )
            for record, signal in members[:20]
        )
        opportunity_count += 1

    source = await session.get(Source, batch.source_id)
    if source is not None:
        source.last_success_at = datetime.now(UTC)
        source.last_error = None
        source.connection_status = "verified"
    run.duration_ms = int((time.monotonic() - started) * 1000)
    run.stage_status = {
        "status": "pending_review",
        "current_phase": "human_review",
        "completed_phases": [
            "validate",
            "deduplicate",
            "privacy_gate",
            "extract",
            "cluster",
            "draft_opportunities",
            "quality_gate",
        ],
        "analysis_mode": "offline_keyword_rules",
        "model_calls": 0,
        "notice": "本地规则基线，主题与机会发布前必须人工复核",
    }
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action="analysis.local_baseline_created",
            subject_type="analysis_run",
            subject_id=run.id,
            after_state={
                "batch_id": str(batch.id),
                "product": product,
                "records": len(records),
                "clusters": len(clusters_by_name),
                "opportunities": opportunity_count,
                "model_calls": 0,
            },
            reason="CSV 上传后生成可追溯的离线规则基线，等待人工复核",
        )
    )
    await session.flush()
    return BaselineResult(
        analysis_run_id=run.id,
        signal_count=len(records),
        cluster_count=len(clusters_by_name),
        opportunity_count=opportunity_count,
        status="pending_review",
    )
