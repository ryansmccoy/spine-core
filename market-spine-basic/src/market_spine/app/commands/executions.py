"""
Pipeline execution commands.

These commands handle running pipelines with parameters,
supporting both actual execution and dry-run preview.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from market_spine.app.models import (
    CommandError,
    ErrorCode,
    ExecutionMetrics,
    ExecutionStatus,
    Result,
)
from market_spine.app.services.ingest import IngestResolution, IngestResolver
from market_spine.app.services.params import ParameterResolver
from market_spine.app.services.tier import TierNormalizer
from spine.framework.dispatcher import Dispatcher, Lane, TriggerSource
from spine.framework.exceptions import BadParamsError, PipelineNotFoundError
from spine.framework.pipelines import PipelineStatus

# =============================================================================
# Run Pipeline Command
# =============================================================================


@dataclass
class RunPipelineRequest:
    """Input for running a pipeline."""

    pipeline: str
    params: dict[str, Any] = field(default_factory=dict)
    lane: str = "normal"
    dry_run: bool = False
    trigger_source: str = "cli"  # "cli" | "api"


@dataclass
class RunPipelineResult(Result):
    """
    Output from running a pipeline.

    Fields reserved for future tier evolution are included but nullable.
    Basic tier always returns status=completed or status=failed (synchronous).
    Intermediate tier will return status=pending with poll_url.
    """

    # Execution identification
    execution_id: str | None = None

    # Execution status (Basic: completed/failed/dry_run; Future: pending)
    status: ExecutionStatus | None = None

    # Timing
    duration_seconds: float | None = None

    # Results (only on success)
    metrics: ExecutionMetrics | None = None

    # Ingest resolution (for ingest pipelines)
    ingest_resolution: IngestResolution | None = None

    # Dry run preview data
    dry_run: bool = False
    would_execute: dict[str, Any] | None = None

    # Reserved for future tiers (nullable now)
    poll_url: str | None = None  # Intermediate: URL to poll for status
    owner: str | None = None  # Advanced: Execution owner
    tenant_id: str | None = None  # Full: Tenant context


class RunPipelineCommand:
    """
    Run a pipeline with parameters.

    This command handles the full execution flow:
    1. Normalize parameters (tier aliases, etc.)
    2. Resolve ingest source (if applicable)
    3. Execute via Dispatcher (or preview for dry-run)
    4. Return structured result

    Example:
        command = RunPipelineCommand()
        result = command.execute(RunPipelineRequest(
            pipeline="finra.otc_transparency.normalize_week",
            params={"week_ending": "2025-12-19", "tier": "tier1"},
        ))
        if result.success:
            print(f"Execution {result.execution_id} completed")
    """

    def __init__(
        self,
        tier_normalizer: TierNormalizer | None = None,
        param_resolver: ParameterResolver | None = None,
        ingest_resolver: IngestResolver | None = None,
    ) -> None:
        """Initialize with optional service overrides (for testing)."""
        self._tier_normalizer = tier_normalizer or TierNormalizer()
        self._param_resolver = param_resolver or ParameterResolver(self._tier_normalizer)
        self._ingest_resolver = ingest_resolver or IngestResolver()

    def execute(self, request: RunPipelineRequest) -> RunPipelineResult:
        """
        Execute the run pipeline command.

        Args:
            request: Request with pipeline name and parameters

        Returns:
            Result with execution status, metrics, or error
        """
        # 1. Normalize parameters
        try:
            normalized_params = self._param_resolver.resolve(request.params)
        except ValueError as e:
            return RunPipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INVALID_TIER,
                    message=str(e),
                ),
            )

        # 2. Resolve ingest source (if applicable)
        ingest_resolution = None
        try:
            ingest_resolution = self._ingest_resolver.resolve(
                request.pipeline,
                normalized_params,
            )
        except ValueError as e:
            # Missing required params for ingest resolution
            return RunPipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.MISSING_REQUIRED,
                    message=str(e),
                    details={"context": "ingest_resolution"},
                ),
            )

        # 3. Dry run - return preview without executing
        if request.dry_run:
            return RunPipelineResult(
                success=True,
                execution_id=None,
                status=ExecutionStatus.DRY_RUN,
                dry_run=True,
                would_execute={
                    "pipeline": request.pipeline,
                    "params": normalized_params,
                    "lane": request.lane,
                },
                ingest_resolution=ingest_resolution,
            )

        # 4. Execute via Dispatcher
        start_time = time.time()

        try:
            # Map trigger source
            trigger = TriggerSource.CLI if request.trigger_source == "cli" else TriggerSource.API

            dispatcher = Dispatcher()
            execution = dispatcher.submit(
                pipeline=request.pipeline,
                params=normalized_params,
                lane=Lane(request.lane.lower()) if request.lane else Lane.NORMAL,
                trigger_source=trigger,
            )

            duration = time.time() - start_time

            # Check result status
            if execution.status == PipelineStatus.COMPLETED:
                # Extract metrics from result
                result_metrics = None
                if execution.result and execution.result.metrics:
                    result_metrics = ExecutionMetrics(
                        rows_processed=execution.result.metrics.get("rows_processed"),
                        duration_seconds=duration,
                        capture_id=execution.result.metrics.get("capture_id"),
                        extra={
                            k: v
                            for k, v in execution.result.metrics.items()
                            if k not in ("rows_processed", "capture_id")
                        },
                    )

                return RunPipelineResult(
                    success=True,
                    execution_id=execution.id,
                    status=ExecutionStatus.COMPLETED,
                    duration_seconds=duration,
                    metrics=result_metrics,
                    ingest_resolution=ingest_resolution,
                )
            else:
                # Pipeline failed
                return RunPipelineResult(
                    success=False,
                    execution_id=execution.id,
                    status=ExecutionStatus.FAILED,
                    duration_seconds=duration,
                    error=CommandError(
                        code=ErrorCode.EXECUTION_FAILED,
                        message=str(execution.error) if execution.error else "Pipeline failed",
                    ),
                    ingest_resolution=ingest_resolution,
                )

        except PipelineNotFoundError:
            return RunPipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.PIPELINE_NOT_FOUND,
                    message=f"Pipeline '{request.pipeline}' not found.",
                    details={"pipeline": request.pipeline},
                ),
            )

        except BadParamsError as e:
            return RunPipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INVALID_PARAMS,
                    message="Parameter validation failed.",
                    details={
                        "missing": e.missing_params or [],
                        "invalid": e.invalid_params or [],
                    },
                ),
            )

        except Exception as e:
            duration = time.time() - start_time
            return RunPipelineResult(
                success=False,
                execution_id=None,
                status=ExecutionStatus.FAILED,
                duration_seconds=duration,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Execution error: {e}",
                ),
            )
