"""Tests for APSchedulerBackend."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from spine.core.scheduling.protocol import SchedulerBackend


class TestAPSchedulerBackendImportGuard:
    """Test that import fails gracefully when apscheduler is not installed."""

    def test_import_error_without_apscheduler(self, monkeypatch):
        """Raises ImportError with install hint when apscheduler missing."""
        # Remove apscheduler from sys.modules and prevent import
        monkeypatch.delitem(sys.modules, "apscheduler", raising=False)
        monkeypatch.delitem(sys.modules, "apscheduler.schedulers", raising=False)
        monkeypatch.delitem(sys.modules, "apscheduler.schedulers.background", raising=False)

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("apscheduler"):
                raise ImportError("No module named 'apscheduler'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Clear any cached module
        monkeypatch.delitem(sys.modules, "spine.core.scheduling.apscheduler_backend", raising=False)

        from spine.core.scheduling.apscheduler_backend import _require_apscheduler

        with pytest.raises(ImportError, match="spine-core\\[apscheduler\\]"):
            _require_apscheduler()


class TestAPSchedulerBackendWithMock:
    """Test APSchedulerBackend with mocked APScheduler."""

    @pytest.fixture
    def mock_apscheduler(self, monkeypatch):
        """Create a mock APScheduler environment."""
        # Create mock scheduler class
        mock_scheduler_instance = MagicMock()
        mock_scheduler_instance.running = False
        mock_scheduler_instance.get_jobs.return_value = []

        mock_bg_scheduler_cls = MagicMock(return_value=mock_scheduler_instance)

        # Create mock module hierarchy
        mock_bg_module = ModuleType("apscheduler.schedulers.background")
        mock_bg_module.BackgroundScheduler = mock_bg_scheduler_cls

        mock_schedulers_module = ModuleType("apscheduler.schedulers")
        mock_schedulers_module.background = mock_bg_module

        mock_apscheduler_module = ModuleType("apscheduler")
        mock_apscheduler_module.schedulers = mock_schedulers_module

        monkeypatch.setitem(sys.modules, "apscheduler", mock_apscheduler_module)
        monkeypatch.setitem(sys.modules, "apscheduler.schedulers", mock_schedulers_module)
        monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", mock_bg_module)

        # Clear cached import
        monkeypatch.delitem(sys.modules, "spine.core.scheduling.apscheduler_backend", raising=False)

        return mock_scheduler_instance

    def test_backend_name(self, mock_apscheduler):
        """Backend has correct name."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        assert backend.name == "apscheduler"

    def test_start_adds_job_and_starts(self, mock_apscheduler):
        """start() adds an interval job and starts the scheduler."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=15.0)

        mock_apscheduler.add_job.assert_called_once()
        call_kwargs = mock_apscheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "spine_scheduler_tick"
        assert call_kwargs[1]["seconds"] == 15.0
        assert call_kwargs[0][1] == "interval"  # trigger type
        mock_apscheduler.start.assert_called_once()

    def test_stop_shuts_down(self, mock_apscheduler):
        """stop() shuts down the scheduler."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        mock_apscheduler.running = True

        backend.stop()

        mock_apscheduler.shutdown.assert_called_once_with(wait=True)

    def test_stop_noop_when_not_running(self, mock_apscheduler):
        """stop() does nothing when scheduler not running."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        mock_apscheduler.running = False

        backend.stop()

        mock_apscheduler.shutdown.assert_not_called()

    def test_health_not_running(self, mock_apscheduler):
        """health() returns unhealthy when not running."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        mock_apscheduler.running = False

        h = backend.health()
        assert h["healthy"] is False
        assert h["backend"] == "apscheduler"
        assert h["tick_count"] == 0
        assert h["last_tick"] is None

    def test_health_running(self, mock_apscheduler):
        """health() returns healthy with job count when running."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        mock_apscheduler.running = True
        mock_apscheduler.get_jobs.return_value = [MagicMock()]

        # Simulate ticks
        backend._tick_count = 5
        backend._last_tick = datetime(2026, 1, 1, tzinfo=UTC)

        h = backend.health()
        assert h["healthy"] is True
        assert h["tick_count"] == 5
        assert h["last_tick"] == "2026-01-01T00:00:00+00:00"
        assert h["scheduled_jobs"] == 1

    def test_tick_wrapper_increments_counters(self, mock_apscheduler):
        """The internal tick wrapper increments count and timestamp."""
        from spine.core.scheduling.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        tick_called = False

        async def tick():
            nonlocal tick_called
            tick_called = True

        backend.start(tick, interval_seconds=10.0)

        # Get the wrapper function that was passed to add_job
        wrapper_fn = mock_apscheduler.add_job.call_args[0][0]

        # Call it directly
        wrapper_fn()

        assert backend._tick_count == 1
        assert backend._last_tick is not None
        assert tick_called is True

    def test_protocol_compliance_via_lazy_import(self):
        """APSchedulerBackend is accessible via __getattr__ on scheduling package."""
        # Test module-level lazy import
        from spine.core.scheduling import __all__

        assert "APSchedulerBackend" in __all__
