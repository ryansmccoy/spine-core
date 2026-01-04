"""Pipeline runner - executes pipelines by execution ID."""

import time
from typing import Any

from market_spine.core.models import ExecutionStatus
from market_spine.execution.ledger import ExecutionLedger
from market_spine.execution.dlq import DLQManager
from market_spine.execution.concurrency import ConcurrencyGuard
from market_spine.pipelines.registry import get_registry
from market_spine.observability.logging import get_logger, bind_context, clear_context
from market_spine.observability.metrics import (
    pipeline_duration_histogram,
    execution_completed_counter,
    execution_status_gauge,
)

logger = get_logger(__name__)


def run_pipeline(execution_id: str) -> dict[str, Any]:
    """
    Run a pipeline by execution ID.

    This is the ONLY function that actually runs pipeline logic.
    It is called by Celery workers (or other backends).

    Steps:
    1. Load execution from ledger
    2. Validate execution can run
    3. Acquire lock if needed
    4. Update status to RUNNING
    5. Execute pipeline handler
    6. Update status to COMPLETED or FAILED
    7. Handle DLQ on failure
    """
    ledger = ExecutionLedger()
    dlq = DLQManager()
    guard = ConcurrencyGuard()
    registry = get_registry()

    # Bind execution context for logging
    bind_context(execution_id=execution_id)

    try:
        # Load execution
        execution = ledger.get_execution(execution_id)
        if execution is None:
            logger.error("execution_not_found", execution_id=execution_id)
            return {"error": "Execution not found"}

        bind_context(pipeline=execution.pipeline)

        # Check if already processed
        if execution.status not in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
            logger.warning(
                "execution_already_processed",
                status=execution.status.value,
            )
            return {"error": f"Execution already in state: {execution.status.value}"}

        # Get pipeline definition
        pipeline_def = registry.get(execution.pipeline)
        if pipeline_def is None:
            logger.error("pipeline_not_found", pipeline=execution.pipeline)
            ledger.update_status(
                execution_id,
                ExecutionStatus.FAILED,
                error=f"Pipeline not found: {execution.pipeline}",
            )
            return {"error": f"Pipeline not found: {execution.pipeline}"}

        # Acquire lock if needed
        lock_key = None
        if pipeline_def.requires_lock and pipeline_def.lock_key_template:
            lock_key = pipeline_def.lock_key_template.format(**execution.params)
            if not guard.acquire(lock_key, execution_id):
                logger.warning("lock_not_acquired", lock_key=lock_key)
                ledger.update_status(
                    execution_id,
                    ExecutionStatus.FAILED,
                    error=f"Could not acquire lock: {lock_key}",
                )
                return {"error": f"Could not acquire lock: {lock_key}"}

        # Update status to running
        ledger.update_status(execution_id, ExecutionStatus.RUNNING)
        execution_status_gauge.labels(
            pipeline=execution.pipeline, status=ExecutionStatus.PENDING.value
        ).dec()
        execution_status_gauge.labels(
            pipeline=execution.pipeline, status=ExecutionStatus.RUNNING.value
        ).inc()

        # Execute pipeline
        start_time = time.time()
        try:
            result = pipeline_def.handler(execution.params)
            duration = time.time() - start_time

            # Success
            ledger.update_status(execution_id, ExecutionStatus.COMPLETED, result=result)
            pipeline_duration_histogram.labels(pipeline=execution.pipeline).observe(duration)
            execution_completed_counter.labels(pipeline=execution.pipeline, result="success").inc()
            execution_status_gauge.labels(
                pipeline=execution.pipeline, status=ExecutionStatus.RUNNING.value
            ).dec()

            logger.info(
                "pipeline_completed",
                duration=duration,
                result=result,
            )
            return result

        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)

            # Failure
            ledger.update_status(execution_id, ExecutionStatus.FAILED, error=error_msg)
            pipeline_duration_histogram.labels(pipeline=execution.pipeline).observe(duration)
            execution_completed_counter.labels(pipeline=execution.pipeline, result="failure").inc()
            execution_status_gauge.labels(
                pipeline=execution.pipeline, status=ExecutionStatus.RUNNING.value
            ).dec()

            # Add to DLQ
            dlq.add_to_dlq(
                execution_id=execution_id,
                pipeline=execution.pipeline,
                params=execution.params,
                error=error_msg,
                retry_count=execution.retry_count,
            )

            logger.error(
                "pipeline_failed",
                duration=duration,
                error=error_msg,
            )
            return {"error": error_msg}

        finally:
            # Release lock
            if lock_key:
                guard.release(lock_key, execution_id)

    finally:
        clear_context()
