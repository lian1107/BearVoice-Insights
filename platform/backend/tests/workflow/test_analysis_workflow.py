import asyncio
from collections import Counter

import pytest

from bearvoice.modules.analysis.workflow import (
    AnalysisWorkflow,
    AnalysisWorkflowInput,
    PhaseActivityInput,
    SemanticBatchWorkflow,
)
from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


async def wait_for_phase(
    handle: WorkflowHandle,
    expected: str,
) -> None:
    for _ in range(200):
        if await handle.query(AnalysisWorkflow.current_phase) == expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"工作流未进入阶段：{expected}")


@pytest.mark.asyncio
async def test_workflow_retries_activity_and_waits_for_human_approval():
    attempts: Counter[str] = Counter()
    idempotency_keys: list[str] = []

    @activity.defn(name="execute_analysis_phase")
    async def execute_phase(input_data: PhaseActivityInput):
        attempts[input_data.phase] += 1
        idempotency_keys.append(input_data.idempotency_key)
        if input_data.phase == "extract" and attempts["extract"] == 1:
            raise ApplicationError("transient extract failure")
        return {"status": "completed"}

    async with await WorkflowEnvironment.start_time_skipping() as environment:
        task_queue = "analysis-workflow-test"
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=[AnalysisWorkflow],
            activities=[execute_phase],
        ):
            handle = await environment.client.start_workflow(
                AnalysisWorkflow.run,
                AnalysisWorkflowInput(
                    run_id="run-1",
                    input_hash="sha256:fixture",
                    cache_only=True,
                ),
                id="analysis-run-1",
                task_queue=task_queue,
            )
            await wait_for_phase(handle, "pending_review")
            assert (
                await handle.query(AnalysisWorkflow.current_phase)
                == "pending_review"
            )
            await handle.signal(
                AnalysisWorkflow.approve_taxonomy,
                "reviewer-1",
            )
            result = await handle.result()

    assert result.status == "succeeded"
    assert result.approved_by == "reviewer-1"
    assert attempts["extract"] == 2
    assert idempotency_keys.count("run-1:extract:sha256:fixture") == 2


@pytest.mark.asyncio
async def test_semantic_batch_workflow_retries_transient_worker_failure():
    attempts = 0

    @activity.defn(name="execute_model_analysis_job")
    async def execute_job(job_id: str):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ApplicationError("temporary worker failure")
        return {"job_id": job_id, "status": "succeeded"}

    @activity.defn(name="mark_model_analysis_job_failed")
    async def mark_failed(_payload: dict[str, str]):
        raise AssertionError("成功重试时不应标记失败")

    async with await WorkflowEnvironment.start_time_skipping() as environment:
        task_queue = "semantic-batch-test"
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=[SemanticBatchWorkflow],
            activities=[execute_job, mark_failed],
        ):
            result = await environment.client.execute_workflow(
                SemanticBatchWorkflow.run,
                "job-1",
                id="semantic-job-1",
                task_queue=task_queue,
            )

    assert result == {"job_id": "job-1", "status": "succeeded"}
    assert attempts == 2
