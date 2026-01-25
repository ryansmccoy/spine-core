"""Synchronous pipeline runner."""

from datetime import datetime
from typing import Any

from spine.framework.exceptions import BadParamsError, PipelineNotFoundError
from spine.framework.logging import get_logger, log_step
from spine.framework.pipelines import PipelineResult, PipelineStatus
from spine.framework.registry import get_pipeline

log = get_logger(__name__)


class PipelineRunner:
    """
    Synchronous pipeline runner.

    Executes pipelines immediately in the current thread.
    """

    def run(self, pipeline_name: str, params: dict[str, Any] | None = None) -> PipelineResult:
        """
        Run a pipeline by name.

        Args:
            pipeline_name: Name of the registered pipeline
            params: Optional parameters for the pipeline

        Returns:
            PipelineResult with execution details

        Raises:
            PipelineNotFoundError: If pipeline is not registered
            BadParamsError: If parameters are missing or invalid
        """
        log.debug("runner.start", pipeline=pipeline_name)

        try:
            pipeline_cls = get_pipeline(pipeline_name)
        except KeyError:
            raise PipelineNotFoundError(pipeline_name)

        pipeline = pipeline_cls(params=params)

        # Validate parameters using pipeline spec
        if pipeline.spec is not None:
            validation_result = pipeline.spec.validate(params or {})
            if not validation_result.valid:
                raise BadParamsError(
                    validation_result.get_error_message(),
                    missing_params=validation_result.missing_params,
                    invalid_params=validation_result.invalid_params,
                )

        # Validate using pipeline's custom validation (if any)
        try:
            pipeline.validate_params()
        except Exception as e:
            # Wrap any validation errors as BadParamsError
            if not isinstance(e, BadParamsError):
                raise BadParamsError(str(e))
            raise

        # Run the pipeline
        try:
            with log_step("pipeline.run", pipeline=pipeline_name) as timer:
                result = pipeline.run()

            log.info(
                "runner.completed",
                status=result.status.value,
                duration_ms=round(result.duration_seconds * 1000, 2)
                if result.duration_seconds
                else None,
            )

            return result

        except Exception as e:
            log.error("runner.error", error=str(e), error_type=type(e).__name__)
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                error=str(e),
            )

    def run_all(
        self, pipeline_names: list[str], params: dict[str, Any] | None = None
    ) -> list[PipelineResult]:
        """
        Run multiple pipelines in sequence.

        Args:
            pipeline_names: List of pipeline names to run in order
            params: Optional shared parameters

        Returns:
            List of PipelineResults
        """
        results = []
        for name in pipeline_names:
            result = self.run(name, params)
            results.append(result)

            # Stop on failure
            if result.status == PipelineStatus.FAILED:
                log.warning("runner.stopped", failed_at=name)
                break

        return results


# Default runner instance
_runner: PipelineRunner | None = None


def get_runner() -> PipelineRunner:
    """Get or create runner instance."""
    global _runner
    if _runner is None:
        _runner = PipelineRunner()
    return _runner
