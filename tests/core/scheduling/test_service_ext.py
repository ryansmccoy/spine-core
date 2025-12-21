"""Tests for SchedulerService orchestration logic.

Covers _tick, _process_schedule, _dispatch, _within_grace_period,
_reschedule, trigger, pause, resume, health, and lifecycle methods.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spine.core.scheduling.service import (
    SchedulerHealth,
    SchedulerService,
    SchedulerStats,
)


def _run(coro):
    """Run async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def svc():
    """Create a SchedulerService with all mock dependencies."""
    backend = MagicMock()
    backend.name = "mock"
    backend.health.return_value = {"healthy": True}

    repo = MagicMock()
    repo.count_enabled.return_value = 3

    lock_mgr = MagicMock()
    lock_mgr.list_active_locks.return_value = []

    dispatcher = AsyncMock()
    dispatcher.submit_workflow = AsyncMock(return_value="run-123")
    dispatcher.submit_operation = AsyncMock(return_value="run-456")

    service = SchedulerService(
        backend=backend,
        repository=repo,
        lock_manager=lock_mgr,
        dispatcher=dispatcher,
        interval_seconds=10.0,
    )
    return service


@pytest.fixture()
def mock_schedule():
    """Create a mock schedule object."""
    s = MagicMock()
    s.id = 1
    s.name = "test-schedule"
    s.target_type = "workflow"
    s.target_name = "etl_pipeline"
    s.params = json.dumps({"key": "val"})
    s.next_run_at = datetime.now(UTC).isoformat()
    s.misfire_grace_seconds = 60
    return s


# ── Lifecycle ────────────────────────────────────────────────


class TestLifecycle:
    def test_start(self, svc):
        svc.start()
        assert svc.is_running is True
        svc.backend.start.assert_called_once()

    def test_start_already_running(self, svc):
        svc.start()
        svc.start()  # Should warn, not fail
        assert svc.backend.start.call_count == 1

    def test_stop(self, svc):
        svc.start()
        svc.stop()
        assert svc.is_running is False
        svc.backend.stop.assert_called_once()

    def test_stop_when_not_running(self, svc):
        svc.stop()  # Should be a no-op
        svc.backend.stop.assert_not_called()


# ── _tick ────────────────────────────────────────────────────


class TestTick:
    def test_tick_no_due_schedules(self, svc):
        svc.repository.get_due_schedules.return_value = []
        _run(svc._tick())
        assert svc._stats.tick_count == 1
        assert svc._stats.last_tick is not None

    def test_tick_processes_due_schedule(self, svc, mock_schedule):
        svc.repository.get_due_schedules.return_value = [mock_schedule]
        svc.lock_manager.acquire_schedule_lock.return_value = True
        _run(svc._tick())
        assert svc._stats.tick_count == 1
        assert svc._stats.schedules_processed == 1

    def test_tick_lock_cleanup_every_6th(self, svc):
        svc.repository.get_due_schedules.return_value = []
        # Run 6 ticks to trigger cleanup
        for _ in range(6):
            _run(svc._tick())
        svc.lock_manager.cleanup_expired_locks.assert_called_once()

    def test_tick_exception_recorded(self, svc):
        svc.repository.get_due_schedules.side_effect = RuntimeError("db fail")
        _run(svc._tick())
        assert svc._stats.last_error == "db fail"


# ── _process_schedule ────────────────────────────────────────


class TestProcessSchedule:
    def test_lock_denied_skips(self, svc, mock_schedule):
        svc.lock_manager.acquire_schedule_lock.return_value = False
        _run(svc._process_schedule(mock_schedule))
        assert svc._stats.schedules_skipped == 1

    def test_grace_missed_skips(self, svc, mock_schedule):
        svc.lock_manager.acquire_schedule_lock.return_value = True
        # Set next_run_at far in the past — beyond grace
        mock_schedule.next_run_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        mock_schedule.misfire_grace_seconds = 10  # 10 seconds grace
        _run(svc._process_schedule(mock_schedule))
        assert svc._stats.schedules_skipped == 1
        svc.repository.mark_run_completed.assert_called_with(mock_schedule.id, "MISSED")

    def test_dispatch_failure(self, svc, mock_schedule):
        svc.lock_manager.acquire_schedule_lock.return_value = True
        svc.dispatcher.submit_workflow.side_effect = RuntimeError("dispatch fail")
        _run(svc._process_schedule(mock_schedule))
        assert svc._stats.schedules_failed == 1
        svc.lock_manager.release_schedule_lock.assert_called_once()

    def test_lock_released_on_success(self, svc, mock_schedule):
        svc.lock_manager.acquire_schedule_lock.return_value = True
        _run(svc._process_schedule(mock_schedule))
        svc.lock_manager.release_schedule_lock.assert_called_with(mock_schedule.id)


# ── _dispatch ────────────────────────────────────────────────


class TestDispatch:
    def test_workflow_dispatch(self, svc, mock_schedule):
        mock_schedule.target_type = "workflow"
        run_id = _run(svc._dispatch(mock_schedule))
        assert run_id == "run-123"
        svc.dispatcher.submit_workflow.assert_called_once()
        svc.repository.mark_run_started.assert_called_with(mock_schedule.id, "run-123")

    def test_operation_dispatch(self, svc, mock_schedule):
        mock_schedule.target_type = "operation"
        run_id = _run(svc._dispatch(mock_schedule))
        assert run_id == "run-456"
        svc.dispatcher.submit_operation.assert_called_once()

    def test_unknown_target_type_raises(self, svc, mock_schedule):
        mock_schedule.target_type = "unknown"
        with pytest.raises(ValueError, match="Unknown target_type"):
            _run(svc._dispatch(mock_schedule))

    def test_no_dispatcher_test_mode(self, svc, mock_schedule):
        svc.dispatcher = None
        run_id = _run(svc._dispatch(mock_schedule))
        assert run_id == "test-run-id"
        svc.repository.mark_run_started.assert_called_with(mock_schedule.id, "test-run-id")

    def test_null_params(self, svc, mock_schedule):
        mock_schedule.params = None
        _run(svc._dispatch(mock_schedule))
        args = svc.dispatcher.submit_workflow.call_args
        assert args[0][1]["trigger_source"] == "schedule"


# ── _within_grace_period ─────────────────────────────────────


class TestWithinGracePeriod:
    def test_no_next_run_always_ok(self, svc, mock_schedule):
        mock_schedule.next_run_at = None
        assert svc._within_grace_period(mock_schedule) is True

    def test_within_grace(self, svc, mock_schedule):
        mock_schedule.next_run_at = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
        mock_schedule.misfire_grace_seconds = 60
        assert svc._within_grace_period(mock_schedule) is True

    def test_outside_grace(self, svc, mock_schedule):
        mock_schedule.next_run_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        mock_schedule.misfire_grace_seconds = 10
        assert svc._within_grace_period(mock_schedule) is False

    def test_naive_datetime_handling(self, svc, mock_schedule):
        """Naive ISO timestamp should be treated as UTC."""
        mock_schedule.next_run_at = datetime.now(UTC).replace(tzinfo=None).isoformat()
        mock_schedule.misfire_grace_seconds = 60
        assert svc._within_grace_period(mock_schedule) is True


# ── trigger / pause / resume ─────────────────────────────────


class TestManualOperations:
    def test_trigger_dispatches(self, svc, mock_schedule):
        svc.repository.get_by_name.return_value = mock_schedule
        run_id = _run(svc.trigger("test-schedule"))
        assert run_id == "run-123"

    def test_trigger_not_found(self, svc):
        svc.repository.get_by_name.return_value = None
        with pytest.raises(KeyError, match="Schedule not found"):
            _run(svc.trigger("missing"))

    def test_trigger_with_override_params(self, svc):
        from spine.core.models.scheduler import Schedule
        real_schedule = Schedule(
            id="s1", name="test-schedule",
            target_type="workflow", target_name="etl_pipeline",
            params='{"key": "val"}',
        )
        svc.repository.get_by_name.return_value = real_schedule
        run_id = _run(svc.trigger("test-schedule", params={"override": True}))
        assert run_id == "run-123"
        # Check merged params were passed
        call_args = svc.dispatcher.submit_workflow.call_args
        assert call_args[0][1]["override"] is True
        assert call_args[0][1]["key"] == "val"  # Original param preserved

    def test_pause(self, svc, mock_schedule):
        svc.repository.get_by_name.return_value = mock_schedule
        assert svc.pause("test-schedule") is True
        svc.repository.update.assert_called_once()

    def test_pause_not_found(self, svc):
        svc.repository.get_by_name.return_value = None
        assert svc.pause("missing") is False

    def test_resume(self, svc, mock_schedule):
        svc.repository.get_by_name.return_value = mock_schedule
        assert svc.resume("test-schedule") is True
        svc.repository.update.assert_called_once()

    def test_resume_not_found(self, svc):
        svc.repository.get_by_name.return_value = None
        assert svc.resume("missing") is False


# ── health / stats ───────────────────────────────────────────


class TestHealthAndStats:
    def test_health_when_running(self, svc):
        svc.start()
        h = svc.health()
        assert isinstance(h, SchedulerHealth)
        assert h.healthy is True
        assert h.schedules_enabled == 3

    def test_health_when_stopped(self, svc):
        h = svc.health()
        assert h.healthy is False

    def test_health_to_dict(self, svc):
        svc.start()
        d = svc.health().to_dict()
        assert d["healthy"] is True
        assert "stats" in d

    def test_get_stats(self, svc):
        assert isinstance(svc.get_stats(), SchedulerStats)

    def test_reset_stats(self, svc):
        svc._stats.tick_count = 100
        svc.reset_stats()
        assert svc.get_stats().tick_count == 0
