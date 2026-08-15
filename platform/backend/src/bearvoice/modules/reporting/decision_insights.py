import hashlib
import uuid
from collections import defaultdict
from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.models import AnalysisRun, Signal, VoiceRecord


RISK_PRIORITY = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}
MISSING_VALUE = "未提供"
MAX_DECISION_CARDS = 12


class DimensionValue(BaseModel):
    value: str
    count: int
    percentage: float
    denominator: int


class InsightCoverage(BaseModel):
    total_voices: int
    total_signals: int
    period_start: date | None
    period_end: date | None
    days: int
    trend_allowed: bool
    channels: list[str]
    has_business_denominator: Literal[False] = False
    denominator_notice: str
    limitations: list[str]


class InsightPattern(BaseModel):
    pattern_id: str
    signal_type: str
    object_name: str
    issue: str
    risk_level: str
    voice_count: int
    share: float
    denominator: int
    channels: list[str]
    skus: list[str]
    batches: list[str]
    versions: list[str]
    lifecycle_stages: list[str]
    scenarios: list[str]
    latent_needs: list[str]
    root_cause_hypotheses: list[str]
    improvement_directions: list[str]
    validation_suggestions: list[str]
    missing_information: list[str]
    supporting_evidence_ids: list[uuid.UUID]
    conflict_notice: str | None


class DecisionCard(BaseModel):
    card_id: str
    problem: str
    why_now: str
    evidence_level: Literal["directional", "local_descriptive"]
    risk_level: str
    voice_count: int
    share: float
    recommended_direction: str
    validation_plan: str
    human_owner: str
    human_review_required: Literal[True] = True
    forbidden_claims: list[str]
    priority_explanation: str
    supporting_evidence_ids: list[uuid.UUID]


class InsightGovernance(BaseModel):
    scope_notice: str
    causality_notice: str
    financial_notice: str
    human_review_notice: str


class DecisionInsightResponse(BaseModel):
    product: str
    analysis_run_id: uuid.UUID
    coverage: InsightCoverage
    dimensions: dict[str, list[DimensionValue]]
    patterns: list[InsightPattern]
    decision_cards: list[DecisionCard]
    governance: InsightGovernance


def _clean(value: object, *, fallback: str = MISSING_VALUE) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _clean(item, fallback=""))]


def _unique(values: list[str], *, include_missing: bool = False) -> list[str]:
    result = {
        value.strip()
        for value in values
        if value.strip() and (include_missing or value != MISSING_VALUE)
    }
    return sorted(result)


def _risk_level(values: set[str]) -> str:
    return max(values or {"unknown"}, key=lambda value: RISK_PRIORITY.get(value, 0))


def _percentage(count: int, denominator: int) -> float:
    return round(count / denominator * 100, 1) if denominator else 0.0


def _pattern_id(
    run_id: uuid.UUID,
    signal_type: str,
    object_name: str,
    issue: str,
) -> str:
    content = "\x1f".join((str(run_id), signal_type, object_name, issue))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _dimension(
    values_by_voice: dict[uuid.UUID, set[str]],
    denominator: int,
) -> list[DimensionValue]:
    counts: dict[str, int] = defaultdict(int)
    for values in values_by_voice.values():
        for value in values or {MISSING_VALUE}:
            counts[value] += 1
    return [
        DimensionValue(
            value=value,
            count=count,
            percentage=_percentage(count, denominator),
            denominator=denominator,
        )
        for value, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _coverage(voices: list[VoiceRecord], total_signals: int) -> InsightCoverage:
    dates = [voice.occurred_at.date() for voice in voices if voice.occurred_at]
    period_start = min(dates) if dates else None
    period_end = max(dates) if dates else None
    days = (
        (period_end - period_start).days + 1
        if period_start is not None and period_end is not None
        else 0
    )
    trend_allowed = days >= 28
    limitations = [
        "当前百分比分母仅为最新分析运行覆盖的去重原声，不代表全部客户或市场。",
        "同一条原声可包含多个生命周期或风险信号，因此这些维度的占比允许重叠，不应相加为百分之百。",
        "未接入销量、订单、退货、维修和成本分母，不能计算发生率、损失金额或 ROI。",
    ]
    if not trend_allowed:
        limitations.append("时间覆盖不足 28 天，仅支持截面描述，不支持趋势、同比或环比结论。")
    return InsightCoverage(
        total_voices=len(voices),
        total_signals=total_signals,
        period_start=period_start,
        period_end=period_end,
        days=days,
        trend_allowed=trend_allowed,
        channels=_unique([_clean(voice.channel) for voice in voices]),
        denominator_notice=(
            f"本页数字以最新分析运行中 {len(voices)} 条去重原声为分母；"
            "缺少企业经营分母。"
        ),
        limitations=limitations,
    )


def _conflict_notice(risks: set[str], directions: list[str]) -> str | None:
    notices: list[str] = []
    if len(risks) > 1:
        notices.append("同一问题存在多个风险标签，当前按最高风险排序，必须人工复核。")
    if len(_unique(directions)) > 1:
        notices.append("存在多个未验证的候选改进方向，必须由产品、研发和质量负责人取舍。")
    return "".join(notices) or None


def _forbidden_claims(coverage: InsightCoverage) -> list[str]:
    claims = [
        "不得将局部原声占比外推为总体市场发生率。",
        "不得把根因假设表述为已证实因果。",
        "没有销量、订单、退货、维修和成本分母时，不得计算或宣称 ROI、损失金额或节省金额。",
        "未经人工复核，不得直接作为产品发布、召回或安全结论。",
    ]
    if not coverage.trend_allowed:
        claims.append("覆盖不足 28 天，不得宣称趋势、同比或环比变化。")
    return claims


def _card(pattern: InsightPattern, coverage: InsightCoverage) -> DecisionCard:
    safety = pattern.risk_level in {"critical", "high"}
    if safety:
        why_now = (
            f"该问题被标记为 {pattern.risk_level} 风险，当前数据内有 "
            f"{pattern.voice_count} 条去重原声支持；风险标签尚未校准，应先人工复核。"
        )
        owner = "质量/安全负责人（联合研发与产品）"
    else:
        why_now = (
            f"最新分析运行中有 {pattern.voice_count} 条去重原声指向该问题，"
            f"占当前局部样本 {pattern.share}%；该占比不能外推。"
        )
        owner = "产品负责人（联合研发、质量或用户研究）"

    if pattern.improvement_directions:
        candidates = "；".join(pattern.improvement_directions[:3])
        direction = f"候选方向（未经验证）：{candidates}"
    elif safety:
        direction = "暂不给出直接修改结论；先由质量/安全负责人完成复现、失效模式排查和风险分级。"
    else:
        direction = (
            f"围绕“{pattern.object_name}”的“{pattern.issue}”完成问题定义，"
            "再进行候选方案评审；当前不宜直接确定产品改动。"
        )

    if pattern.validation_suggestions:
        validation = "；".join(pattern.validation_suggestions[:3])
    elif safety:
        validation = "先复现并记录触发条件，完成安全/失效评审，经主管批准后才进行隔离的小范围验证。"
    else:
        validation = "先补齐缺失信息，再用可控原型或小范围用户测试比较改动前后，并在验证前定义指标和通过标准。"

    priority = (
        f"安全边界优先：{pattern.risk_level} 风险必须先于普通体验优化；"
        if safety
        else "在同等安全等级内，按去重原声支持数排序；"
    )
    priority += (
        f"当前有 {pattern.voice_count} 条局部证据，覆盖 "
        f"{len(pattern.channels)} 个渠道、{len(pattern.skus)} 个 SKU、"
        f"{len(pattern.batches)} 个批次、{len(pattern.versions)} 个版本；"
        "排序不使用虚构加权分。成本与 ROI 因缺经营分母为 TBD。"
    )
    return DecisionCard(
        card_id=f"card-{pattern.pattern_id}",
        problem=f"{pattern.object_name}：{pattern.issue}",
        why_now=why_now,
        evidence_level="directional",
        risk_level=pattern.risk_level,
        voice_count=pattern.voice_count,
        share=pattern.share,
        recommended_direction=direction,
        validation_plan=validation,
        human_owner=owner,
        forbidden_claims=_forbidden_claims(coverage),
        priority_explanation=priority,
        supporting_evidence_ids=pattern.supporting_evidence_ids,
    )


async def _latest_run_id(session: AsyncSession, product: str) -> uuid.UUID:
    run_id = await session.scalar(
        select(AnalysisRun.id)
        .join(Signal, Signal.analysis_run_id == AnalysisRun.id)
        .join(VoiceRecord, VoiceRecord.id == Signal.voice_record_id)
        .where(VoiceRecord.product == product)
        .group_by(AnalysisRun.id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(1)
    )
    if run_id is None:
        raise LookupError(f"产品线没有可用洞察数据：{product}")
    return run_id


async def get_decision_insights(
    session: AsyncSession,
    *,
    product: str,
) -> DecisionInsightResponse:
    """Build a bounded decision view from the latest run; no causal/ROI inference."""
    run_id = await _latest_run_id(session, product)
    rows = (
        await session.execute(
            select(Signal, VoiceRecord)
            .join(VoiceRecord, VoiceRecord.id == Signal.voice_record_id)
            .where(
                Signal.analysis_run_id == run_id,
                VoiceRecord.product == product,
            )
            .order_by(Signal.id)
        )
    ).all()
    voices_by_id = {voice.id: voice for _, voice in rows}
    voices = list(voices_by_id.values())
    coverage = _coverage(voices, len(rows))

    dimension_values: dict[str, dict[uuid.UUID, set[str]]] = {
        name: defaultdict(set)
        for name in (
            "channel",
            "sku",
            "batch",
            "version",
            "lifecycle_stage",
            "risk_level",
        )
    }
    for voice in voices:
        attributes = voice.attributes if isinstance(voice.attributes, dict) else {}
        dimension_values["channel"][voice.id].add(_clean(voice.channel))
        dimension_values["sku"][voice.id].add(_clean(voice.sku))
        dimension_values["batch"][voice.id].add(_clean(attributes.get("batch")))
        dimension_values["version"][voice.id].add(_clean(attributes.get("version")))
    for signal, voice in rows:
        dimension_values["lifecycle_stage"][voice.id].add(
            _clean(signal.lifecycle_stage, fallback="unknown")
        )
        dimension_values["risk_level"][voice.id].add(
            _clean(signal.risk_level, fallback="unknown")
        )

    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for signal, voice in rows:
        signal_type = _clean(signal.signal_type, fallback="unknown")
        object_name = _clean(signal.object_name, fallback="未标注对象")
        issue = _clean(signal.issue, fallback=object_name)
        key = (signal_type, object_name, issue)
        group = grouped.setdefault(
            key,
            {
                "voice_ids": set(),
                "risks": set(),
                "channels": [],
                "skus": [],
                "batches": [],
                "versions": [],
                "lifecycle_stages": [],
                "scenarios": [],
                "latent_needs": [],
                "root_cause_hypotheses": [],
                "improvement_directions": [],
                "validation_suggestions": [],
                "missing_information": [],
                "evidence_ids": [],
            },
        )
        attributes = voice.attributes if isinstance(voice.attributes, dict) else {}
        group["voice_ids"].add(voice.id)  # type: ignore[union-attr]
        group["risks"].add(_clean(signal.risk_level, fallback="unknown"))  # type: ignore[union-attr]
        group["channels"].append(_clean(voice.channel))  # type: ignore[union-attr]
        group["skus"].append(_clean(voice.sku))  # type: ignore[union-attr]
        group["batches"].append(_clean(attributes.get("batch")))  # type: ignore[union-attr]
        group["versions"].append(_clean(attributes.get("version")))  # type: ignore[union-attr]
        group["lifecycle_stages"].append(  # type: ignore[union-attr]
            _clean(signal.lifecycle_stage, fallback="unknown")
        )
        group["scenarios"].append(_clean(signal.scenario, fallback=""))  # type: ignore[union-attr]
        group["latent_needs"].append(_clean(signal.latent_need, fallback=""))  # type: ignore[union-attr]
        group["root_cause_hypotheses"].extend(  # type: ignore[union-attr]
            _string_list(signal.root_cause_hypotheses)
        )
        group["improvement_directions"].extend(  # type: ignore[union-attr]
            _string_list(signal.improvement_directions)
        )
        group["validation_suggestions"].extend(  # type: ignore[union-attr]
            _string_list(signal.validation_suggestions)
        )
        group["missing_information"].extend(  # type: ignore[union-attr]
            _string_list(signal.missing_information)
        )
        group["evidence_ids"].append(signal.id)  # type: ignore[union-attr]

    patterns: list[InsightPattern] = []
    denominator = len(voices)
    for (signal_type, object_name, issue), group in grouped.items():
        voice_count = len(group["voice_ids"])  # type: ignore[arg-type]
        risks = group["risks"]  # type: ignore[assignment]
        directions = _unique(group["improvement_directions"])  # type: ignore[arg-type]
        patterns.append(
            InsightPattern(
                pattern_id=_pattern_id(run_id, signal_type, object_name, issue),
                signal_type=signal_type,
                object_name=object_name,
                issue=issue,
                risk_level=_risk_level(risks),
                voice_count=voice_count,
                share=_percentage(voice_count, denominator),
                denominator=denominator,
                channels=_unique(group["channels"]),  # type: ignore[arg-type]
                skus=_unique(group["skus"]),  # type: ignore[arg-type]
                batches=_unique(group["batches"]),  # type: ignore[arg-type]
                versions=_unique(group["versions"]),  # type: ignore[arg-type]
                lifecycle_stages=_unique(group["lifecycle_stages"]),  # type: ignore[arg-type]
                scenarios=_unique(group["scenarios"]),  # type: ignore[arg-type]
                latent_needs=_unique(group["latent_needs"]),  # type: ignore[arg-type]
                root_cause_hypotheses=_unique(  # type: ignore[arg-type]
                    group["root_cause_hypotheses"]
                ),
                improvement_directions=directions,
                validation_suggestions=_unique(  # type: ignore[arg-type]
                    group["validation_suggestions"]
                ),
                missing_information=_unique(  # type: ignore[arg-type]
                    group["missing_information"]
                ),
                supporting_evidence_ids=sorted(  # type: ignore[arg-type]
                    group["evidence_ids"], key=str
                ),
                conflict_notice=_conflict_notice(risks, directions),
            )
        )
    patterns.sort(
        key=lambda item: (
            -RISK_PRIORITY.get(item.risk_level, 0),
            -item.voice_count,
            -(
                len(item.channels)
                + len(item.skus)
                + len(item.batches)
                + len(item.versions)
            ),
            item.signal_type,
            item.object_name,
            item.issue,
        )
    )

    dimensions = {
        name: _dimension(values, denominator)
        for name, values in dimension_values.items()
    }
    return DecisionInsightResponse(
        product=product,
        analysis_run_id=run_id,
        coverage=coverage,
        dimensions=dimensions,
        patterns=patterns,
        decision_cards=[
            _card(pattern, coverage) for pattern in patterns[:MAX_DECISION_CARDS]
        ],
        governance=InsightGovernance(
            scope_notice="仅描述最新分析运行覆盖的当前产品线数据。",
            causality_notice="根因和改进方向均为待验证假设，不得表述为已证实因果。",
            financial_notice="未接入经营分母，不计算 ROI、损失金额或节省金额。",
            human_review_notice="决策卡只是候选输入，所有产品改动与安全结论均需有权限的人员审核。",
        ),
    )
