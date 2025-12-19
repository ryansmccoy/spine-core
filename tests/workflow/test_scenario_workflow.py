"""
Backend workflow integration tests — scenario-driven.

Tests the orchestration registry, workflow operations, and run lifecycle
directly against the ops layer (no HTTP).  Uses an in-memory SQLite
connection to keep tests fast and deterministic.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from tests._support.scenario_loader import load_scenarios, Scenario

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCENARIOS = load_scenarios()


@pytest.fixture()
def db_conn():
    """Fresh in-memory SQLite with all core tables + scheduler tables."""
    from spine.ops.sqlite_conn import SqliteConnection
    from spine.core.schema import create_core_tables

    conn = SqliteConnection(":memory:")
    create_core_tables(conn)
    # core_schedules is now in CORE_DDL, created by create_core_tables
    yield conn
    conn.close()


@pytest.fixture()
def op_ctx(db_conn):
    """OperationContext wired to the in-memory DB."""
    from spine.ops.context import OperationContext

    return OperationContext(conn=db_conn)


@pytest.fixture(autouse=True)
def _register_example_workflows():
    """Ensure example workflows are in the registry for every test."""
    from spine.orchestration.workflow_registry import clear_workflow_registry

    clear_workflow_registry()
    from spine.api.example_workflows import register_example_workflows

    # Reset the _REGISTERED flag so workflows are re-loaded
    import spine.api.example_workflows as ew
    ew._REGISTERED = False
    register_example_workflows()
    yield
    clear_workflow_registry()


# ---------------------------------------------------------------------------
# Parametrised scenario tests
# ---------------------------------------------------------------------------

def _scenario_ids():
    return [s.id for s in SCENARIOS]


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=_scenario_ids(),
)
class TestWorkflowScenarios:
    """Run every scenario through the ops layer."""

    def test_submit_run(self, scenario: Scenario, op_ctx):
        """Submit a run if the scenario has a submit payload."""
        if not scenario.is_submit:
            pytest.skip("No submit payload")

        from spine.ops.runs import submit_run
        from spine.ops.requests import SubmitRunRequest

        body = scenario.submit
        request = SubmitRunRequest(
            kind=body["kind"],
            name=body["name"],
            params=body.get("params", {}),
            idempotency_key=body.get("idempotency_key"),
        )
        result = submit_run(op_ctx, request)

        expected = scenario.expected
        has_actions = bool(scenario.actions or scenario.pre_actions)
        if expected.get("submit_status") == 202 or has_actions:
            # Submit is the happy path OR a precondition for a later action
            assert result.success, f"Expected success: {result.error}"
            assert result.data is not None
            assert result.data.run_id
        elif expected.get("error_code"):
            assert not result.success
            assert result.error is not None
            assert result.error.code == expected["error_code"]

    def test_trigger_workflow(self, scenario: Scenario, op_ctx):
        """Trigger a workflow if the scenario defines trigger_workflow."""
        if not scenario.is_workflow_trigger:
            pytest.skip("No workflow trigger")

        from spine.ops.workflows import run_workflow
        from spine.ops.requests import RunWorkflowRequest

        tw = scenario.trigger_workflow
        request = RunWorkflowRequest(
            name=tw["name"],
            params=tw.get("params", {}),
            idempotency_key=tw.get("idempotency_key", ""),
        )
        op_ctx.dry_run = tw.get("dry_run", False)
        result = run_workflow(op_ctx, request)

        expected = scenario.expected
        if expected.get("submit_status") == 202:
            assert result.success, f"Expected success: {result.error}"
            if expected.get("dry_run_flag"):
                assert result.data.dry_run is True
        elif expected.get("error_code"):
            assert not result.success
            assert result.error is not None
            assert result.error.code == expected["error_code"]
            if expected.get("error_message_contains"):
                assert expected["error_message_contains"].lower() in result.error.message.lower()

    def test_run_detail_lookup(self, scenario: Scenario, op_ctx):
        """Look up a run by ID (for not-found scenarios)."""
        if not scenario.lookup_run_id:
            pytest.skip("No lookup_run_id")

        from spine.ops.runs import get_run
        from spine.ops.requests import GetRunRequest

        result = get_run(op_ctx, GetRunRequest(run_id=scenario.lookup_run_id))

        expected = scenario.expected
        if expected.get("error_code") == "NOT_FOUND":
            assert not result.success
            assert result.error.code == "NOT_FOUND"

    def test_workflow_listing(self, scenario: Scenario, op_ctx):
        """Validate workflow listing."""
        if scenario.id != "workflow_listing":
            pytest.skip("Not a workflow listing scenario")

        from spine.ops.workflows import list_workflows

        result = list_workflows(op_ctx)
        expected = scenario.expected

        assert result.success
        assert len(result.data) >= expected.get("min_workflow_count", 1)
        for w in result.data:
            for key in expected.get("workflow_has_keys", []):
                assert hasattr(w, key), f"Missing key: {key}"

    def test_workflow_detail(self, scenario: Scenario, op_ctx):
        """Validate workflow detail endpoint logic."""
        if scenario.id != "workflow_detail":
            pytest.skip("Not a workflow detail scenario")

        from spine.ops.workflows import get_workflow
        from spine.ops.requests import GetWorkflowRequest

        result = get_workflow(op_ctx, GetWorkflowRequest(name=scenario.workflow))

        expected = scenario.expected
        assert result.success
        assert len(result.data.steps) == expected.get("steps_count", 0)

    def test_cancel_lifecycle(self, scenario: Scenario, op_ctx):
        """Test cancel scenarios — submit then cancel."""
        if "cancel" not in scenario.actions:
            pytest.skip("No cancel action")

        from spine.ops.runs import submit_run, cancel_run
        from spine.ops.requests import SubmitRunRequest, CancelRunRequest

        if not scenario.submit:
            pytest.skip("No submit payload for cancel test")

        body = scenario.submit
        sub = submit_run(
            op_ctx,
            SubmitRunRequest(kind=body["kind"], name=body["name"], params=body.get("params", {})),
        )
        assert sub.success
        run_id = sub.data.run_id

        # Force-complete if needed
        if "force_complete" in scenario.pre_actions:
            op_ctx.conn.execute(
                "UPDATE core_executions SET status = 'completed' WHERE id = ?",
                (run_id,),
            )
            op_ctx.conn.commit()

        result = cancel_run(op_ctx, CancelRunRequest(run_id=run_id))

        if scenario.expected.get("cancel_succeeds"):
            assert result.success
        elif scenario.expected.get("error_code"):
            assert not result.success
            assert result.error.code == scenario.expected["error_code"]

    def test_schedule_crud(self, scenario: Scenario, op_ctx):
        """Test schedule CRUD lifecycle."""
        if not scenario.is_schedule:
            pytest.skip("Not a schedule scenario")

        from spine.ops.schedules import (
            create_schedule,
            get_schedule,
            update_schedule,
            delete_schedule,
            list_schedules,
        )
        from spine.ops.requests import (
            CreateScheduleRequest,
            GetScheduleRequest,
            UpdateScheduleRequest,
            DeleteScheduleRequest,
        )

        sched = scenario.schedule
        # Create
        cr = create_schedule(
            op_ctx,
            CreateScheduleRequest(
                name=sched.get("name", sched.get("workflow_name", "")),
                target_type=sched.get("target_type", "workflow"),
                target_name=sched.get("target_name", sched.get("workflow_name", "")),
                cron_expression=sched.get("cron_expression", sched.get("cron", "")),
                params=sched.get("params", {}),
            ),
        )
        assert cr.success, f"Create failed: {cr.error}"

        sid = cr.data.schedule_id
        assert sid

        # Get
        gr = get_schedule(op_ctx, GetScheduleRequest(schedule_id=sid))
        assert gr.success

        # Update
        ur = update_schedule(
            op_ctx,
            UpdateScheduleRequest(schedule_id=sid, enabled=False),
        )
        assert ur.success

        # Delete
        dr = delete_schedule(op_ctx, DeleteScheduleRequest(schedule_id=sid))
        assert dr.success

    def test_run_events(self, scenario: Scenario, op_ctx):
        """Validate event timeline after submission."""
        if scenario.id != "run_events_timeline":
            pytest.skip("Not an events scenario")

        from spine.ops.runs import submit_run, get_run_events
        from spine.ops.requests import SubmitRunRequest, GetRunEventsRequest

        body = scenario.submit
        sub = submit_run(
            op_ctx,
            SubmitRunRequest(kind=body["kind"], name=body["name"], params=body.get("params", {})),
        )
        assert sub.success

        events = get_run_events(
            op_ctx,
            GetRunEventsRequest(run_id=sub.data.run_id),
        )
        assert events.success
        expected = scenario.expected
        assert len(events.data) >= expected.get("min_event_count", 1)
        if expected.get("first_event_type"):
            assert events.data[0].event_type == expected["first_event_type"]
