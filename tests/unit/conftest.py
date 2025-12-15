"""Shared fixtures for unit tests."""
from __future__ import annotations

import pytest
from spine.execution.runnable import PipelineRunResult, Runnable


class _NoOpRunnable:
    """Minimal Runnable that always returns success (for lambda-only tests)."""

    def submit_pipeline_sync(
        self,
        pipeline_name: str,
        params: dict | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineRunResult:
        return PipelineRunResult(status="completed")


@pytest.fixture
def noop_runnable() -> Runnable:
    return _NoOpRunnable()
