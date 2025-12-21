"""Tests for ``spine.execution.tasks`` — Celery task stubs when Celery is not installed."""

from __future__ import annotations

import pytest

from spine.execution.tasks import (
    CELERY_AVAILABLE,
    execute_operation,
    execute_step,
    execute_task,
    execute_workflow,
)


class TestCeleryStubs:
    """When Celery is not installed, the task stubs must raise RuntimeError."""

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery IS installed")
    def test_execute_task_raises(self):
        with pytest.raises(RuntimeError, match="Celery is not installed"):
            execute_task("my_task", {})

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery IS installed")
    def test_execute_operation_raises(self):
        with pytest.raises(RuntimeError, match="Celery is not installed"):
            execute_operation("my_pipe", {})

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery IS installed")
    def test_execute_workflow_raises(self):
        with pytest.raises(RuntimeError, match="Celery is not installed"):
            execute_workflow("my_wf", {})

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery IS installed")
    def test_execute_step_raises(self):
        with pytest.raises(RuntimeError, match="Celery is not installed"):
            execute_step("my_step", {})

    def test_celery_available_flag(self):
        """CELERY_AVAILABLE should be a bool."""
        assert isinstance(CELERY_AVAILABLE, bool)
