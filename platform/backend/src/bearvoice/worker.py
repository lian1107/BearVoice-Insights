import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from bearvoice.config import Settings
from bearvoice.modules.analysis.activities import execute_analysis_phase
from bearvoice.modules.analysis.workflow import AnalysisWorkflow


async def run_worker() -> None:
    settings = Settings()
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue="bearvoice-analysis",
        workflows=[AnalysisWorkflow],
        activities=[execute_analysis_phase],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
