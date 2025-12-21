"""Tests for WorkflowExecutor — bridge from execution to orchestration."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spine.execution.registry import HandlerRegistry
from spine.execution.workflow_executor import (
    execute_workflow,
    register_workflow_executor,
)
from spine.orchestration.workflow import Step, Workflow
from spine.orchestration.workflow_runner import WorkflowResult, WorkflowStatus


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def registry():
    return HandlerRegistry()


@pytest.fixture()
def simple_workflow():
    """A two-step workflow for testing."""
    return Workflow(
        name="test.workflow",
        steps=[
            Step.operation(name="step1", operation_name="pipe_a"),
            Step.operation(name="step2", operation_name="pipe_b"),
        ],
    )


# ── register_workflow_executor ───────────────────────────────────────────


class TestRegisterWorkflowExecutor:
    def test_registers_handler(self, registry):
        register_workflow_executor(registry=registry)
        assert registry.has("workflow", "__all__")

    def test_double_register_no_error(self, registry):
        register_workflow_executor(registry=registry)
        register_workflow_executor(registry=registry)
        assert registry.has("workflow", "__all__")

    def test_uses_default_registry(self):
        """Falls back to get_default_registry() when registry=None."""
        from spine.execution.registry import get_default_registry, reset_default_registry

        reset_default_registry()
        try:
            register_workflow_executor(registry=None)
            assert get_default_registry().has("workflow", "__all__")
        finally:
            reset_default_registry()


# ── execute_workflow (sync convenience) ──────────────────────────────────


class TestExecuteWorkflow:
    def test_execute_completes(self, simple_workflow):
        result = execute_workflow(simple_workflow, dry_run=True)
        assert isinstance(result, WorkflowResult)
        assert result.status == WorkflowStatus.COMPLETED

    def test_execute_with_params(self, simple_workflow):
        result = execute_workflow(
            simple_workflow,
            params={"date": "2025-01-01"},
            dry_run=True,
        )
        assert result.status == WorkflowStatus.COMPLETED

    def test_execute_dry_run_no_side_effects(self, simple_workflow):
        """Dry run should complete without actually running operations."""
        result = execute_workflow(simple_workflow, dry_run=True)
        assert len(result.completed_steps) == 2
        assert len(result.failed_steps) == 0

    def test_execute_with_runnable(self, simple_workflow):
        """When a Runnable is passed, WorkflowRunner uses it for operation steps."""
        mock_runnable = MagicMock()
        # In dry_run mode the runnable is not actually used, but it should be accepted
        result = execute_workflow(
            simple_workflow, dry_run=True, runnable=mock_runnable,
        )
        assert result.status == WorkflowStatus.COMPLETED

    def test_result_has_duration(self, simple_workflow):
        result = execute_workflow(simple_workflow, dry_run=True)
        assert result.duration_seconds >= 0

    def test_result_has_workflow_name(self, simple_workflow):
        result = execute_workflow(simple_workflow, dry_run=True)
        assert result.workflow_name == "test.workflow"
