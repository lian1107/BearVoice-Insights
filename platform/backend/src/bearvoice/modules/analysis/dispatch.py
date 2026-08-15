import uuid

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from bearvoice.config import Settings
from bearvoice.modules.analysis.workflow import SemanticBatchWorkflow


class TemporalSemanticJobDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def enqueue(self, job_id: uuid.UUID, workflow_id: str) -> None:
        client = await Client.connect(self._settings.temporal_address)
        try:
            await client.start_workflow(
                SemanticBatchWorkflow.run,
                str(job_id),
                id=workflow_id,
                task_queue="bearvoice-analysis",
            )
        except WorkflowAlreadyStartedError:
            # The workflow ID is the durable idempotency boundary. A lost HTTP
            # acknowledgement must not create a second billable model job.
            return
