"""Tests for ``spine.ops.workflows`` — workflow operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.workflows import (
    get_workflow,
    list_workflow_events,
    list_workflows,
    run_workflow,
)
from spine.ops.requests import (
    GetWorkflowRequest,
    ListWorkflowEventsRequest,
    RunWorkflowRequest,
)


@pytest.fixture()
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


@pytest.fixture()
def dry_ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test", dry_run=True)


class TestListWorkflows:
    @patch("spine.ops.workflows._list_workflows", create=True)
    @patch("spine.ops.workflows._get_workflow", create=True)
    def test_success(self, mock_get, mock_list, ctx):
        with patch("spine.orchestration.workflow_registry.list_workflows", return_value=["wf-1"]), \
             patch("spine.orchestration.workflow_registry.get_workflow") as mock_get_wf:
            wf = MagicMock()
            wf.name = "wf-1"
            wf.steps = [MagicMock(), MagicMock()]
            wf.description = "Test"
            mock_get_wf.return_value = wf

            result = list_workflows(ctx)
            assert result.success is True
            assert len(result.data) >= 1

    @patch("spine.orchestration.workflow_registry.list_workflows", side_effect=RuntimeError("boom"))
    def test_error(self, mock_list, ctx):
        result = list_workflows(ctx)
        assert result.success is False


class TestGetWorkflow:
    def test_missing_name_fails(self, ctx):
        req = GetWorkflowRequest(name="")
        result = get_workflow(ctx, req)
        assert result.success is False
        assert "required" in result.error.message.lower()

    @patch("spine.orchestration.workflow_registry.get_workflow")
    @patch("spine.orchestration.workflow_registry.WorkflowNotFoundError", RuntimeError)
    def test_not_found(self, mock_get, ctx):
        mock_get.side_effect = RuntimeError("not found")
        req = GetWorkflowRequest(name="missing")
        result = get_workflow(ctx, req)
        assert result.success is False

    @patch("spine.orchestration.workflow_registry.get_workflow")
    def test_success(self, mock_get, ctx):
        wf = MagicMock()
        wf.name = "my-wf"
        wf.steps = []
        wf.description = "test wf"
        wf.execution_policy = None
        wf.domain = "test"
        wf.version = 1
        wf.tags = ["tag1"]
        wf.defaults = {}
        mock_get.return_value = wf

        req = GetWorkflowRequest(name="my-wf")
        result = get_workflow(ctx, req)
        assert result.success is True
        assert result.data.name == "my-wf"


class TestRunWorkflow:
    def test_missing_name(self, ctx):
        req = RunWorkflowRequest(name="")
        result = run_workflow(ctx, req)
        assert result.success is False

    @patch("spine.orchestration.workflow_registry.workflow_exists", return_value=False)
    def test_not_found(self, mock_exists, ctx):
        req = RunWorkflowRequest(name="missing")
        result = run_workflow(ctx, req)
        assert result.success is False
        assert "not found" in result.error.message.lower()

    @patch("spine.orchestration.workflow_registry.workflow_exists", return_value=True)
    def test_dry_run(self, mock_exists, dry_ctx):
        req = RunWorkflowRequest(name="my-wf")
        result = run_workflow(dry_ctx, req)
        assert result.success is True
        assert result.data.dry_run is True

    @patch("spine.orchestration.workflow_registry.workflow_exists", return_value=True)
    def test_submit(self, mock_exists, ctx):
        req = RunWorkflowRequest(name="my-wf", params={"key": "val"})
        result = run_workflow(ctx, req)
        assert result.success is True
        assert result.data.run_id is not None

    @patch("spine.orchestration.workflow_registry.workflow_exists", side_effect=RuntimeError("error"))
    def test_registry_error(self, mock_exists, ctx):
        req = RunWorkflowRequest(name="test")
        result = run_workflow(ctx, req)
        assert result.success is False


class TestListWorkflowEvents:
    def test_missing_run_id(self, ctx):
        req = ListWorkflowEventsRequest(run_id="")
        result = list_workflow_events(ctx, req)
        assert result.success is False

    @patch("spine.ops.workflows._wf_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_events.return_value = (
            [
                {
                    "id": 1,
                    "run_id": "run-1",
                    "step_id": "s1",
                    "event_type": "started",
                    "timestamp": "2026-01-01T00:00:00",
                    "payload": '{"key": "val"}',
                }
            ],
            1,
        )
        mock_repo_fn.return_value = repo

        req = ListWorkflowEventsRequest(run_id="run-1")
        result = list_workflow_events(ctx, req)
        assert result.success is True
        assert result.data[0].event_type == "started"
        assert result.data[0].payload == {"key": "val"}

    @patch("spine.ops.workflows._wf_repo")
    def test_invalid_json_payload(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_events.return_value = (
            [
                {
                    "id": 1,
                    "run_id": "run-1",
                    "step_id": None,
                    "event_type": "error",
                    "timestamp": None,
                    "payload": "not-json{",
                }
            ],
            1,
        )
        mock_repo_fn.return_value = repo

        req = ListWorkflowEventsRequest(run_id="run-1")
        result = list_workflow_events(ctx, req)
        assert result.success is True
        assert result.data[0].payload == {}

    @patch("spine.ops.workflows._wf_repo")
    def test_error(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_events.side_effect = RuntimeError("db err")
        mock_repo_fn.return_value = repo

        req = ListWorkflowEventsRequest(run_id="run-1")
        result = list_workflow_events(ctx, req)
        assert result.success is False
