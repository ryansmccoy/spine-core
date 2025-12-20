"""Tests for spine.ops.workflows — workflow operations."""

import pytest

from spine.ops.workflows import get_workflow, list_workflows, run_workflow
from spine.ops.requests import GetWorkflowRequest, RunWorkflowRequest
from spine.orchestration import (
    Workflow,
    Step,
    register_workflow,
    clear_workflow_registry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear the workflow registry before/after each test."""
    clear_workflow_registry()
    yield
    clear_workflow_registry()


@pytest.fixture()
def sample_workflow():
    """Register a sample workflow for testing."""
    workflow = Workflow(
        name="test.workflow",
        domain="test",
        steps=[
            Step.pipeline("step1", "test.pipe1"),
            Step.pipeline("step2", "test.pipe2"),
        ],
    )
    register_workflow(workflow)
    return workflow


class TestListWorkflows:
    def test_empty_registry(self, ctx):
        result = list_workflows(ctx)
        assert result.success is True
        assert result.data == []

    def test_with_registered_workflows(self, ctx, sample_workflow):
        result = list_workflows(ctx)
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].name == "test.workflow"
        assert result.data[0].step_count == 2


class TestGetWorkflow:
    def test_not_found(self, ctx):
        result = get_workflow(ctx, GetWorkflowRequest(name="nonexistent"))
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx, sample_workflow):
        result = get_workflow(ctx, GetWorkflowRequest(name="test.workflow"))
        assert result.success is True
        assert result.data.name == "test.workflow"
        assert len(result.data.steps) == 2

    def test_validation_empty_name(self, ctx):
        result = get_workflow(ctx, GetWorkflowRequest(name=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"


class TestRunWorkflow:
    def test_not_found(self, ctx):
        result = run_workflow(ctx, RunWorkflowRequest(name="missing"))
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_submit(self, ctx, sample_workflow):
        result = run_workflow(ctx, RunWorkflowRequest(name="test.workflow"))
        assert result.success is True
        assert result.data.run_id is not None
        assert result.data.would_execute is True

    def test_dry_run(self, dry_ctx, sample_workflow):
        result = run_workflow(dry_ctx, RunWorkflowRequest(name="test.workflow"))
        assert result.success is True
        assert result.data.dry_run is True
        assert result.data.run_id is None

    def test_validation_empty_name(self, ctx):
        result = run_workflow(ctx, RunWorkflowRequest(name=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"
