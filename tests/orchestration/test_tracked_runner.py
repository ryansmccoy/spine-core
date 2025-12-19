"""Tests for TrackedWorkflowRunner and query helpers.

Covers:
- _make_stages() helper
- TrackedWorkflowRunner.execute() with partition tracking
- Idempotency skip when already completed
- execute() without partition (falls back to base runner)
- get_workflow_state() query
- list_workflow_failures() query
"""

import sqlite3
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spine.core.schema import create_core_tables
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step
from spine.orchestration.tracked_runner import (
    TrackedWorkflowRunner,
    _make_stages,
    get_workflow_state,
    list_workflow_failures,
)
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_runner import WorkflowStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory SQLite with core tables."""
    c = sqlite3.connect(":memory:")
    create_core_tables(c)
    return c


def _dummy_fn(ctx, config=None):
    """A simple lambda step that always succeeds."""
    return StepResult.ok(output={"status": "ok"})


def _fail_fn(ctx, config=None):
    """A lambda step that always fails."""
    return StepResult.fail("step exploded")


def _simple_workflow(name: str = "test.wf", steps=None) -> Workflow:
    return Workflow(
        name=name,
        domain="test",
        steps=steps or [Step.lambda_("validate", _dummy_fn)],
    )


# ---------------------------------------------------------------------------
# Tests: _make_stages
# ---------------------------------------------------------------------------


class TestMakeStages:
    def test_basic(self):
        wf = _simple_workflow(steps=[
            Step.lambda_("step_a", _dummy_fn),
            Step.lambda_("step_b", _dummy_fn),
        ])
        stages = _make_stages(wf)
        assert stages == ["STARTED", "STEP_STEP_A", "STEP_STEP_B", "COMPLETED"]


# ---------------------------------------------------------------------------
# Tests: execute
# ---------------------------------------------------------------------------


class TestTrackedWorkflowRunner:
    def test_execute_success(self, conn, noop_runnable):
        wf = _simple_workflow(steps=[Step.lambda_("check", _dummy_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable)
        result = runner.execute(wf, params={}, partition={"key": "1"})
        assert result.status == WorkflowStatus.COMPLETED
        assert result.error is None

    def test_execute_records_manifest(self, conn, noop_runnable):
        wf = _simple_workflow(steps=[Step.lambda_("check", _dummy_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable)
        runner.execute(wf, params={}, partition={"key": "1"})

        # Verify manifest rows were written
        cursor = conn.execute(
            "SELECT stage FROM core_manifest WHERE domain = ?",
            (f"workflow.{wf.name}",),
        )
        stages = [r[0] for r in cursor.fetchall()]
        assert "STARTED" in stages
        assert "COMPLETED" in stages

    def test_idempotency_skip(self, conn, noop_runnable):
        wf = _simple_workflow(steps=[Step.lambda_("check", _dummy_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable, skip_if_completed=True)
        # Run once
        r1 = runner.execute(wf, params={}, partition={"key": "1"})
        assert r1.status == WorkflowStatus.COMPLETED

        # Run again with same partition
        r2 = runner.execute(wf, params={}, partition={"key": "1"})
        assert r2.status == WorkflowStatus.COMPLETED
        assert "Skipped" in (r2.error or "")

    def test_execute_without_partition_delegates(self, conn, noop_runnable):
        """execute() without partition falls back to base WorkflowRunner."""
        wf = _simple_workflow(steps=[Step.lambda_("check", _dummy_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable)
        result = runner.execute(wf, params={})
        # Still runs — just no manifest tracking
        assert result.status == WorkflowStatus.COMPLETED

    def test_execute_step_failure(self, conn, noop_runnable):
        wf = _simple_workflow(steps=[Step.lambda_("explode", _fail_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable)
        result = runner.execute(wf, params={}, partition={"key": "bad"})
        assert result.status == WorkflowStatus.FAILED
        assert result.error_step == "explode"


# ---------------------------------------------------------------------------
# Tests: query helpers
# ---------------------------------------------------------------------------


class TestGetWorkflowState:
    def test_returns_state(self, conn, noop_runnable):
        wf = _simple_workflow(steps=[Step.lambda_("check", _dummy_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable)
        runner.execute(wf, params={}, partition={"k": "1"})

        state = get_workflow_state(conn, wf.name, {"k": "1"})
        assert state["is_completed"] is True
        assert state["latest_stage"] == "COMPLETED"
        assert len(state["stages"]) >= 2

    def test_no_state(self, conn):
        state = get_workflow_state(conn, "nonexistent", {"k": "x"})
        assert state["is_completed"] is False
        assert state["latest_stage"] is None


class TestListWorkflowFailures:
    def test_empty(self, conn):
        failures = list_workflow_failures(conn)
        assert failures == []

    def test_returns_failures(self, conn, noop_runnable):
        wf = _simple_workflow(steps=[Step.lambda_("explode", _fail_fn)])
        runner = TrackedWorkflowRunner(conn, runnable=noop_runnable)
        runner.execute(wf, params={}, partition={"k": "1"})

        failures = list_workflow_failures(conn)
        assert len(failures) >= 1
        assert failures[0]["category"] == "WORKFLOW_FAILURE"
