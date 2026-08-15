import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from bearvoice.db import async_session_factory
from bearvoice.domain.models import (
    AnalysisRun,
    AuditEvent,
    ClusterMembership,
    Embedding,
    OpportunityEvidence,
    Signal,
    TaxonomyVersion,
    VoiceRecord,
)
from bearvoice.modules.analysis.workflow import PhaseActivityInput
from bearvoice.observability import redact_sensitive


class PhaseVerificationError(RuntimeError):
    pass


PHASE_ORDER = (
    "validate",
    "privacy_gate",
    "extract",
    "embed",
    "cluster",
    "draft_opportunities",
    "quality_gate",
    "publish",
)


@dataclass(frozen=True)
class RunFailure:
    run_id: uuid.UUID
    phase: str
    error_code: str
    provider: str
    model: str | None
    attempts: int
    completed_phases: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class AnalysisRunHistory:
    run_id: uuid.UUID
    phase: str
    error_code: str | None
    provider: str | None
    model: str | None
    attempts: int
    completed_phases: tuple[str, ...]
    redacted_message: str


async def record_run_failure(
    session: AsyncSession,
    failure: RunFailure,
) -> None:
    run = await session.get(AnalysisRun, failure.run_id)
    if run is None:
        raise LookupError(f"分析运行不存在：{failure.run_id}")
    run.error_code = failure.error_code
    run.error_message = redact_sensitive(failure.message)
    previous = dict(run.stage_status or {})
    completed_phases = list(failure.completed_phases) or list(
        previous.get("completed_phases") or []
    )
    run.stage_status = {
        **previous,
        "current_phase": failure.phase,
        "provider": failure.provider,
        "model": failure.model,
        "attempts": failure.attempts,
        "completed_phases": completed_phases,
        "status": "failed",
    }
    await session.flush()


async def load_analysis_run(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> AnalysisRunHistory:
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise LookupError(f"分析运行不存在：{run_id}")
    state = run.stage_status or {}
    return AnalysisRunHistory(
        run_id=run.id,
        phase=str(state.get("current_phase", "pending")),
        error_code=run.error_code,
        provider=state.get("provider"),
        model=state.get("model"),
        attempts=int(state.get("attempts", 0)),
        completed_phases=tuple(state.get("completed_phases", [])),
        redacted_message=run.error_message or "",
    )


async def _phase_facts(
    session: AsyncSession,
    run: AnalysisRun,
    input_data: PhaseActivityInput,
) -> dict[str, object]:
    signal_ids = select(Signal.id).where(Signal.analysis_run_id == run.id)
    voice_ids = select(Signal.voice_record_id).where(
        Signal.analysis_run_id == run.id
    )
    signal_count = int(
        await session.scalar(
            select(func.count()).select_from(Signal).where(
                Signal.analysis_run_id == run.id
            )
        )
        or 0
    )

    if input_data.phase == "validate":
        return {"dataset_hash": run.dataset_hash}

    if signal_count == 0:
        raise PhaseVerificationError(
            f"{input_data.phase} 阶段没有可验证的真实抽取结果"
        )

    invalid_privacy_count = int(
        await session.scalar(
            select(func.count())
            .select_from(VoiceRecord)
            .where(
                VoiceRecord.id.in_(voice_ids),
                VoiceRecord.privacy_status.not_in(("clean", "masked")),
            )
        )
        or 0
    )
    voice_count = int(
        await session.scalar(
            select(func.count(distinct(VoiceRecord.id))).where(
                VoiceRecord.id.in_(voice_ids)
            )
        )
        or 0
    )
    if input_data.phase == "privacy_gate":
        if invalid_privacy_count:
            raise PhaseVerificationError("仍有原声未通过隐私门禁")
        return {"voices": voice_count, "invalid_privacy": 0}

    missing_evidence_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Signal)
            .where(
                Signal.analysis_run_id == run.id,
                func.length(func.trim(Signal.evidence_text)) == 0,
            )
        )
        or 0
    )
    if input_data.phase == "extract":
        if missing_evidence_count:
            raise PhaseVerificationError("抽取结果包含空证据")
        return {"signals": signal_count, "missing_evidence": 0}

    embedding_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Embedding)
            .where(Embedding.signal_id.in_(signal_ids))
        )
        or 0
    )
    if input_data.phase == "embed":
        legacy_import = (
            run.model_version == "legacy-claude-cache"
            and bool((run.parameters or {}).get("cache_only"))
        )
        if legacy_import:
            return {
                "signals": signal_count,
                "embeddings": embedding_count,
                "result": "not_required_for_verified_legacy_import",
            }
        if embedding_count != signal_count:
            raise PhaseVerificationError("向量缓存没有完整覆盖抽取信号")
        return {"signals": signal_count, "embeddings": embedding_count}

    taxonomy_rows = (
        await session.execute(
            select(
                TaxonomyVersion.id,
                func.count(distinct(ClusterMembership.signal_id)),
            )
            .join(
                ClusterMembership,
                ClusterMembership.taxonomy_version_id == TaxonomyVersion.id,
            )
            .join(Signal, Signal.id == ClusterMembership.signal_id)
            .where(Signal.analysis_run_id == run.id)
            .group_by(TaxonomyVersion.id)
        )
    ).all()
    maximum_membership_count = max(
        (int(count) for _, count in taxonomy_rows),
        default=0,
    )
    if input_data.phase == "cluster":
        if maximum_membership_count != signal_count:
            raise PhaseVerificationError("没有分类法完整覆盖本次分析信号")
        return {
            "signals": signal_count,
            "covered_memberships": maximum_membership_count,
        }

    opportunity_row = (
        await session.execute(
            select(
                func.count(distinct(OpportunityEvidence.opportunity_id)),
                func.count(OpportunityEvidence.id),
            )
            .join(Signal, Signal.id == OpportunityEvidence.signal_id)
            .where(Signal.analysis_run_id == run.id)
        )
    ).one()
    opportunity_count, opportunity_evidence_count = map(int, opportunity_row)
    if input_data.phase == "draft_opportunities":
        if opportunity_count == 0 or opportunity_evidence_count == 0:
            raise PhaseVerificationError("没有真实机会草案及其证据")
        return {
            "opportunities": opportunity_count,
            "opportunity_evidence": opportunity_evidence_count,
        }

    mismatched_evidence_count = int(
        await session.scalar(
            select(func.count())
            .select_from(OpportunityEvidence)
            .join(Signal, Signal.id == OpportunityEvidence.signal_id)
            .where(
                Signal.analysis_run_id == run.id,
                OpportunityEvidence.voice_record_id != Signal.voice_record_id,
            )
        )
        or 0
    )
    if input_data.phase == "quality_gate":
        if any(
            (
                invalid_privacy_count,
                missing_evidence_count,
                mismatched_evidence_count,
                maximum_membership_count != signal_count,
                opportunity_count == 0,
            )
        ):
            raise PhaseVerificationError("质量门禁发现数据完整性问题")
        return {
            "invalid_privacy": 0,
            "missing_evidence": 0,
            "mismatched_opportunity_evidence": 0,
            "covered_memberships": maximum_membership_count,
        }

    if input_data.phase == "publish":
        if not (input_data.reviewer_id or "").strip():
            raise PhaseVerificationError("发布阶段缺少人工审核人")
        taxonomy_ids = [row_id for row_id, _ in taxonomy_rows]
        taxonomy = await session.scalar(
            select(TaxonomyVersion)
            .where(
                TaxonomyVersion.id.in_(taxonomy_ids),
                TaxonomyVersion.status.in_(("draft", "published")),
            )
            .order_by(TaxonomyVersion.created_at.desc(), TaxonomyVersion.id.desc())
            .limit(1)
            .with_for_update()
        )
        if taxonomy is None:
            raise PhaseVerificationError("没有可发布的分类法版本")
        if taxonomy.status != "published":
            previous_releases = list(
                await session.scalars(
                    select(TaxonomyVersion)
                    .where(
                        TaxonomyVersion.product_scope == taxonomy.product_scope,
                        TaxonomyVersion.status == "published",
                        TaxonomyVersion.id != taxonomy.id,
                    )
                    .with_for_update()
                )
            )
            for previous in previous_releases:
                previous.status = "superseded"
            taxonomy.status = "published"
            taxonomy.published_by = input_data.reviewer_id.strip()
            taxonomy.published_at = datetime.now(UTC)
            session.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    actor_id=input_data.reviewer_id.strip(),
                    action="taxonomy.published",
                    subject_type="taxonomy_version",
                    subject_id=taxonomy.id,
                    before_state={"status": "draft"},
                    after_state={"status": "published"},
                    reason="耐久工作流收到人工审核批准",
                )
            )
        return {
            "taxonomy_version_id": str(taxonomy.id),
            "published_by": input_data.reviewer_id.strip(),
        }

    raise PhaseVerificationError(f"未知分析阶段：{input_data.phase}")


async def verify_and_record_analysis_phase(
    session: AsyncSession,
    input_data: PhaseActivityInput,
    *,
    attempt: int,
) -> dict[str, object]:
    if input_data.phase not in PHASE_ORDER:
        raise PhaseVerificationError(f"未知分析阶段：{input_data.phase}")
    try:
        run_id = uuid.UUID(input_data.run_id)
    except ValueError as error:
        raise PhaseVerificationError("分析运行 ID 无效") from error
    run = await session.scalar(
        select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update()
    )
    if run is None:
        raise PhaseVerificationError(f"分析运行不存在：{input_data.run_id}")
    if run.dataset_hash != input_data.input_hash:
        raise PhaseVerificationError("工作流输入哈希与分析运行不一致")

    state = dict(run.stage_status or {})
    phase_results = dict(state.get("phase_results") or {})
    existing = phase_results.get(input_data.phase)
    if isinstance(existing, dict):
        if existing.get("idempotency_key") != input_data.idempotency_key:
            raise PhaseVerificationError("已完成阶段收到冲突的幂等键")
        return {**existing, "replayed": True}

    phase_index = PHASE_ORDER.index(input_data.phase)
    if phase_index and PHASE_ORDER[phase_index - 1] not in phase_results:
        raise PhaseVerificationError("分析阶段不能跳过前置阶段")

    facts = await _phase_facts(session, run, input_data)
    result = {
        "status": "completed",
        "phase": input_data.phase,
        "idempotency_key": input_data.idempotency_key,
        "attempt": attempt,
        "facts": facts,
    }
    phase_results[input_data.phase] = result
    completed_phases = [
        phase for phase in PHASE_ORDER if phase in phase_results
    ]
    run.stage_status = {
        **state,
        "phase_results": phase_results,
        "current_phase": input_data.phase,
        "completed_phases": completed_phases,
        "status": "succeeded" if input_data.phase == "publish" else "running",
    }
    run.error_code = None
    run.error_message = None
    await session.flush()
    return result


@activity.defn(name="execute_analysis_phase")
async def execute_analysis_phase(input_data: PhaseActivityInput) -> dict[str, object]:
    """Verify real persisted outputs and record an idempotent phase ledger."""

    attempt = activity.info().attempt
    async with async_session_factory() as session:
        try:
            result = await verify_and_record_analysis_phase(
                session,
                input_data,
                attempt=attempt,
            )
            await session.commit()
            return result
        except PhaseVerificationError as error:
            await session.rollback()
            try:
                run_id = uuid.UUID(input_data.run_id)
                await record_run_failure(
                    session,
                    RunFailure(
                        run_id=run_id,
                        phase=input_data.phase,
                        error_code="phase_verification_failed",
                        provider="cache-only" if input_data.cache_only else "configured",
                        model=None,
                        attempts=attempt,
                        completed_phases=(),
                        message=str(error),
                    ),
                )
                await session.commit()
            except (ValueError, LookupError):
                await session.rollback()
            raise ApplicationError(
                str(error),
                type="phase_verification_failed",
                non_retryable=True,
            ) from error
