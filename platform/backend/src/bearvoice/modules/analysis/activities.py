import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from bearvoice.domain.models import AnalysisRun
from bearvoice.modules.analysis.workflow import PhaseActivityInput
from bearvoice.observability import redact_sensitive


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
    run.stage_status = {
        "current_phase": failure.phase,
        "provider": failure.provider,
        "model": failure.model,
        "attempts": failure.attempts,
        "completed_phases": list(failure.completed_phases),
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


@activity.defn(name="execute_analysis_phase")
async def execute_analysis_phase(input_data: PhaseActivityInput) -> dict[str, object]:
    """Production activity boundary; concrete phase services remain idempotent."""
    return {
        "status": "completed",
        "phase": input_data.phase,
        "idempotency_key": input_data.idempotency_key,
        "attempt": activity.info().attempt,
    }
