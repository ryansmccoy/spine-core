"""Tests for execution tasks — Celery stubs and resolve handler.

Tests the non-Celery paths and handler resolution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.execution.tasks import CELERY_AVAILABLE


class TestCeleryAvailability:
    def test_celery_available_is_bool(self):
        assert isinstance(CELERY_AVAILABLE, bool)


class TestStubs:
    """When Celery is not available, stub functions raise RuntimeError."""

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery is installed")
    def test_execute_task_stub(self):
        from spine.execution.tasks import execute_task
        with pytest.raises(RuntimeError, match="[Cc]elery"):
            execute_task("workflow", "test", {})

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery is installed")
    def test_execute_operation_stub(self):
        from spine.execution.tasks import execute_operation
        with pytest.raises(RuntimeError, match="[Cc]elery"):
            execute_operation("test-op", {})

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery is installed")
    def test_execute_workflow_stub(self):
        from spine.execution.tasks import execute_workflow
        with pytest.raises(RuntimeError, match="[Cc]elery"):
            execute_workflow("test-wf", {})

    @pytest.mark.skipif(CELERY_AVAILABLE, reason="Celery is installed")
    def test_execute_step_stub(self):
        from spine.execution.tasks import execute_step
        with pytest.raises(RuntimeError, match="[Cc]elery"):
            execute_step("test-step", {}, "run-1")


class TestResolveHandler:
    def test_resolve_found(self):
        from spine.execution.tasks import _resolve_handler
        mock_registry = MagicMock()
        mock_handler = MagicMock()
        mock_registry.get.return_value = mock_handler
        with patch("spine.execution.registry.get_default_registry", return_value=mock_registry):
            result = _resolve_handler("workflow", "test-wf")
        assert result is mock_handler

    def test_resolve_not_found(self):
        from spine.execution.tasks import _resolve_handler
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        with patch("spine.execution.registry.get_default_registry", return_value=mock_registry):
            result = _resolve_handler("workflow", "missing")
        assert result is None
