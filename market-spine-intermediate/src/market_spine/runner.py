"""Runner - Execute pipelines by execution ID."""

import json
import traceback
from typing import Any

import structlog

from market_spine.db import get_connection
from market_spine.registry import registry
from market_spine.repositories.executions import ExecutionRepository, ExecutionEventRepository

logger = structlog.get_logger()


def run_pipeline(execution_id: str) -> dict[str, Any]:
    """
    Execute a pipeline for the given execution ID.

    This function:
    1. Loads the execution record
    2. Gets the pipeline from the registry
    3. Executes the pipeline
    4. Updates the execution status
    5. Emits events

    Args:
        execution_id: The execution ID to run

    Returns:
        The pipeline result
    """
    log = logger.bind(execution_id=execution_id)
    log.info("run_pipeline_start")

    # Load execution
    execution = ExecutionRepository.get(execution_id)
    if not execution:
        raise ValueError(f"Execution not found: {execution_id}")

    pipeline_name = execution["pipeline_name"]
    params = execution["params"] or {}

    # Handle JSON string params (from database)
    if isinstance(params, str):
        params = json.loads(params)

    log = log.bind(pipeline_name=pipeline_name)

    # Get pipeline
    pipeline = registry.get(pipeline_name)
    if not pipeline:
        error_msg = f"Pipeline not found: {pipeline_name}"
        ExecutionRepository.update_status(execution_id, "failed", error_message=error_msg)
        raise ValueError(error_msg)

    # Emit start event
    ExecutionEventRepository.emit(
        execution_id=execution_id,
        event_type="pipeline_started",
        payload={"pipeline_name": pipeline_name, "params": params},
        idempotency_key=f"{execution_id}:started",
    )

    try:
        # Validate params
        validation_errors = pipeline.validate_params(params)
        if validation_errors:
            raise ValueError(f"Parameter validation failed: {validation_errors}")

        # Execute
        result = pipeline.execute(params)

        # Success
        ExecutionRepository.update_status(execution_id, "completed")

        ExecutionEventRepository.emit(
            execution_id=execution_id,
            event_type="pipeline_completed",
            payload={"result": result},
            idempotency_key=f"{execution_id}:completed",
        )

        log.info("run_pipeline_completed", result=result)
        return result

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        ExecutionRepository.update_status(execution_id, "failed", error_message=error_msg)

        ExecutionEventRepository.emit(
            execution_id=execution_id,
            event_type="pipeline_failed",
            payload={"error": error_msg, "traceback": error_traceback},
            idempotency_key=f"{execution_id}:failed",
        )

        log.error("run_pipeline_failed", error=error_msg)
        raise


def run_pipeline_sync(
    pipeline_name: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run a pipeline synchronously without creating an execution record.

    Useful for CLI and testing.

    Args:
        pipeline_name: Name of the pipeline to run
        params: Pipeline parameters

    Returns:
        The pipeline result
    """
    params = params or {}

    pipeline = registry.get(pipeline_name)
    if not pipeline:
        raise ValueError(f"Pipeline not found: {pipeline_name}")

    validation_errors = pipeline.validate_params(params)
    if validation_errors:
        raise ValueError(f"Parameter validation failed: {validation_errors}")

    return pipeline.execute(params)
