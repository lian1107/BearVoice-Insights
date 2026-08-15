from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@dataclass(frozen=True)
class AnalysisWorkflowInput:
    run_id: str
    input_hash: str
    cache_only: bool = True


@dataclass(frozen=True)
class PhaseActivityInput:
    run_id: str
    phase: str
    input_hash: str
    idempotency_key: str
    cache_only: bool
    reviewer_id: str | None = None


@dataclass(frozen=True)
class AnalysisWorkflowResult:
    run_id: str
    status: str
    approved_by: str
    completed_phases: tuple[str, ...]


AUTOMATED_PHASES = (
    "validate",
    "privacy_gate",
    "extract",
    "embed",
    "cluster",
    "draft_opportunities",
    "quality_gate",
)


@workflow.defn
class AnalysisWorkflow:
    def __init__(self) -> None:
        self.phase = "pending"
        self.approved_by: str | None = None
        self.completed_phases: list[str] = []

    @workflow.query
    def current_phase(self) -> str:
        return self.phase

    @workflow.signal
    def approve_taxonomy(self, reviewer_id: str) -> None:
        if reviewer_id.strip():
            self.approved_by = reviewer_id

    @workflow.run
    async def run(
        self,
        input_data: AnalysisWorkflowInput,
    ) -> AnalysisWorkflowResult:
        for phase in AUTOMATED_PHASES:
            self.phase = phase
            await workflow.execute_activity(
                "execute_analysis_phase",
                PhaseActivityInput(
                    run_id=input_data.run_id,
                    phase=phase,
                    input_hash=input_data.input_hash,
                    idempotency_key=(
                        f"{input_data.run_id}:{phase}:{input_data.input_hash}"
                    ),
                    cache_only=input_data.cache_only,
                    reviewer_id=None,
                ),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(milliseconds=100),
                    backoff_coefficient=2,
                    maximum_attempts=3,
                ),
            )
            self.completed_phases.append(phase)

        self.phase = "pending_review"
        await workflow.wait_condition(lambda: self.approved_by is not None)

        self.phase = "publish"
        await workflow.execute_activity(
            "execute_analysis_phase",
            PhaseActivityInput(
                run_id=input_data.run_id,
                phase="publish",
                input_hash=input_data.input_hash,
                idempotency_key=(
                    f"{input_data.run_id}:publish:{input_data.input_hash}"
                ),
                cache_only=input_data.cache_only,
                reviewer_id=self.approved_by,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        self.completed_phases.append("publish")
        self.phase = "succeeded"
        return AnalysisWorkflowResult(
            run_id=input_data.run_id,
            status="succeeded",
            approved_by=self.approved_by or "",
            completed_phases=tuple(self.completed_phases),
        )


@workflow.defn
class SemanticBatchWorkflow:
    @workflow.run
    async def run(self, job_id: str) -> dict[str, Any]:
        try:
            return await workflow.execute_activity(
                "execute_model_analysis_job",
                job_id,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=2,
                    maximum_interval=timedelta(minutes=1),
                    maximum_attempts=3,
                ),
            )
        except ActivityError as error:
            await workflow.execute_activity(
                "mark_model_analysis_job_failed",
                {"job_id": job_id, "message": str(error)},
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return {"job_id": job_id, "status": "failed"}
