"""Shared fixtures for unit tests."""
from __future__ import annotations

import pytest
from spine.execution.runnable import OperationRunResult, Runnable


class _NoOpRunnable:
    """Minimal Runnable that always returns success (for lambda-only tests)."""

    def submit_operation_sync(
        self,
        operation_name: str,
        params: dict | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> OperationRunResult:
        return OperationRunResult(status="completed")


@pytest.fixture
def noop_runnable() -> Runnable:
    return _NoOpRunnable()
