"""Local synchronous backend for testing and development."""

from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


class LocalBackend:
    """Synchronous local execution backend (for testing)."""

    def __init__(self):
        """Initialize local backend."""
        self._pending: list[str] = []

    def submit(self, execution_id: str, pipeline: str, lane: str) -> None:
        """Queue an execution locally (does not run immediately)."""
        self._pending.append(execution_id)
        logger.info(
            "local_task_queued",
            execution_id=execution_id,
            pipeline=pipeline,
        )

    def cancel(self, execution_id: str) -> bool:
        """Cancel a pending local execution."""
        if execution_id in self._pending:
            self._pending.remove(execution_id)
            return True
        return False

    def run_pending(self) -> None:
        """Run all pending executions synchronously."""
        from market_spine.pipelines.runner import run_pipeline

        while self._pending:
            execution_id = self._pending.pop(0)
            run_pipeline(execution_id)

    def clear(self) -> None:
        """Clear pending executions."""
        self._pending.clear()
