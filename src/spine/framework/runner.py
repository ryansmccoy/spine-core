"""Synchronous operation runner.

Manifesto:
    The runner executes operations with consistent lifecycle hooks
    (start → execute → record result) so ops code never manages
    its own timing, error capture, or result storage.

Tags:
    spine-core, framework, runner, synchronous, lifecycle

Doc-Types:
    api-reference
"""

from datetime import UTC, datetime
from typing import Any

from spine.framework.exceptions import BadParamsError, OperationNotFoundError
from spine.framework.logging import get_logger, log_step
from spine.framework.operations import OperationResult, OperationStatus
from spine.framework.registry import get_operation

log = get_logger(__name__)


class OperationRunner:
    """
    Synchronous operation runner.

    Executes operations immediately in the current thread.
    """

    def run(self, operation_name: str, params: dict[str, Any] | None = None) -> OperationResult:
        """
        Run a operation by name.

        Args:
            operation_name: Name of the registered operation
            params: Optional parameters for the operation

        Returns:
            OperationResult with execution details

        Raises:
            OperationNotFoundError: If operation is not registered
            BadParamsError: If parameters are missing or invalid
        """
        log.debug("runner.start", operation=operation_name)

        try:
            operation_cls = get_operation(operation_name)
        except KeyError:
            raise OperationNotFoundError(operation_name) from None

        operation = operation_cls(params=params)

        # Validate parameters using operation spec
        if operation.spec is not None:
            validation_result = operation.spec.validate(params or {})
            if not validation_result.valid:
                raise BadParamsError(
                    validation_result.get_error_message(),
                    missing_params=validation_result.missing_params,
                    invalid_params=validation_result.invalid_params,
                )

        # Validate using operation's custom validation (if any)
        try:
            operation.validate_params()
        except Exception as e:
            # Wrap any validation errors as BadParamsError
            if not isinstance(e, BadParamsError):
                raise BadParamsError(str(e)) from e
            raise

        # Run the operation
        try:
            with log_step("operation.run", operation=operation_name):
                result = operation.run()

            log.info(
                "runner.completed",
                status=result.status.value,
                duration_ms=round(result.duration_seconds * 1000, 2) if result.duration_seconds else None,
            )

            return result

        except Exception as e:
            log.error("runner.error", error=str(e), error_type=type(e).__name__)
            return OperationResult(
                status=OperationStatus.FAILED,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                error=str(e),
            )

    def run_all(self, operation_names: list[str], params: dict[str, Any] | None = None) -> list[OperationResult]:
        """
        Run multiple operations in sequence.

        Args:
            operation_names: List of operation names to run in order
            params: Optional shared parameters

        Returns:
            List of OperationResults
        """
        results = []
        for name in operation_names:
            result = self.run(name, params)
            results.append(result)

            # Stop on failure
            if result.status == OperationStatus.FAILED:
                log.warning("runner.stopped", failed_at=name)
                break

        return results


# Default runner instance
_runner: OperationRunner | None = None


def get_runner() -> OperationRunner:
    """Get or create runner instance."""
    global _runner
    if _runner is None:
        _runner = OperationRunner()
    return _runner
