import hashlib
import importlib.util
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.enums import OpportunityStatus
from bearvoice.domain.models import (
    AnalysisRun,
    Cluster,
    ClusterMembership,
    IngestionBatch,
    Opportunity,
    OpportunityEvidence,
    PrivacyFinding,
    Signal,
    Source,
    TaxonomyVersion,
    VoiceRecord,
)
from bearvoice.modules.analysis.cache import load_cached_json
from bearvoice.modules.ingest.privacy import sanitize_voice_text


class LegacyBaselineMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class LegacyRecord:
    external_id: str
    text: str
    sentiment: str
    occurred_at: str
    signal: str
    stage: str
    object_name: str
    issue: str


@dataclass(frozen=True)
class LegacySnapshot:
    dataset_hash: str
    records: tuple[LegacyRecord, ...]
    clusters: tuple[dict[str, Any], ...]
    recommendations: tuple[dict[str, Any], ...]
    extract_cache_count: int
    actionable_signal_count: int


def _load_legacy_module(repo_root: Path):
    script_path = repo_root / "scripts/analyze.py"
    spec = importlib.util.spec_from_file_location(
        "bearvoice_legacy_analyze",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise LegacyBaselineMismatch(f"无法加载历史管线：{script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_legacy_snapshot(repo_root: Path) -> LegacySnapshot:
    analyze = _load_legacy_module(repo_root)
    rows = analyze.load_rows(verbose=False)
    kettle_rows = [
        row
        for row in rows
        if analyze.product_key(row.get("商品标题", "")) == "养生壶"
    ]
    batches = [
        kettle_rows[index : index + analyze.BATCH]
        for index in range(0, len(kettle_rows), analyze.BATCH)
    ]
    build_dir = repo_root / "_build/analyze"
    extracted: list[LegacyRecord] = []
    cache_names: list[str] = []

    for batch in batches:
        lines = [
            f"{index}. {row['_文本'][:300]}"
            for index, row in enumerate(batch)
        ]
        prompt = "%s\n\n品类：%s\n\n--- %d 条原声 ---\n%s" % (
            analyze.EXTRACT_RULES,
            "养生壶",
            len(batch),
            "\n".join(lines),
        )
        cached = load_cached_json(prompt, "extract", build_dir)
        if not isinstance(cached, list):
            raise LegacyBaselineMismatch("抽取缓存不是 JSON 数组")
        cache_names.append(
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        )
        for item in cached:
            index = item.get("i")
            if not isinstance(index, int) or not 0 <= index < len(batch):
                raise LegacyBaselineMismatch("抽取缓存包含越界原声索引")
            source = batch[index]
            extracted.append(
                LegacyRecord(
                    external_id=source.get("原声id", ""),
                    text=source["_文本"],
                    sentiment=source.get("原声情感", ""),
                    occurred_at=source.get("原声日期", ""),
                    signal=item.get("signal", "咨询"),
                    stage=item.get("stage", ""),
                    object_name=item.get("object", ""),
                    issue=item.get("issue", ""),
                )
            )

    detail_path = repo_root / "reports/improve-养生壶/聚类明细.json"
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    clusters = tuple(detail.get("clusters", []))
    recommendations = tuple(detail.get("recommendations", []))
    actionable = sum(
        int(cluster.get("count", 0))
        for cluster in clusters
        if cluster.get("signal") != "咨询"
    )

    if len(extracted) != 370:
        raise LegacyBaselineMismatch("抽取缓存没有完整覆盖 370 条养生壶原声")
    if len(batches) != 10 or len(set(cache_names)) != 10:
        raise LegacyBaselineMismatch("预期 10 个独立抽取缓存")
    if len(clusters) != 10 or sum(c.get("count", 0) for c in clusters) != 370:
        raise LegacyBaselineMismatch("聚类明细未完整覆盖 370 条原声")
    if len(recommendations) != 9 or actionable != 254:
        raise LegacyBaselineMismatch("建议或可行动信号与已验证基线不一致")

    dataset_hash = hashlib.sha256(
        json.dumps(
            {
                "record_ids": [record.external_id for record in extracted],
                "extract_caches": cache_names,
                "cluster_detail": hashlib.sha256(
                    detail_path.read_bytes()
                ).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return LegacySnapshot(
        dataset_hash=dataset_hash,
        records=tuple(extracted),
        clusters=clusters,
        recommendations=recommendations,
        extract_cache_count=len(batches),
        actionable_signal_count=actionable,
    )


async def import_legacy_snapshot(
    session: AsyncSession,
    snapshot: LegacySnapshot,
) -> uuid.UUID:
    existing = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.dataset_hash == snapshot.dataset_hash,
            AnalysisRun.model_version == "legacy-claude-cache",
        )
    )
    if existing is not None:
        return existing.id

    source = Source(
        id=uuid.uuid4(),
        source_type="legacy_snapshot",
        name=f"养生壶历史基线-{snapshot.dataset_hash[:12]}",
        channel="天猫咨询",
        connection_status="verified",
        authorization_scope={"mode": "cache_only", "model_fallback": False},
    )
    batch = IngestionBatch(
        id=uuid.uuid4(),
        source_id=source.id,
        file_hash=snapshot.dataset_hash,
        raw_count=370,
        deduplicated_count=370,
        quarantined_count=0,
        status="verified_legacy_import",
    )
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash=snapshot.dataset_hash,
        code_version="legacy-analyze.py",
        model_version="legacy-claude-cache",
        prompt_version="extract-rules-2026-08-15",
        parameters={
            "provider": "legacy-claude-cache",
            "cache_only": True,
            "extract_cache_count": snapshot.extract_cache_count,
        },
        stage_status={
            "extract": "imported",
            "cluster": "imported",
            "recommend": "imported",
        },
    )
    session.add(source)
    await session.flush()
    session.add_all([batch, run])
    await session.flush()

    voice_by_index: dict[int, VoiceRecord] = {}
    signal_by_index: dict[int, Signal] = {}
    privacy_rows: list[PrivacyFinding] = []
    for index, item in enumerate(snapshot.records):
        sanitized = sanitize_voice_text(item.text)
        voice = VoiceRecord(
            id=uuid.uuid4(),
            source_id=source.id,
            ingestion_batch_id=batch.id,
            external_id=item.external_id,
            product="养生壶",
            channel="天猫",
            occurred_at=_parse_legacy_datetime(item.occurred_at),
            raw_object_ref="legacy:kettle-20260815",
            normalized_text=sanitized.text,
            content_hash=hashlib.sha256(item.text.encode("utf-8")).hexdigest(),
            privacy_status="masked" if sanitized.findings else "clean",
            attributes={"sentiment": item.sentiment},
        )
        signal = Signal(
            id=uuid.uuid4(),
            analysis_run_id=run.id,
            voice_record_id=voice.id,
            signal_index=0,
            signal_type=item.signal,
            object_name=item.object_name or None,
            evidence_text=item.issue or sanitized.text,
            confidence=None,
            calibration_status="uncalibrated",
            is_outlier=False,
        )
        voice_by_index[index] = voice
        signal_by_index[index] = signal
        privacy_rows.extend(
            PrivacyFinding(
                id=uuid.uuid4(),
                voice_record_id=voice.id,
                entity_type=finding.entity_type,
                start_offset=finding.start_offset,
                end_offset=finding.end_offset,
                recognizer=finding.recognizer,
                confidence=finding.confidence,
                action=finding.action,
                review_status="automatic",
            )
            for finding in sanitized.findings
        )
    session.add_all(voice_by_index.values())
    await session.flush()
    session.add_all(signal_by_index.values())
    session.add_all(privacy_rows)
    await session.flush()

    taxonomy = TaxonomyVersion(
        id=uuid.uuid4(),
        product_scope="养生壶",
        origin="legacy_verified_import",
        status="draft",
    )
    session.add(taxonomy)
    await session.flush()
    memberships: list[ClusterMembership] = []
    for cluster_data in snapshot.clusters:
        cluster = Cluster(
            id=uuid.uuid4(),
            taxonomy_version_id=taxonomy.id,
            original_name=cluster_data["name"],
            current_name=cluster_data["name"],
            primary_signal_type=cluster_data.get("signal"),
            keywords=[],
            representative_record_ids=[
                snapshot.records[index].external_id
                for index in cluster_data.get("members", [])[:3]
            ],
            is_outlier=False,
            status="imported_unreviewed",
        )
        session.add(cluster)
        for member_index in cluster_data.get("members", []):
            memberships.append(
                ClusterMembership(
                    id=uuid.uuid4(),
                    taxonomy_version_id=taxonomy.id,
                    cluster_id=cluster.id,
                    signal_id=signal_by_index[member_index].id,
                    assignment_status="legacy_uncalibrated",
                )
            )
    await session.flush()
    session.add_all(memberships)
    await session.flush()

    cluster_data_by_name = {
        item["name"]: item for item in snapshot.clusters
    }
    opportunity_evidence: list[OpportunityEvidence] = []
    for recommendation in snapshot.recommendations:
        cluster_name = recommendation.get("cluster", "")
        opportunity = Opportunity(
            id=uuid.uuid4(),
            opportunity_type="improvement",
            title=recommendation.get("action") or cluster_name,
            problem=cluster_name,
            product="养生壶",
            impact_scope=str(recommendation.get("impact", "")),
            severity=recommendation.get("priority"),
            differentiation=None,
            recommended_action=recommendation.get("action"),
            status=OpportunityStatus.DRAFT.value,
        )
        session.add(opportunity)
        cluster_data = cluster_data_by_name.get(cluster_name, {})
        for member_index in cluster_data.get("members", []):
            opportunity_evidence.append(
                OpportunityEvidence(
                    id=uuid.uuid4(),
                    opportunity_id=opportunity.id,
                    voice_record_id=voice_by_index[member_index].id,
                    signal_id=signal_by_index[member_index].id,
                    evidence_direction="support",
                    reviewed=False,
                )
            )

    await session.flush()
    session.add_all(opportunity_evidence)
    await session.flush()
    return run.id


def _parse_legacy_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return parsed
