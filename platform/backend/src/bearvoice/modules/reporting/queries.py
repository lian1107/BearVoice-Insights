import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.models import (
    AnalysisRun,
    Cluster,
    ClusterMembership,
    Opportunity,
    OpportunityEvidence,
    Signal,
    Source,
    TaxonomyVersion,
    VoiceRecord,
)
from bearvoice.modules.ingest.privacy import sanitize_voice_text


class SignalMetric(BaseModel):
    signal_type: str
    count: int
    percentage: float
    denominator: int


class ClusterMetric(BaseModel):
    id: uuid.UUID
    name: str
    signal_type: str | None
    count: int
    percentage: float
    denominator: int


class OpportunitySummary(BaseModel):
    id: uuid.UUID
    title: str
    opportunity_type: str
    status: str
    safety_level: str | None
    priority_override: str | None
    severity: str | None
    impact_scope: str | None
    evidence_count: int


class CoverageBoundary(BaseModel):
    channel: str
    period_start: date | None
    period_end: date | None
    days: int
    trend_allowed: bool
    limitation: str


class DashboardSnapshot(BaseModel):
    product: str
    view: Literal["competition", "enterprise"]
    analysis_run_id: uuid.UUID
    total_voices: int
    actionable_voices: int
    denominator: int
    signals: list[SignalMetric]
    top_clusters: list[ClusterMetric]
    opportunities: list[OpportunitySummary]
    coverage: CoverageBoundary


class EvidenceProjection(BaseModel):
    id: uuid.UUID
    quote: str
    voice_record_id: uuid.UUID
    source: str
    product: str
    channel: str
    analysis_run_id: uuid.UUID
    signal_type: str
    object_name: str | None
    privacy_status: str


class ReconciliationError(AssertionError):
    def __init__(self, expected: dict[str, int], actual: dict[str, int]):
        super().__init__(f"历史基线对账失败：expected={expected}, actual={actual}")
        self.expected = expected
        self.actual = actual


async def _latest_analysis_run_id(
    session: AsyncSession,
    product: str,
) -> uuid.UUID:
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
        raise LookupError(f"产品线没有可用分析运行：{product}")
    return run_id


async def get_dashboard_snapshot(
    session: AsyncSession,
    *,
    product: str,
    view: Literal["competition", "enterprise"],
) -> DashboardSnapshot:
    run_id = await _latest_analysis_run_id(session, product)
    total_voices = int(
        await session.scalar(
            select(func.count(distinct(VoiceRecord.id))).where(
                VoiceRecord.product == product
            )
        )
        or 0
    )
    signal_rows = (
        await session.execute(
            select(
                Signal.signal_type,
                func.count(distinct(Signal.voice_record_id)),
            )
            .join(VoiceRecord, VoiceRecord.id == Signal.voice_record_id)
            .where(
                Signal.analysis_run_id == run_id,
                VoiceRecord.product == product,
            )
            .group_by(Signal.signal_type)
            .order_by(func.count(distinct(Signal.voice_record_id)).desc())
        )
    ).all()
    signals = [
        SignalMetric(
            signal_type=signal_type,
            count=int(count),
            percentage=round(int(count) / total_voices * 100, 1),
            denominator=total_voices,
        )
        for signal_type, count in signal_rows
    ]
    actionable_voices = sum(
        metric.count for metric in signals if metric.signal_type != "咨询"
    )

    taxonomy_id = await session.scalar(
        select(TaxonomyVersion.id)
        .where(TaxonomyVersion.product_scope == product)
        .order_by(TaxonomyVersion.created_at.desc(), TaxonomyVersion.id.desc())
        .limit(1)
    )
    cluster_rows = []
    if taxonomy_id is not None:
        cluster_rows = (
            await session.execute(
                select(
                    Cluster.id,
                    Cluster.current_name,
                    Cluster.primary_signal_type,
                    func.count(distinct(Signal.voice_record_id)).label("voice_count"),
                )
                .join(
                    ClusterMembership,
                    ClusterMembership.cluster_id == Cluster.id,
                )
                .join(Signal, Signal.id == ClusterMembership.signal_id)
                .where(
                    Cluster.taxonomy_version_id == taxonomy_id,
                    Signal.analysis_run_id == run_id,
                )
                .group_by(
                    Cluster.id,
                    Cluster.current_name,
                    Cluster.primary_signal_type,
                )
                .order_by(
                    func.count(distinct(Signal.voice_record_id)).desc(),
                    Cluster.current_name,
                )
            )
        ).all()
    clusters = [
        ClusterMetric(
            id=cluster_id,
            name=name,
            signal_type=signal_type,
            count=int(count),
            percentage=round(int(count) / total_voices * 100, 1),
            denominator=total_voices,
        )
        for cluster_id, name, signal_type, count in cluster_rows
    ]

    opportunity_rows = (
        await session.execute(
            select(
                Opportunity,
                func.count(distinct(OpportunityEvidence.voice_record_id)).label(
                    "evidence_count"
                ),
            )
            .outerjoin(
                OpportunityEvidence,
                OpportunityEvidence.opportunity_id == Opportunity.id,
            )
            .where(Opportunity.product == product)
            .group_by(Opportunity.id)
            .order_by(
                Opportunity.priority_override.desc().nullslast(),
                Opportunity.created_at,
            )
        )
    ).all()
    opportunities = [
        OpportunitySummary(
            id=opportunity.id,
            title=opportunity.title,
            opportunity_type=opportunity.opportunity_type,
            status=opportunity.status,
            safety_level=opportunity.safety_level,
            priority_override=opportunity.priority_override,
            severity=opportunity.severity,
            impact_scope=opportunity.impact_scope,
            evidence_count=int(evidence_count),
        )
        for opportunity, evidence_count in opportunity_rows
    ]

    coverage_row = (
        await session.execute(
            select(
                func.min(
                    func.date(
                        func.timezone("Asia/Shanghai", VoiceRecord.occurred_at)
                    )
                ),
                func.max(
                    func.date(
                        func.timezone("Asia/Shanghai", VoiceRecord.occurred_at)
                    )
                ),
                func.string_agg(distinct(VoiceRecord.channel), ","),
            ).where(VoiceRecord.product == product)
        )
    ).one()
    period_start, period_end, channels = coverage_row
    days = (
        (period_end - period_start).days + 1
        if period_start is not None and period_end is not None
        else 0
    )
    trend_allowed = days >= 28
    coverage = CoverageBoundary(
        channel=channels or "未知",
        period_start=period_start,
        period_end=period_end,
        days=days,
        trend_allowed=trend_allowed,
        limitation=(
            "可支持趋势分析"
            if trend_allowed
            else "仅支持截面分析，不支持趋势、同比或环比判断"
        ),
    )
    return DashboardSnapshot(
        product=product,
        view=view,
        analysis_run_id=run_id,
        total_voices=total_voices,
        actionable_voices=actionable_voices,
        denominator=total_voices,
        signals=signals,
        top_clusters=clusters,
        opportunities=opportunities,
        coverage=coverage,
    )


def reconcile_legacy_baseline(snapshot: DashboardSnapshot) -> None:
    expected = {
        "total_voices": 370,
        "actionable_voices": 254,
        "clusters": 10,
        "opportunities": 9,
    }
    actual = {
        "total_voices": snapshot.total_voices,
        "actionable_voices": snapshot.actionable_voices,
        "clusters": len(snapshot.top_clusters),
        "opportunities": len(snapshot.opportunities),
    }
    if actual != expected:
        raise ReconciliationError(expected, actual)


async def get_evidence_projection(
    session: AsyncSession,
    *,
    evidence_id: uuid.UUID,
    allowed_products: frozenset[str] | None,
) -> EvidenceProjection | None:
    statement = (
        select(Signal, VoiceRecord, Source)
        .join(VoiceRecord, VoiceRecord.id == Signal.voice_record_id)
        .join(Source, Source.id == VoiceRecord.source_id)
        .where(Signal.id == evidence_id)
    )
    if allowed_products is not None:
        statement = statement.where(VoiceRecord.product.in_(allowed_products))
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    signal, voice, source = row
    return EvidenceProjection(
        id=signal.id,
        quote=sanitize_voice_text(voice.normalized_text).text,
        voice_record_id=voice.id,
        source=source.channel,
        product=voice.product,
        channel=voice.channel,
        analysis_run_id=signal.analysis_run_id,
        signal_type=signal.signal_type,
        object_name=signal.object_name,
        privacy_status=voice.privacy_status,
    )
