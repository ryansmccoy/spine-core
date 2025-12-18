"""
Tests for the Celery task definitions module.

These tests validate the module loads cleanly regardless of whether
Celery is installed, and that the task stubs/definitions exist.
"""

from __future__ import annotations

import pytest


class TestCeleryTasksModule:
    def test_import_succeeds(self):
        """Module should import without error even without Celery."""
        from spine.execution import tasks
        assert hasattr(tasks, "execute_task")
        assert hasattr(tasks, "execute_pipeline")
        assert hasattr(tasks, "execute_workflow")
        assert hasattr(tasks, "execute_step")

    def test_celery_available_flag(self):
        """CELERY_AVAILABLE should be a bool."""
        from spine.execution.tasks import CELERY_AVAILABLE
        assert isinstance(CELERY_AVAILABLE, bool)

    def test_stubs_raise_without_celery(self):
        """If Celery is not installed, stub functions should raise RuntimeError."""
        from spine.execution.tasks import CELERY_AVAILABLE
        if not CELERY_AVAILABLE:
            from spine.execution.tasks import execute_task
            with pytest.raises(RuntimeError, match="Celery is not installed"):
                execute_task("test", {})
