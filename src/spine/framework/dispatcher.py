"""
Dispatcher - simplified version for Basic tier.

This is the stable interface that will evolve into the full dispatcher
in Advanced/Full tiers. For Basic, it's a thin wrapper around the runner.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from spine.framework.exceptions import BadParamsError, PipelineNotFoundError
from spine.framework.logging import clear_context, get_logger, log_step, set_context
from spine.framework.pipelines import PipelineResult, PipelineStatus
from spine.framework.runner import get_runner

log = get_logger(__name__)


class TriggerSource(str, Enum):
    """Source that triggered the execution."""

    CLI = "cli"
    API = "api"
    SCHEDULER = "scheduler"
    RETRY = "retry"
    MANUAL = "manual"


class Lane(str, Enum):
    """Execution lane (queue)."""

    NORMAL = "normal"
    BACKFILL = "backfill"
    SLOW = "slow"


@dataclass
class Execution:
    """Execution record (simplified for Basic tier)."""

    id: str
    pipeline: str
    params: dict[str, Any]
    lane: Lane
    trigger_source: TriggerSource
    logical_key: str | None
    status: PipelineStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: PipelineResult | None = None


class PipelineDispatcher:
    """
    Dispatcher for pipeline executions.

    Basic tier: Synchronous execution (no queue).
    This interface remains stable as we add async execution in higher tiers.
    """

    def __init__(self) -> None:
        self._executions: dict[str, Execution] = {}
        self._runner = get_runner()

    def submit(
        self,
        pipeline: str,
        params: dict[str, Any] | None = None,
        lane: Lane = Lane.NORMAL,
        trigger_source: TriggerSource = TriggerSource.CLI,
        logical_key: str | None = None,
    ) -> Execution:
        """
        Submit a pipeline for execution.

        In Basic tier, this runs synchronously and returns the completed execution.

        Args:
            pipeline: Name of the pipeline to run
            params: Pipeline parameters
            lane: Execution lane (informational in Basic)
            trigger_source: What triggered this execution
            logical_key: Optional concurrency guard key (informational in Basic)

        Returns:
            Execution record with results
        """
        execution_id = str(uuid4())
        now = datetime.now(UTC)

        execution = Execution(
            id=execution_id,
            pipeline=pipeline,
            params=params or {},
            lane=lane,
            trigger_source=trigger_source,
            logical_key=logical_key,
            status=PipelineStatus.PENDING,
            created_at=now,
        )

        # Set logging context for this execution
        set_context(
            execution_id=execution_id,
            pipeline=pipeline,
            backend="sync",
        )

        log.info(
            "execution.submitted",
            lane=lane.value,
            trigger_source=trigger_source.value,
        )
        log.debug("execution.params", param_keys=list((params or {}).keys()))

        # Store execution
        self._executions[execution_id] = execution

        # Run synchronously in Basic tier
        execution.status = PipelineStatus.RUNNING
        execution.started_at = datetime.now(UTC)

        try:
            with log_step("execution.run"):
                result = self._runner.run(pipeline, params)

            execution.status = result.status
            execution.completed_at = result.completed_at
            execution.error = result.error
            execution.result = result

            # Build summary fields
            summary_fields = {
                "status": execution.status.value,
                "duration_ms": round(result.duration_seconds * 1000, 2) if result.duration_seconds else None,
            }

            # Add row metrics from result if available
            if result.metrics:
                if "rows" in result.metrics:
                    summary_fields["rows_out"] = result.metrics["rows"]
                if "weeks" in result.metrics:
                    summary_fields["weeks"] = result.metrics["weeks"]

            # Handle success vs failure logging
            if execution.status == PipelineStatus.COMPLETED:
                log.info("execution.summary", **summary_fields)
            else:
                # Add error details for failures
                if result.error:
                    summary_fields["error_type"] = "PipelineError"
                    summary_fields["error_message"] = result.error
                log.error("execution.summary", **summary_fields)

        except PipelineNotFoundError as e:
            # Pipeline doesn't exist in registry
            execution.status = PipelineStatus.FAILED
            execution.completed_at = datetime.now(UTC)
            execution.error = str(e)

            log.error(
                "execution.pipeline_not_found",
                status="failed",
                error_type="PipelineNotFoundError",
                error_message=str(e),
                pipeline_name=pipeline,
            )
            # Re-raise so CLI can handle it
            raise

        except BadParamsError as e:
            # Parameters are missing or invalid
            execution.status = PipelineStatus.FAILED
            execution.completed_at = datetime.now(UTC)
            execution.error = str(e)

            log.error(
                "execution.params_invalid",
                status="failed",
                error_type="BadParamsError",
                error_message=str(e),
                missing_params=e.missing_params,
                invalid_params=e.invalid_params,
            )
            # Re-raise so CLI can handle it
            raise

        except Exception as e:
            # Handle unexpected exceptions (pipeline should catch its own)
            import traceback

            execution.status = PipelineStatus.FAILED
            execution.completed_at = datetime.now(UTC)
            execution.error = str(e)

            log.error(
                "execution.summary",
                status="failed",
                error_type=type(e).__name__,
                error_message=str(e),
                error_stack=traceback.format_exc(),
            )
        finally:
            # Clear context after execution
            clear_context()

        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        """Get execution by ID."""
        return self._executions.get(execution_id)

    def list_executions(
        self,
        pipeline: str | None = None,
        status: PipelineStatus | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        """List executions with optional filters."""
        executions = list(self._executions.values())

        if pipeline:
            executions = [e for e in executions if e.pipeline == pipeline]
        if status:
            executions = [e for e in executions if e.status == status]

        # Sort by created_at descending
        executions.sort(key=lambda e: e.created_at, reverse=True)

        return executions[:limit]


