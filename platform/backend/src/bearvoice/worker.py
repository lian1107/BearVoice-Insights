import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from bearvoice.config import Settings
from bearvoice.modules.analysis.activities import execute_analysis_phase
from bearvoice.modules.analysis.semantic_jobs import (
    execute_model_analysis_job_activity,
    mark_model_analysis_job_failed_activity,
)
from bearvoice.modules.analysis.workflow import AnalysisWorkflow, SemanticBatchWorkflow


async def run_worker() -> None:
    settings = Settings()
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue="bearvoice-analysis",
        workflows=[AnalysisWorkflow, SemanticBatchWorkflow],
        activities=[
            execute_analysis_phase,
            execute_model_analysis_job_activity,
            mark_model_analysis_job_failed_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
