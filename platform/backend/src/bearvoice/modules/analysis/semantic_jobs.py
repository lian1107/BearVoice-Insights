import hashlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, ROUND_UP
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from bearvoice.config import Settings
from bearvoice.db import async_session_factory
from bearvoice.domain.models import (
    AuditEvent,
    IngestionBatch,
    ModelAnalysisJob,
    ModelBudgetCounter,
    VoiceRecord,
)
from bearvoice.modules.analysis.china_model_adapter import (
    ChinaModelProvider,
    provider_config_from_settings,
)
from bearvoice.modules.analysis.semantic_persistence import run_semantic_analysis
from bearvoice.observability import redact_sensitive


class ModelBudgetExceeded(ValueError):
    pass


def serialize_model_job(job: ModelAnalysisJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "analysis_run_id": job.analysis_run_id,
        "batch_id": job.ingestion_batch_id,
        "status": job.status,
        "product": job.product,
        "analysis_provider": job.provider,
        "requested_items": job.requested_items,
        "processed_items": job.processed_items,
        "model_calls": job.model_calls,
        "signal_count": job.signal_count,
        "cluster_count": job.cluster_count,
        "opportunity_count": job.opportunity_count,
        "attempt_count": job.attempt_count,
        "reserved_cost_amount": float(job.reserved_cost_amount),
        "input_tokens": job.input_tokens,
        "output_tokens": job.output_tokens,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "notice": (
            "AI 分析已完成，候选洞察等待人工复核"
            if job.status == "succeeded"
            else "AI 分析已安全终止，未写入不完整候选结果"
            if job.status == "failed"
            else "AI 分析正在后台分批处理，可安全离开页面"
        ),
    }


async def create_model_analysis_job(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    product: str,
    provider: ChinaModelProvider,
    actor_id: str,
    settings: Settings,
) -> tuple[ModelAnalysisJob, bool]:
    batch = await session.get(IngestionBatch, batch_id)
    if batch is None:
        raise LookupError("导入批次不存在")
    provider_config = provider_config_from_settings(settings, provider)
    requested_items = int(
        await session.scalar(
            select(func.count())
            .select_from(VoiceRecord)
            .where(
                VoiceRecord.ingestion_batch_id == batch.id,
                VoiceRecord.product == product,
            )
        )
        or 0
    )
    if requested_items == 0:
        raise ValueError("该批次没有可分析的产品原声")

    idempotency_source = ":".join(
        (str(batch.id), batch.file_hash, product, provider, provider_config.model)
    )
    idempotency_key = hashlib.sha256(idempotency_source.encode()).hexdigest()
    existing = await session.scalar(
        select(ModelAnalysisJob).where(
            ModelAnalysisJob.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing, True

    if requested_items > settings.model_job_max_calls:
        raise ModelBudgetExceeded(
            f"本批需要 {requested_items} 次调用，超过单任务上限 "
            f"{settings.model_job_max_calls} 次"
        )
    reserved_calls = min(
        requested_items * settings.semantic_retry_max_attempts,
        settings.model_job_max_calls,
    )
    if reserved_calls > settings.model_daily_max_calls:
        raise ModelBudgetExceeded(
            f"本批含有界重试最多预留 {reserved_calls} 次调用，超过单日上限 "
            f"{settings.model_daily_max_calls} 次"
        )
    reserved_cost = (
        Decimal(str(settings.model_reserved_cost_per_call_rmb)) * reserved_calls
    ).quantize(Decimal("0.0001"), rounding=ROUND_UP)
    if reserved_cost > Decimal(str(settings.model_job_budget_rmb)):
        raise ModelBudgetExceeded(
            f"本批预留预算 ¥{reserved_cost}，超过单任务上限 "
            f"¥{settings.model_job_budget_rmb:.2f}"
        )
    if reserved_cost > Decimal(str(settings.model_daily_budget_rmb)):
        raise ModelBudgetExceeded(
            f"本批预留预算 ¥{reserved_cost}，超过单日上限 "
            f"¥{settings.model_daily_budget_rmb:.2f}"
        )

    today = datetime.now(UTC).date()
    counter_insert = insert(ModelBudgetCounter).values(
        id=uuid.uuid4(),
        budget_date=today,
        provider=provider,
        reserved_calls=reserved_calls,
        reserved_cost_amount=reserved_cost,
    )
    reservation = counter_insert.on_conflict_do_update(
        index_elements=[ModelBudgetCounter.budget_date, ModelBudgetCounter.provider],
        set_={
            "reserved_calls": ModelBudgetCounter.reserved_calls + reserved_calls,
            "reserved_cost_amount": (
                ModelBudgetCounter.reserved_cost_amount + reserved_cost
            ),
        },
        where=and_(
            ModelBudgetCounter.reserved_calls + reserved_calls
            <= settings.model_daily_max_calls,
            ModelBudgetCounter.reserved_cost_amount + reserved_cost
            <= Decimal(str(settings.model_daily_budget_rmb)),
        ),
    ).returning(ModelBudgetCounter.id)
    if await session.scalar(reservation) is None:
        raise ModelBudgetExceeded("今日模型调用次数或金额预算已经达到管理员上限")

    job_id = uuid.uuid4()
    job = ModelAnalysisJob(
        id=job_id,
        ingestion_batch_id=batch.id,
        idempotency_key=idempotency_key,
        workflow_id=f"semantic-analysis-{job_id}",
        product=product,
        provider=provider,
        requested_by=actor_id,
        status="queued",
        requested_items=requested_items,
        processed_items=0,
        model_calls=0,
        signal_count=0,
        cluster_count=0,
        opportunity_count=0,
        attempt_count=0,
        reserved_cost_amount=reserved_cost,
        input_tokens=0,
        output_tokens=0,
    )
    session.add(job)
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action="analysis.model_job_queued",
            subject_type="model_analysis_job",
            subject_id=job.id,
            after_state={
                "batch_id": str(batch.id),
                "provider": provider,
                "requested_items": requested_items,
                "reserved_calls": reserved_calls,
                "reserved_cost_amount": str(reserved_cost),
            },
            reason="外部模型任务通过预算门禁后进入后台队列",
        )
    )
    await session.flush()
    return job, False


async def execute_model_analysis_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    attempt: int,
    heartbeat_callback: Callable[[dict[str, int]], None] | None = None,
) -> ModelAnalysisJob:
    job = await session.scalar(
        select(ModelAnalysisJob)
        .where(ModelAnalysisJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise LookupError("模型分析任务不存在")
    if job.status in {"succeeded", "failed"}:
        return job
    job.status = "running"
    job.attempt_count = max(job.attempt_count, attempt)
    job.started_at = job.started_at or datetime.now(UTC)
    await session.commit()

    async def record_progress(
        run_id: uuid.UUID,
        processed_items: int,
        model_calls: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        job.analysis_run_id = run_id
        job.processed_items = processed_items
        job.model_calls = model_calls
        job.input_tokens = input_tokens
        job.output_tokens = output_tokens
        if heartbeat_callback is not None:
            heartbeat_callback(
                {
                    "processed_items": processed_items,
                    "model_calls": model_calls,
                }
            )
        await session.commit()

    cost_per_call = Decimal(str(settings.model_reserved_cost_per_call_rmb))
    model_call_limit = int(job.reserved_cost_amount / cost_per_call)

    result = await run_semantic_analysis(
        session,
        batch_id=job.ingestion_batch_id,
        product=job.product,
        provider=job.provider,  # type: ignore[arg-type]
        actor_id=job.requested_by,
        settings=settings,
        progress_callback=record_progress,
        model_call_limit=model_call_limit,
    )
    job.analysis_run_id = result.analysis_run_id
    job.status = "succeeded" if result.status != "failed" else "failed"
    job.processed_items = result.voice_count if job.status == "succeeded" else job.processed_items
    job.completed_at = datetime.now(UTC)
    job.signal_count = result.signal_count
    job.cluster_count = result.cluster_count
    job.opportunity_count = result.opportunity_count
    job.error_code = result.error_code
    if job.status == "failed":
        job.error_message = "模型调用或输出校验在重试后仍失败"
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=job.requested_by,
            action=f"analysis.model_job_{job.status}",
            subject_type="model_analysis_job",
            subject_id=job.id,
            after_state={
                "analysis_run_id": str(result.analysis_run_id),
                "processed_items": job.processed_items,
                "model_calls": job.model_calls,
                "attempt_count": job.attempt_count,
                "error_code": job.error_code,
            },
            reason="后台分批模型分析结束",
        )
    )
    await session.flush()
    return job


async def mark_model_analysis_job_failed(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    message: str,
) -> None:
    job = await session.get(ModelAnalysisJob, job_id)
    if job is None or job.status in {"succeeded", "failed"}:
        return
    job.status = "failed"
    job.completed_at = datetime.now(UTC)
    job.error_code = "workflow_exhausted"
    job.error_message = redact_sensitive(message)[:4_000]
    await session.flush()


@activity.defn(name="execute_model_analysis_job")
async def execute_model_analysis_job_activity(job_id: str) -> dict[str, Any]:
    settings = Settings()
    async with async_session_factory() as session:
        job = await execute_model_analysis_job(
            session,
            job_id=uuid.UUID(job_id),
            settings=settings,
            attempt=activity.info().attempt,
            heartbeat_callback=activity.heartbeat,
        )
        await session.commit()
        return serialize_model_job(job)


@activity.defn(name="mark_model_analysis_job_failed")
async def mark_model_analysis_job_failed_activity(payload: dict[str, str]) -> None:
    async with async_session_factory() as session:
        await mark_model_analysis_job_failed(
            session,
            job_id=uuid.UUID(payload["job_id"]),
            message=payload["message"],
        )
        await session.commit()
