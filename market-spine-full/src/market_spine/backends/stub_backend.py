"""Stub backends for Temporal and Dagster (interface only, not implemented)."""

from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


class TemporalStubBackend:
    """
    Stub backend for Temporal workflow engine.

    This is a placeholder that shows how to integrate with Temporal.
    To implement:
    1. Install temporalio SDK
    2. Define workflows in a workflows/ module
    3. Connect to Temporal server
    4. Replace submit() with workflow.start()
    """

    def __init__(self, namespace: str = "default", task_queue: str = "spine-tasks"):
        """Initialize Temporal backend."""
        self.namespace = namespace
        self.task_queue = task_queue
        self._client = None
        logger.warning("temporal_stub_initialized", message="Temporal backend is a stub")

    async def connect(self) -> None:
        """Connect to Temporal server."""
        # from temporalio.client import Client
        # self._client = await Client.connect("localhost:7233", namespace=self.namespace)
        raise NotImplementedError("Temporal backend not implemented")

    def submit(self, execution_id: str, pipeline: str, lane: str) -> None:
        """Submit workflow to Temporal."""
        # await self._client.start_workflow(
        #     RunPipelineWorkflow.run,
        #     args=[execution_id],
        #     id=f"execution-{execution_id}",
        #     task_queue=self.task_queue,
        # )
        raise NotImplementedError("Temporal backend not implemented")

    def cancel(self, execution_id: str) -> bool:
        """Cancel a Temporal workflow."""
        # handle = self._client.get_workflow_handle(f"execution-{execution_id}")
        # await handle.cancel()
        raise NotImplementedError("Temporal backend not implemented")


class DagsterStubBackend:
    """
    Stub backend for Dagster orchestration.

    This is a placeholder that shows how to integrate with Dagster.
    To implement:
    1. Define assets and jobs in a dagster module
    2. Use dagster-webserver or dagster-daemon
    3. Replace submit() with job launch
    """

    def __init__(self, host: str = "localhost", port: int = 3000):
        """Initialize Dagster backend."""
        self.host = host
        self.port = port
        logger.warning("dagster_stub_initialized", message="Dagster backend is a stub")

    def submit(self, execution_id: str, pipeline: str, lane: str) -> None:
        """Submit job to Dagster."""
        # Use Dagster GraphQL API to launch a run
        # mutation {
        #   launchRun(executionParams: {...}) {
        #     run { runId }
        #   }
        # }
        raise NotImplementedError("Dagster backend not implemented")

    def cancel(self, execution_id: str) -> bool:
        """Cancel a Dagster run."""
        raise NotImplementedError("Dagster backend not implemented")


class PrefectStubBackend:
    """
    Stub backend for Prefect orchestration.

    This is a placeholder that shows how to integrate with Prefect.
    To implement:
    1. Define flows in a prefect module
    2. Deploy flows to Prefect server/cloud
    3. Replace submit() with flow.run()
    """

    def __init__(self, api_url: str = "http://localhost:4200/api"):
        """Initialize Prefect backend."""
        self.api_url = api_url
        logger.warning("prefect_stub_initialized", message="Prefect backend is a stub")

    def submit(self, execution_id: str, pipeline: str, lane: str) -> None:
        """Submit flow run to Prefect."""
        # from prefect import get_client
        # async with get_client() as client:
        #     await client.create_flow_run(...)
        raise NotImplementedError("Prefect backend not implemented")

    def cancel(self, execution_id: str) -> bool:
        """Cancel a Prefect flow run."""
        raise NotImplementedError("Prefect backend not implemented")
