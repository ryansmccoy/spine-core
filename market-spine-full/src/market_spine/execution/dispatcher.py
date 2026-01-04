"""Dispatcher - single canonical entrypoint for submitting pipeline executions."""

from typing import Any, Protocol

from market_spine.core.models import Execution, ExecutionStatus, TriggerSource
from market_spine.execution.ledger import ExecutionLedger
from market_spine.observability.logging import get_logger
from market_spine.observability.metrics import (
    execution_submitted_counter,
    execution_status_gauge,
)

logger = get_logger(__name__)


class Backend(Protocol):
    """Protocol for execution backends (Celery, Temporal, etc.)."""

    def submit(self, execution_id: str, pipeline: str, lane: str) -> None:
        """Submit an execution to the backend."""
        ...

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        ...


class Dispatcher:
    """
    Single canonical entrypoint for submitting pipeline executions.

    All execution submissions go through dispatcher.submit():
    - API calls submit()
    - CLI calls submit()
    - Scheduled tasks call submit()
    - Retries call submit()

    The dispatcher:
    1. Creates the execution record in the ledger
    2. Submits to the configured backend (Celery, etc.)
    3. Returns the execution ID
    """

    def __init__(
        self,
        ledger: ExecutionLedger,
        backend: Backend,
    ):
        """Initialize dispatcher with ledger and backend."""
        self._ledger = ledger
        self._backend = backend

    def submit(
        self,
        pipeline: str,
        params: dict[str, Any] | None = None,
        lane: str = "default",
        trigger_source: TriggerSource = TriggerSource.API,
        parent_execution_id: str | None = None,
    ) -> Execution:
        """
        Submit a pipeline execution.

        This is the ONLY way to start a pipeline execution.

        Args:
            pipeline: Name of the pipeline to run
            params: Parameters to pass to the pipeline
            lane: Execution lane (for concurrency control)
            trigger_source: What triggered this execution
            parent_execution_id: Parent execution if this is a retry

        Returns:
            The created Execution record
        """
        # Create execution record
        execution = Execution.create(
            pipeline=pipeline,
            params=params,
            lane=lane,
            trigger_source=trigger_source,
            parent_execution_id=parent_execution_id,
        )

        # Persist to ledger
        self._ledger.create_execution(execution)

        # Submit to backend
        try:
            self._backend.submit(execution.id, pipeline, lane)
            logger.info(
                "execution_submitted",
                execution_id=execution.id,
                pipeline=pipeline,
                lane=lane,
                trigger_source=trigger_source.value,
            )
            # Update metrics
            execution_submitted_counter.labels(pipeline=pipeline).inc()
            execution_status_gauge.labels(
                pipeline=pipeline, status=ExecutionStatus.PENDING.value
            ).inc()
        except Exception as e:
            # If backend submission fails, mark as failed
            self._ledger.update_status(
                execution.id,
                ExecutionStatus.FAILED,
                error=f"Backend submission failed: {e}",
            )
            logger.error(
                "execution_submission_failed",
                execution_id=execution.id,
                error=str(e),
            )
            raise

        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        """Get an execution by ID."""
        return self._ledger.get_execution(execution_id)

    def get_events(self, execution_id: str) -> list:
        """Get events for an execution."""
        return self._ledger.get_events(execution_id)

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        execution = self._ledger.get_execution(execution_id)
        if execution is None:
            return False

        if execution.status not in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
            return False

        try:
            if self._backend.cancel(execution_id):
                self._ledger.update_status(execution_id, ExecutionStatus.CANCELLED)
                return True
        except Exception as e:
            logger.error(
                "execution_cancel_failed",
                execution_id=execution_id,
                error=str(e),
            )
        return False
