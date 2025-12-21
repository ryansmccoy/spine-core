"""Shared fixtures for orchestration tests."""

import pytest

from spine.execution.runnable import OperationRunResult


class _NoOpRunnable:
    """Minimal Runnable for tests that only use lambda steps."""

    def submit_operation_sync(self, operation_name, params=None, *, parent_run_id=None, correlation_id=None):
        return OperationRunResult(status="completed")


@pytest.fixture
def noop_runnable():
    """A Runnable that always returns success (for lambda-only workflows)."""
    return _NoOpRunnable()
