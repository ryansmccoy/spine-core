"""Dispatcher - High-level API for submitting pipeline executions."""

from typing import Any

import structlog

from market_spine.config import get_settings
from market_spine.pipelines.registry import PipelineRegistry
from market_spine.repositories.executions import ExecutionRepository
from market_spine.orchestration import get_backend

logger = structlog.get_logger()


class Dispatcher:
    """
    High-level API for dispatching pipeline executions.

    Handles:
    - Parameter validation
    - Logical key deduplication
    - Execution record creation
    - Backend submission
    """

    @classmethod
    def submit(
        cls,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
        skip_dedup: bool = False,
    ) -> str:
        """
        Submit a pipeline for execution.

        Returns the execution ID.

        Raises:
            ValueError: If pipeline not found or validation fails
            RuntimeError: If duplicate execution exists (unless skip_dedup=True)
        """
        params = params or {}
        settings = get_settings()
        exec_repo = ExecutionRepository()

        # Get pipeline class and validate
        pipeline_class = PipelineRegistry.get_or_raise(pipeline_name)
        pipeline = pipeline_class()

        valid, error = pipeline.validate_params(params)
        if not valid:
            raise ValueError(f"Invalid parameters for {pipeline_name}: {error}")

        # Check logical key for deduplication
        logical_key = pipeline.get_logical_key(params)
        if logical_key and not skip_dedup:
            existing = exec_repo.check_logical_key_conflict(logical_key)
            if existing:
                raise RuntimeError(
                    f"Duplicate execution: {existing} already running for key {logical_key}"
                )

        # Create execution record
        execution_id = exec_repo.create(
            pipeline_name=pipeline_name,
            params=params,
            logical_key=logical_key,
            max_retries=max_retries,
        )

        # Submit to backend
        backend = get_backend()
        backend.submit(execution_id, pipeline_name, params)

        logger.info(
            "pipeline_dispatched",
            execution_id=execution_id,
            pipeline=pipeline_name,
            backend=settings.backend_type,
        )

        return execution_id

    @classmethod
    def get_status(cls, execution_id: str) -> dict | None:
        """Get execution status and details."""
        exec_repo = ExecutionRepository()
        return exec_repo.get(execution_id)

    @classmethod
    def list_executions(
        cls,
        status: str | None = None,
        pipeline_name: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List executions with optional filters."""
        exec_repo = ExecutionRepository()
        return exec_repo.list_executions(status, pipeline_name, limit)

    @classmethod
    def cancel(cls, execution_id: str) -> bool:
        """
        Attempt to cancel an execution.

        Only works for pending/queued executions.
        """
        exec_repo = ExecutionRepository()
        execution = exec_repo.get(execution_id)

        if not execution:
            return False

        if execution["status"] not in ("pending", "queued"):
            logger.warning(
                "cannot_cancel_execution",
                execution_id=execution_id,
                status=execution["status"],
            )
            return False

        return exec_repo.update_status(execution_id, "cancelled")
