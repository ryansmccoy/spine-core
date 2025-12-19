"""Shared fixtures for orchestration tests."""

import pytest

from spine.execution.runnable import PipelineRunResult


class _NoOpRunnable:
    """Minimal Runnable for tests that only use lambda steps."""

    def submit_pipeline_sync(self, pipeline_name, params=None, *, parent_run_id=None, correlation_id=None):
        return PipelineRunResult(status="completed")


@pytest.fixture
def noop_runnable():
    """A Runnable that always returns success (for lambda-only workflows)."""
    return _NoOpRunnable()
