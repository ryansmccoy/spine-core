"""Dispatcher - Submit executions to the orchestration backend."""

from typing import Any

import structlog

from market_spine.config import get_settings
from market_spine.repositories.executions import ExecutionRepository

logger = structlog.get_logger()


class Dispatcher:
    """
    Dispatcher for submitting pipeline executions.

    The dispatcher is the canonical entry point for executing pipelines.
    It creates an execution record and submits it to the configured backend.

    Usage:
        dispatcher = Dispatcher()
        execution_id = dispatcher.submit("otc.ingest", {"file_path": "data.csv"})
    """

    def __init__(self, backend=None):
        """
        Initialize the dispatcher.

        Args:
            backend: Optional backend override (defaults to configured backend)
        """
        self._backend = backend

    def _get_backend(self):
        """Get the configured backend (lazy initialization)."""
        if self._backend is None:
            settings = get_settings()

            if settings.backend_type == "local":
                from market_spine.orchestration.backends.local import LocalBackend

                self._backend = LocalBackend()
            else:
                raise ValueError(f"Unknown backend type: {settings.backend_type}")

        return self._backend

    def submit(
        self,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        logical_key: str | None = None,
    ) -> str:
        """
        Submit a pipeline for execution.

        Args:
            pipeline_name: Name of the pipeline to execute
            params: Parameters to pass to the pipeline
            logical_key: Optional unique key for concurrency control

        Returns:
            The execution ID

        Raises:
            ValueError: If there's a logical key conflict
        """
        params = params or {}

        # Check for logical key conflict
        if logical_key:
            existing = ExecutionRepository.check_logical_key_conflict(logical_key)
            if existing:
                logger.warning(
                    "logical_key_conflict",
                    logical_key=logical_key,
                    existing_execution=existing,
                )
                raise ValueError(
                    f"Active execution already exists for logical_key: {logical_key} "
                    f"(execution_id: {existing})"
                )

        # Create execution record
        execution_id = ExecutionRepository.create(
            pipeline_name=pipeline_name,
            params=params,
            logical_key=logical_key,
        )

        # Submit to backend
        backend = self._get_backend()
        backend_run_id = backend.submit(execution_id)

        if backend_run_id:
            ExecutionRepository.set_backend(
                execution_id,
                backend=backend.name,
                backend_run_id=backend_run_id,
            )

        logger.info(
            "execution_submitted",
            execution_id=execution_id,
            pipeline_name=pipeline_name,
            backend=backend.name,
        )

        return execution_id

    def cancel(self, execution_id: str) -> bool:
        """
        Cancel an execution.

        Args:
            execution_id: The execution to cancel

        Returns:
            True if cancellation was successful
        """
        backend = self._get_backend()
        return backend.cancel(execution_id)


# Convenience function
def submit(
    pipeline_name: str,
    params: dict[str, Any] | None = None,
    logical_key: str | None = None,
) -> str:
    """Submit a pipeline for execution (convenience function)."""
    dispatcher = Dispatcher()
    return dispatcher.submit(pipeline_name, params, logical_key)
