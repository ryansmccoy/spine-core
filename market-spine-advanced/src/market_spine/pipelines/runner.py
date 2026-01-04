"""Pipeline runner - Orchestrates pipeline execution with backend support."""

from datetime import datetime
from typing import Any

import structlog

from market_spine.pipelines.base import Pipeline, PipelineResult, StepStatus
from market_spine.pipelines.registry import PipelineRegistry
from market_spine.repositories.executions import ExecutionRepository, ExecutionEventRepository
from market_spine.orchestration import DLQManager

logger = structlog.get_logger()


class PipelineRunner:
    """
    Runs pipelines with execution tracking and DLQ support.

    This is the synchronous execution path. For async execution,
    use the orchestration backends (Local or Celery).
    """

    @classmethod
    def run(
        cls,
        execution_id: str,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """
        Run a pipeline for a given execution ID.

        This updates execution status and emits events as the pipeline runs.
        """
        params = params or {}
        exec_repo = ExecutionRepository()
        event_repo = ExecutionEventRepository()

        # Get pipeline class
        try:
            pipeline_class = PipelineRegistry.get_or_raise(pipeline_name)
        except ValueError as e:
            exec_repo.update_status(execution_id, "failed", str(e))
            return PipelineResult(success=False, error=str(e))

        # Instantiate pipeline
        pipeline = pipeline_class()

        # Mark as running
        exec_repo.update_status(execution_id, "running")
        event_repo.emit(
            execution_id,
            "pipeline.started",
            {"pipeline_name": pipeline_name, "params": params},
        )

        # Execute pipeline
        logger.info(
            "pipeline_execution_started",
            execution_id=execution_id,
            pipeline=pipeline_name,
        )

        try:
            result = pipeline.execute(params)
        except Exception as e:
            logger.exception(
                "pipeline_execution_error",
                execution_id=execution_id,
                pipeline=pipeline_name,
                error=str(e),
            )
            result = PipelineResult(success=False, error=str(e))

        # Emit step events
        for i, step_result in enumerate(result.steps):
            step_name = pipeline.steps[i].name if i < len(pipeline.steps) else f"step_{i}"
            event_repo.emit(
                execution_id,
                f"step.{step_result.status.value}",
                {
                    "step_name": step_name,
                    "duration_ms": step_result.duration_ms,
                    "error": step_result.error,
                },
                idempotency_key=f"{execution_id}:{step_name}:{step_result.status.value}",
            )

        # Update final status
        if result.success:
            exec_repo.update_status(execution_id, "completed")
            event_repo.emit(
                execution_id,
                "pipeline.completed",
                {"duration_ms": result.total_duration_ms},
            )
            logger.info(
                "pipeline_execution_completed",
                execution_id=execution_id,
                pipeline=pipeline_name,
                duration_ms=result.total_duration_ms,
            )
        else:
            # Check if should go to DLQ
            execution = exec_repo.get(execution_id)
            retry_count = execution.get("retry_count", 0) if execution else 0
            max_retries = execution.get("max_retries", 3) if execution else 3

            if retry_count >= max_retries:
                # Move to DLQ
                DLQManager.move_to_dlq(execution_id, result.error or "Unknown error")
                event_repo.emit(
                    execution_id,
                    "pipeline.dlq",
                    {"error": result.error, "retry_count": retry_count},
                )
                logger.warning(
                    "pipeline_moved_to_dlq",
                    execution_id=execution_id,
                    pipeline=pipeline_name,
                    retry_count=retry_count,
                )
            else:
                exec_repo.update_status(execution_id, "failed", result.error)
                event_repo.emit(
                    execution_id,
                    "pipeline.failed",
                    {"error": result.error, "duration_ms": result.total_duration_ms},
                )
                logger.error(
                    "pipeline_execution_failed",
                    execution_id=execution_id,
                    pipeline=pipeline_name,
                    error=result.error,
                )

        return result

    @classmethod
    def run_direct(
        cls,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """
        Run a pipeline directly without execution tracking.

        Useful for testing or one-off runs.
        """
        params = params or {}

        pipeline_class = PipelineRegistry.get_or_raise(pipeline_name)
        pipeline = pipeline_class()

        return pipeline.execute(params)
