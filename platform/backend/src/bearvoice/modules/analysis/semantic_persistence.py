import asyncio
import hashlib
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.config import Settings
from bearvoice.domain.models import (
    AnalysisRun,
    AuditEvent,
    Cluster,
    ClusterMembership,
    IngestionBatch,
    Opportunity,
    OpportunityEvidence,
    Signal,
    SemanticVoiceCache,
    TaxonomyVersion,
    VoiceRecord,
)
from bearvoice.modules.analysis.china_model_adapter import (
    ChinaModelProvider,
    ModelTransportError,
    provider_config_from_settings,
)
from bearvoice.modules.analysis.china_models import build_semantic_engine
from bearvoice.modules.analysis.semantic_engine import (
    SemanticAnalysisEngine,
    SemanticOutputError,
)
from bearvoice.modules.analysis.semantic_models import (
    SemanticSignal,
    VoiceSemanticInput,
    VoiceSemanticResult,
)
from bearvoice.observability import redact_sensitive


@dataclass(frozen=True)
class SemanticBatchResult:
    analysis_run_id: uuid.UUID
    status: str
    voice_count: int
    signal_count: int
    cluster_count: int
    opportunity_count: int
    error_code: str | None = None
    reused: bool = False


class SemanticCallBudgetExceeded(RuntimeError):
    pass


SEMANTIC_PROMPT_VERSION = "voice-semantic-json-v2"


def _cache_key(
    record: VoiceRecord,
    *,
    provider: str,
    model_version: str,
    product: str,
) -> str:
    material = ":".join(
        (
            str(record.id),
            record.content_hash,
            product,
            provider,
            model_version,
            SEMANTIC_PROMPT_VERSION,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _top_nonempty(values: list[str | None]) -> str | None:
    normalized = [value.strip() for value in values if value and value.strip()]
    return Counter(normalized).most_common(1)[0][0] if normalized else None


async def _existing_result(
    session: AsyncSession,
    run: AnalysisRun,
) -> SemanticBatchResult:
    signal_ids = select(Signal.id).where(Signal.analysis_run_id == run.id)
    voice_count = int(
        await session.scalar(
            select(func.count(distinct(Signal.voice_record_id))).where(
                Signal.analysis_run_id == run.id
            )
        )
        or 0
    )
    signal_count = int(
        await session.scalar(
            select(func.count()).select_from(Signal).where(
                Signal.analysis_run_id == run.id
            )
        )
        or 0
    )
    cluster_count = int(
        await session.scalar(
            select(func.count(distinct(ClusterMembership.cluster_id))).where(
                ClusterMembership.signal_id.in_(signal_ids)
            )
        )
        or 0
    )
    opportunity_count = int(
        await session.scalar(
            select(func.count(distinct(OpportunityEvidence.opportunity_id))).where(
                OpportunityEvidence.signal_id.in_(signal_ids)
            )
        )
        or 0
    )
    return SemanticBatchResult(
        analysis_run_id=run.id,
        status=str((run.stage_status or {}).get("status", "pending_review")),
        voice_count=voice_count,
        signal_count=signal_count,
        cluster_count=cluster_count,
        opportunity_count=opportunity_count,
        reused=True,
    )


async def _mark_failed(
    session: AsyncSession,
    run: AnalysisRun,
    *,
    actor_id: str,
    batch_id: uuid.UUID,
    product: str,
    provider: ChinaModelProvider,
    error: Exception,
    started: float,
) -> SemanticBatchResult:
    error_code = type(error).__name__[:100]
    run.duration_ms = int((time.monotonic() - started) * 1000)
    run.error_code = error_code
    run.error_message = redact_sensitive(str(error))[:4_000]
    previous_status = dict(run.stage_status or {})
    run.stage_status = {
        **previous_status,
        "status": "failed",
        "current_phase": "semantic_extract",
        "provider": provider,
        "model": run.model_version,
        "notice": "整批语义结果已拒绝，未写入任何 Signal",
    }
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action="analysis.semantic_failed",
            subject_type="analysis_run",
            subject_id=run.id,
            after_state={
                "batch_id": str(batch_id),
                "product": product,
                "provider": provider,
                "error_code": error_code,
                "partial_signals_persisted": 0,
            },
            reason="模型调用或严格输出校验失败，整批拒绝",
        )
    )
    await session.flush()
    return SemanticBatchResult(
        analysis_run_id=run.id,
        status="failed",
        voice_count=0,
        signal_count=0,
        cluster_count=0,
        opportunity_count=0,
        error_code=error_code,
    )


async def run_semantic_analysis(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    product: str,
    provider: ChinaModelProvider,
    actor_id: str,
    settings: Settings | None = None,
    engine: SemanticAnalysisEngine | None = None,
    progress_callback: Callable[
        [uuid.UUID, int, int, int, int], Awaitable[None]
    ]
    | None = None,
    model_call_limit: int | None = None,
) -> SemanticBatchResult:
    """Analyze an ingestion batch atomically into a distinct governed AI run.

    Model outputs are collected and validated before any Signal is inserted. A
    model or contract failure therefore records a failed run with zero partial
    signals instead of contaminating the offline keyword baseline.
    """

    resolved_settings = settings or Settings()
    provider_config = provider_config_from_settings(resolved_settings, provider)
    resolved_engine = engine or build_semantic_engine(provider, resolved_settings)
    batch = await session.get(IngestionBatch, batch_id)
    if batch is None:
        raise LookupError("导入批次不存在")
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
        raise ValueError("该批次没有可分析的产品原声")
    if any(record.privacy_status not in {"clean", "masked"} for record in records):
        raise ValueError("批次中存在未通过隐私门禁的原声")

    model_version = f"{provider}:{provider_config.model}"
    previous_runs = list(
        await session.scalars(
            select(AnalysisRun)
            .where(
                AnalysisRun.dataset_hash == batch.file_hash,
                AnalysisRun.model_version == model_version,
            )
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        )
    )
    for previous in previous_runs:
        parameters = previous.parameters or {}
        if (
            parameters.get("ingestion_batch_id") == str(batch.id)
            and parameters.get("product") == product
            and (previous.stage_status or {}).get("status")
            in {"pending_review", "succeeded"}
        ):
            return await _existing_result(session, previous)

    started = time.monotonic()
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash=batch.file_hash,
        code_version="governed-semantic-v1",
        model_version=model_version,
        prompt_version=SEMANTIC_PROMPT_VERSION,
        parameters={
            "ingestion_batch_id": str(batch.id),
            "product": product,
            "analysis_mode": "governed_ai_semantic",
            "provider": provider,
            "uncalibrated": True,
        },
        stage_status={
            "status": "running",
            "current_phase": "semantic_extract",
            "provider": provider,
            "model": provider_config.model,
            "processed_items": 0,
            "total_items": len(records),
            "model_calls": 0,
        },
    )
    session.add(run)
    await session.flush()

    extracted: list[tuple[VoiceRecord, list[SemanticSignal]]] = []
    model_calls = 0
    input_tokens = 0
    output_tokens = 0
    cache_hits = 0
    unresolved_voice_ids: list[str] = []
    reserved_model_calls = 0
    model_call_lock = asyncio.Lock()
    cache_keys = {
        record.id: _cache_key(
            record,
            provider=provider,
            model_version=model_version,
            product=product,
        )
        for record in records
    }
    cached_results: dict[str, VoiceSemanticResult] = {}
    cached_rows = list(
        await session.scalars(
            select(SemanticVoiceCache).where(
                SemanticVoiceCache.cache_key.in_(cache_keys.values())
            )
        )
    )
    for cached in cached_rows:
        try:
            parsed = VoiceSemanticResult.model_validate(cached.result_payload)
        except Exception:
            continue
        if parsed.voice_id == str(cached.voice_record_id):
            cached_results[cached.cache_key] = parsed

    async def analyze_record(
        record: VoiceRecord,
    ) -> tuple[VoiceRecord, VoiceSemanticResult, int, int, int, bool, bool]:
        nonlocal reserved_model_calls
        record_cache_key = cache_keys[record.id]
        cached = cached_results.get(record_cache_key)
        if cached is not None:
            return record, cached, 0, 0, 0, True, False
        attempts = 0
        while True:
            async with model_call_lock:
                if (
                    model_call_limit is not None
                    and reserved_model_calls >= model_call_limit
                ):
                    raise SemanticCallBudgetExceeded(
                        f"模型调用已达到本任务硬上限 {model_call_limit} 次"
                    )
                reserved_model_calls += 1
                attempts += 1
            try:
                voice_input = VoiceSemanticInput(
                    voice_id=str(record.id),
                    text=record.normalized_text,
                    product_name=record.product,
                )
                if hasattr(resolved_engine, "analyze_with_usage"):
                    outcome = await resolved_engine.analyze_with_usage(
                        voice_input,
                        run_id=str(run.id),
                    )
                    return (
                        record,
                        outcome.result,
                        attempts,
                        outcome.input_tokens,
                        outcome.output_tokens,
                        False,
                        False,
                    )
                result = await resolved_engine.analyze(voice_input, run_id=str(run.id))
                return record, result, attempts, 0, 0, False, False
            except ModelTransportError as error:
                if not error.retryable:
                    raise
                if attempts >= resolved_settings.semantic_retry_max_attempts:
                    raise
                await asyncio.sleep(
                    resolved_settings.semantic_retry_initial_seconds
                    * (2 ** (attempts - 1))
                )
            except SemanticOutputError:
                if attempts >= resolved_settings.semantic_retry_max_attempts:
                    return (
                        record,
                        VoiceSemanticResult(
                            schema_version="1.0",
                            voice_id=str(record.id),
                            signals=[],
                        ),
                        attempts,
                        0,
                        0,
                        False,
                        True,
                    )
                await asyncio.sleep(
                    resolved_settings.semantic_retry_initial_seconds
                    * (2 ** (attempts - 1))
                )

    try:
        semaphore = asyncio.Semaphore(resolved_settings.semantic_max_concurrency)

        async def limited(record: VoiceRecord):
            async with semaphore:
                return await analyze_record(record)

        for offset in range(0, len(records), resolved_settings.semantic_batch_size):
            chunk = records[offset : offset + resolved_settings.semantic_batch_size]
            chunk_results = await asyncio.gather(*(limited(record) for record in chunk))
            for (
                record,
                semantic_result,
                attempts,
                used_input,
                used_output,
                cache_hit,
                unresolved,
            ) in chunk_results:
                extracted.append((record, semantic_result.signals))
                model_calls += attempts
                input_tokens += used_input
                output_tokens += used_output
                if cache_hit:
                    cache_hits += 1
                elif unresolved:
                    unresolved_voice_ids.append(str(record.id))
                else:
                    cache_statement = insert(SemanticVoiceCache).values(
                        id=uuid.uuid4(),
                        cache_key=cache_keys[record.id],
                        voice_record_id=record.id,
                        provider=provider,
                        model_version=model_version,
                        prompt_version=SEMANTIC_PROMPT_VERSION,
                        content_hash=record.content_hash,
                        result_payload=semantic_result.model_dump(mode="json"),
                        input_tokens=used_input,
                        output_tokens=used_output,
                    )
                    await session.execute(
                        cache_statement.on_conflict_do_update(
                            index_elements=[SemanticVoiceCache.cache_key],
                            set_={
                                "result_payload": semantic_result.model_dump(
                                    mode="json"
                                ),
                                "input_tokens": used_input,
                                "output_tokens": used_output,
                            },
                        )
                    )
            run.stage_status = {
                **(run.stage_status or {}),
                "processed_items": len(extracted),
                "total_items": len(records),
                "model_calls": model_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_hits": cache_hits,
                "unresolved_voice_count": len(unresolved_voice_ids),
                "batch_size": resolved_settings.semantic_batch_size,
                "max_concurrency": resolved_settings.semantic_max_concurrency,
            }
            await session.flush()
            if progress_callback is not None:
                await progress_callback(
                    run.id,
                    len(extracted),
                    model_calls,
                    input_tokens,
                    output_tokens,
                )
    except Exception as exc:
        return await _mark_failed(
            session,
            run,
            actor_id=actor_id,
            batch_id=batch.id,
            product=product,
            provider=provider,
            error=exc,
            started=started,
        )

    taxonomy = TaxonomyVersion(
        id=uuid.uuid4(),
        product_scope=product,
        origin=f"governed_ai_{provider}",
        status="draft",
    )
    assignments: dict[
        tuple[str, str], list[tuple[VoiceRecord, Signal, SemanticSignal]]
    ] = defaultdict(list)
    opportunity_count = 0
    try:
        async with session.begin_nested():
            session.add(taxonomy)
            for record, semantic_signals in extracted:
                for index, semantic in enumerate(semantic_signals):
                    signal = Signal(
                        id=uuid.uuid4(),
                        analysis_run_id=run.id,
                        voice_record_id=record.id,
                        signal_index=index,
                        signal_type=semantic.signal_type,
                        lifecycle_stage=semantic.lifecycle_stage,
                        object_name=semantic.object_name,
                        issue=semantic.issue,
                        latent_need=semantic.latent_need,
                        scenario=semantic.scenario,
                        evidence_text=semantic.evidence_text,
                        confidence=semantic.confidence,
                        calibration_status="ai_uncalibrated_review",
                        risk_level=semantic.risk_level,
                        root_cause_hypotheses=semantic.root_cause_hypotheses,
                        missing_information=semantic.missing_information,
                        improvement_directions=semantic.improvement_directions,
                        validation_suggestions=semantic.validation_suggestions,
                        is_outlier=False,
                    )
                    session.add(signal)
                    key = (semantic.signal_type, semantic.object_name or "未指定对象")
                    assignments[key].append((record, signal, semantic))
            await session.flush()

            for (signal_type, object_name), members in sorted(
                assignments.items(), key=lambda item: -len(item[1])
            ):
                root_causes = list(
                    dict.fromkeys(
                        hypothesis
                        for _, _, semantic in members
                        for hypothesis in semantic.root_cause_hypotheses
                    )
                )[:5]
                missing = list(
                    dict.fromkeys(
                        information
                        for _, _, semantic in members
                        for information in semantic.missing_information
                    )
                )[:5]
                cluster_name = f"{signal_type} · {object_name}"[:200]
                description_parts = [
                    f"AI 语义候选主题，共 {len(members)} 条信号，发布前需人工复核。"
                ]
                if root_causes:
                    description_parts.append(
                        "待验证根因假设：" + "；".join(root_causes)
                    )
                if missing:
                    description_parts.append("仍缺信息：" + "；".join(missing))
                cluster = Cluster(
                    id=uuid.uuid4(),
                    taxonomy_version_id=taxonomy.id,
                    original_name=cluster_name,
                    current_name=cluster_name,
                    description=" ".join(description_parts),
                    primary_signal_type=signal_type,
                    keywords=[],
                    representative_record_ids=list(
                        dict.fromkeys(str(record.id) for record, _, _ in members)
                    )[:3],
                    is_outlier=False,
                    status="active",
                )
                session.add(cluster)
                session.add_all(
                    ClusterMembership(
                        id=uuid.uuid4(),
                        taxonomy_version_id=taxonomy.id,
                        cluster_id=cluster.id,
                        signal_id=signal.id,
                        assignment_status="ai_uncalibrated_review",
                    )
                    for _, signal, _ in members
                )

                semantics = [semantic for _, _, semantic in members]
                representative_issue = _top_nonempty(
                    [semantic.issue for semantic in semantics]
                ) or "待人工复核问题"
                latent_need = _top_nonempty(
                    [semantic.latent_need for semantic in semantics]
                )
                scenario = _top_nonempty([semantic.scenario for semantic in semantics])
                maximum_risk = max(
                    (semantic.risk_level for semantic in semantics),
                    key=("low", "medium", "high", "critical").index,
                )
                problem = (
                    f"{len(members)} 条未校准 AI 信号指向“{representative_issue}”。"
                )
                if root_causes:
                    problem += " 根因仅为待验证假设：" + "；".join(root_causes)
                action_parts = []
                if latent_need:
                    action_parts.append(f"需验证的潜在需求：{latent_need}")
                if missing:
                    action_parts.append("立项前补齐：" + "；".join(missing))
                action_parts.append("由产品、品质或客服负责人结合经营分母复核后决策")
                opportunity = Opportunity(
                    id=uuid.uuid4(),
                    opportunity_type=(
                        "new_product" if signal_type == "innovation" else "improvement"
                    ),
                    title=f"复核并改进{object_name}：{representative_issue}"[:200],
                    problem=problem,
                    scenario=scenario,
                    audience="产品、研发、质量与客服团队",
                    product=product,
                    component=object_name,
                    impact_scope=f"{len(members)} 条未校准 AI 信号",
                    severity={
                        "low": "P3",
                        "medium": "P2",
                        "high": "P1",
                        "critical": "P0",
                    }[maximum_risk],
                    safety_level=maximum_risk,
                    recommended_action="；".join(action_parts),
                    priority_override=(
                        "safety" if maximum_risk == "critical" else None
                    ),
                    status="pending_review",
                )
                session.add(opportunity)
                await session.flush()
                seen_records: set[uuid.UUID] = set()
                evidence_rows = []
                for record, signal, _ in members:
                    if record.id in seen_records:
                        continue
                    seen_records.add(record.id)
                    evidence_rows.append(
                        OpportunityEvidence(
                            id=uuid.uuid4(),
                            opportunity_id=opportunity.id,
                            voice_record_id=record.id,
                            signal_id=signal.id,
                            evidence_direction="support",
                            reviewed=False,
                        )
                    )
                    if len(evidence_rows) == 20:
                        break
                session.add_all(evidence_rows)
                opportunity_count += 1
            await session.flush()
    except Exception as exc:
        return await _mark_failed(
            session,
            run,
            actor_id=actor_id,
            batch_id=batch.id,
            product=product,
            provider=provider,
            error=exc,
            started=started,
        )

    signal_count = sum(len(signals) for _, signals in extracted)
    run.duration_ms = int((time.monotonic() - started) * 1000)
    run.stage_status = {
        "status": "pending_review",
        "current_phase": "human_review",
        "completed_phases": [
            "privacy_gate",
            "semantic_extract",
            "candidate_cluster",
            "draft_opportunities",
        ],
        "analysis_mode": "governed_ai_semantic",
        "provider": provider,
        "model": provider_config.model,
        "model_calls": model_calls,
        "successful_voice_calls": len(records) - len(unresolved_voice_ids),
        "attempted_voice_calls": len(records),
        "cache_hits": cache_hits,
        "unresolved_voice_count": len(unresolved_voice_ids),
        "unresolved_voice_ids": unresolved_voice_ids[:50],
        "batch_size": resolved_settings.semantic_batch_size,
        "max_concurrency": resolved_settings.semantic_max_concurrency,
        "retry_max_attempts": resolved_settings.semantic_retry_max_attempts,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "uncalibrated": True,
        "notice": "AI 语义、聚类和根因均为候选，必须人工复核",
    }
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action="analysis.semantic_candidates_created",
            subject_type="analysis_run",
            subject_id=run.id,
            after_state={
                "batch_id": str(batch.id),
                "product": product,
                "provider": provider,
                "voices": len(records),
                "signals": signal_count,
                "clusters": len(assignments),
                "opportunities": opportunity_count,
                "cache_hits": cache_hits,
                "unresolved_voice_count": len(unresolved_voice_ids),
                "uncalibrated": True,
            },
            reason="受控模型生成候选洞察，等待人工复核",
        )
    )
    await session.flush()
    return SemanticBatchResult(
        analysis_run_id=run.id,
        status="pending_review",
        voice_count=len(records),
        signal_count=signal_count,
        cluster_count=len(assignments),
        opportunity_count=opportunity_count,
    )
