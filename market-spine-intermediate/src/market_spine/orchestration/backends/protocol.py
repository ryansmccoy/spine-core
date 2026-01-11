"""OrchestratorBackend protocol definition."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class OrchestratorBackend(Protocol):
    """
    Protocol for orchestration backends.

    Backends are responsible for:
    - Submitting executions for processing
    - Cancelling running executions
    - Reporting health status

    The backend translates between Market Spine's execution model
    and the underlying execution engine (local threads, Celery, Prefect, etc.)
    """

    name: str

    def submit(self, execution_id: str) -> str | None:
        """
        Submit an execution for processing.

        Args:
            execution_id: The execution ID to process

        Returns:
            Backend-specific run ID (e.g., Celery task ID), or None for local
        """
        ...

    def cancel(self, execution_id: str) -> bool:
        """
        Request cancellation of an execution.

        Best-effort cancellation:
        - If pending: mark as cancelled immediately
        - If running: request cancellation, may not take effect immediately

        Args:
            execution_id: The execution ID to cancel

        Returns:
            True if cancellation was requested successfully
        """
        ...

    def health(self) -> dict:
        """
        Check backend health.

        Returns:
            Health status dict with at least {"healthy": bool, "message": str}
        """
        ...

    def start(self) -> None:
        """Start the backend (e.g., begin polling for work)."""
        ...

    def stop(self) -> None:
        """Stop the backend gracefully."""
        ...
