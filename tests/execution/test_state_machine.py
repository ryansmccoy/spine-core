"""
Tests for state machine transition validation.

Tests cover:
- ExecutionStatus valid/invalid transitions
- RunStatus valid/invalid transitions
- InvalidTransitionError details
- RunRecord.mark_*() methods enforce transitions
- Terminal states have no outgoing transitions
- Retry paths (FAILED → PENDING, DEAD_LETTERED → PENDING)
"""

import pytest
from datetime import datetime

from spine.execution.models import (
    ExecutionStatus,
    InvalidTransitionError,
    EXECUTION_VALID_TRANSITIONS,
    validate_execution_transition,
)
from spine.execution.runs import (
    RunRecord,
    RunStatus,
    RUN_VALID_TRANSITIONS,
    validate_run_transition,
)
from spine.execution.spec import task_spec


# =============================================================================
# Helpers
# =============================================================================


def _make_run(status: RunStatus = RunStatus.PENDING) -> RunRecord:
    """Create a RunRecord in the given status."""
    run = RunRecord(
        run_id="test-run-001",
        spec=task_spec("test_task", params={"key": "value"}),
        status=status,
        created_at=datetime.utcnow(),
    )
    return run


# =============================================================================
# ExecutionStatus Transitions
# =============================================================================


class TestExecutionStatusTransitions:
    """Tests for ExecutionStatus transition validation."""

    def test_pending_to_queued(self):
        """PENDING → QUEUED is valid."""
        validate_execution_transition(ExecutionStatus.PENDING, ExecutionStatus.QUEUED)

    def test_pending_to_running(self):
        """PENDING → RUNNING is valid (skip queue)."""
        validate_execution_transition(ExecutionStatus.PENDING, ExecutionStatus.RUNNING)

    def test_pending_to_cancelled(self):
        """PENDING → CANCELLED is valid."""
        validate_execution_transition(ExecutionStatus.PENDING, ExecutionStatus.CANCELLED)

    def test_queued_to_running(self):
        """QUEUED → RUNNING is valid."""
        validate_execution_transition(ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)

    def test_running_to_completed(self):
        """RUNNING → COMPLETED is valid."""
        validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED)

    def test_running_to_failed(self):
        """RUNNING → FAILED is valid."""
        validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.FAILED)

    def test_running_to_timed_out(self):
        """RUNNING → TIMED_OUT is valid."""
        validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.TIMED_OUT)

    def test_failed_to_pending_retry(self):
        """FAILED → PENDING is valid (retry)."""
        validate_execution_transition(ExecutionStatus.FAILED, ExecutionStatus.PENDING)

    def test_timed_out_to_pending_retry(self):
        """TIMED_OUT → PENDING is valid (retry)."""
        validate_execution_transition(ExecutionStatus.TIMED_OUT, ExecutionStatus.PENDING)

    def test_completed_is_terminal(self):
        """COMPLETED has no outgoing transitions."""
        for target in ExecutionStatus:
            if target == ExecutionStatus.COMPLETED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_execution_transition(ExecutionStatus.COMPLETED, target)

    def test_cancelled_is_terminal(self):
        """CANCELLED has no outgoing transitions."""
        for target in ExecutionStatus:
            if target == ExecutionStatus.CANCELLED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_execution_transition(ExecutionStatus.CANCELLED, target)

    def test_completed_to_running_blocked(self):
        """COMPLETED → RUNNING is invalid and must raise."""
        with pytest.raises(InvalidTransitionError, match="completed → running"):
            validate_execution_transition(ExecutionStatus.COMPLETED, ExecutionStatus.RUNNING)

    def test_completed_to_pending_blocked(self):
        """COMPLETED → PENDING is invalid (no retry from success)."""
        with pytest.raises(InvalidTransitionError):
            validate_execution_transition(ExecutionStatus.COMPLETED, ExecutionStatus.PENDING)

    def test_running_to_queued_blocked(self):
        """RUNNING → QUEUED is invalid (can't go backward)."""
        with pytest.raises(InvalidTransitionError):
            validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.QUEUED)

    def test_self_transition_blocked(self):
        """A status cannot transition to itself."""
        for status in ExecutionStatus:
            with pytest.raises(InvalidTransitionError):
                validate_execution_transition(status, status)

    def test_all_statuses_have_transition_rules(self):
        """Every ExecutionStatus value must appear in VALID_TRANSITIONS."""
        for status in ExecutionStatus:
            assert status in EXECUTION_VALID_TRANSITIONS, f"Missing {status}"

    def test_error_contains_details(self):
        """InvalidTransitionError includes current and target."""
        try:
            validate_execution_transition(ExecutionStatus.COMPLETED, ExecutionStatus.RUNNING)
        except InvalidTransitionError as e:
            assert e.current == "completed"
            assert e.target == "running"
            assert "ExecutionStatus" in str(e)


# =============================================================================
# RunStatus Transitions
# =============================================================================


class TestRunStatusTransitions:
    """Tests for RunStatus transition validation."""

    def test_pending_to_queued(self):
        validate_run_transition(RunStatus.PENDING, RunStatus.QUEUED)

    def test_pending_to_running(self):
        validate_run_transition(RunStatus.PENDING, RunStatus.RUNNING)

    def test_running_to_completed(self):
        validate_run_transition(RunStatus.RUNNING, RunStatus.COMPLETED)

    def test_running_to_failed(self):
        validate_run_transition(RunStatus.RUNNING, RunStatus.FAILED)

    def test_failed_to_dead_lettered(self):
        validate_run_transition(RunStatus.FAILED, RunStatus.DEAD_LETTERED)

    def test_failed_to_pending_retry(self):
        validate_run_transition(RunStatus.FAILED, RunStatus.PENDING)

    def test_dead_lettered_to_pending_retry(self):
        validate_run_transition(RunStatus.DEAD_LETTERED, RunStatus.PENDING)

    def test_completed_is_terminal(self):
        for target in RunStatus:
            if target == RunStatus.COMPLETED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_run_transition(RunStatus.COMPLETED, target)

    def test_cancelled_is_terminal(self):
        for target in RunStatus:
            if target == RunStatus.CANCELLED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_run_transition(RunStatus.CANCELLED, target)

    def test_completed_to_running_blocked(self):
        with pytest.raises(InvalidTransitionError, match="completed → running"):
            validate_run_transition(RunStatus.COMPLETED, RunStatus.RUNNING)

    def test_all_statuses_have_transition_rules(self):
        for status in RunStatus:
            assert status in RUN_VALID_TRANSITIONS, f"Missing {status}"


# =============================================================================
# RunRecord mark_*() enforcement
# =============================================================================


class TestRunRecordTransitionEnforcement:
    """Tests that RunRecord.mark_*() enforce transition rules."""

    def test_mark_started_from_pending(self):
        """PENDING → RUNNING via mark_started()."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        assert run.status == RunStatus.RUNNING
        assert run.started_at is not None

    def test_mark_started_from_completed_raises(self):
        """COMPLETED → RUNNING via mark_started() must raise."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        run.mark_completed()
        with pytest.raises(InvalidTransitionError):
            run.mark_started()

    def test_mark_completed_from_running(self):
        """RUNNING → COMPLETED via mark_completed()."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        run.mark_completed(result={"ok": True})
        assert run.status == RunStatus.COMPLETED
        assert run.result == {"ok": True}
        assert run.duration_seconds is not None

    def test_mark_completed_from_pending_raises(self):
        """PENDING → COMPLETED via mark_completed() is invalid."""
        run = _make_run(RunStatus.PENDING)
        with pytest.raises(InvalidTransitionError):
            run.mark_completed()

    def test_mark_failed_from_running(self):
        """RUNNING → FAILED via mark_failed()."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        run.mark_failed("timeout", "TimeoutError")
        assert run.status == RunStatus.FAILED
        assert run.error == "timeout"
        assert run.error_type == "TimeoutError"

    def test_mark_failed_from_pending_raises(self):
        """PENDING → FAILED via mark_failed() is invalid."""
        run = _make_run(RunStatus.PENDING)
        with pytest.raises(InvalidTransitionError):
            run.mark_failed("oops")

    def test_mark_cancelled_from_pending(self):
        """PENDING → CANCELLED via mark_cancelled()."""
        run = _make_run(RunStatus.PENDING)
        run.mark_cancelled()
        assert run.status == RunStatus.CANCELLED

    def test_mark_cancelled_from_running(self):
        """RUNNING → CANCELLED via mark_cancelled()."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        run.mark_cancelled()
        assert run.status == RunStatus.CANCELLED

    def test_mark_cancelled_from_completed_raises(self):
        """COMPLETED → CANCELLED is invalid."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        run.mark_completed()
        with pytest.raises(InvalidTransitionError):
            run.mark_cancelled()

    def test_double_complete_raises(self):
        """Completing twice must raise."""
        run = _make_run(RunStatus.PENDING)
        run.mark_started()
        run.mark_completed()
        with pytest.raises(InvalidTransitionError):
            run.mark_completed()

    def test_full_lifecycle(self):
        """Happy path: PENDING → RUNNING → COMPLETED."""
        run = _make_run()
        assert run.status == RunStatus.PENDING
        run.mark_started()
        assert run.status == RunStatus.RUNNING
        run.mark_completed({"rows": 42})
        assert run.status == RunStatus.COMPLETED
        assert run.result == {"rows": 42}

    def test_failure_lifecycle(self):
        """Failure path: PENDING → RUNNING → FAILED."""
        run = _make_run()
        run.mark_started()
        run.mark_failed("connection refused", "ConnectionError")
        assert run.status == RunStatus.FAILED
        assert run.error == "connection refused"
