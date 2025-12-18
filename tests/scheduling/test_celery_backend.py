"""Tests for CeleryBeatBackend."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import MagicMock

import pytest


class TestCeleryBeatBackendImportGuard:
    """Test that import fails gracefully when celery is not installed."""

    def test_import_error_without_celery(self, monkeypatch):
        """Raises ImportError with install hint when celery missing."""
        monkeypatch.delitem(sys.modules, "celery", raising=False)

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "celery" or name.startswith("celery."):
                raise ImportError("No module named 'celery'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.delitem(sys.modules, "spine.core.scheduling.celery_backend", raising=False)

        from spine.core.scheduling.celery_backend import _require_celery

        with pytest.raises(ImportError, match="Celery is required"):
            _require_celery()


class TestCeleryBeatBackendWithMock:
    """Test CeleryBeatBackend with mocked Celery."""

    @pytest.fixture
    def mock_celery_env(self, monkeypatch):
        """Set up mock celery environment and return a mock app."""
        mock_celery_module = ModuleType("celery")
        monkeypatch.setitem(sys.modules, "celery", mock_celery_module)
        monkeypatch.delitem(sys.modules, "spine.core.scheduling.celery_backend", raising=False)

        # Create a mock Celery app
        mock_app = MagicMock()
        mock_app.conf = MagicMock()
        mock_app.conf.beat_schedule = {}
        mock_app.task = MagicMock(side_effect=lambda **kwargs: lambda fn: fn)

        return mock_app

    def test_backend_name(self, mock_celery_env):
        """Backend has correct name."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)
        assert backend.name == "celery_beat"

    def test_requires_celery_app(self, mock_celery_env):
        """Raises ValueError when celery_app is None."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        with pytest.raises(ValueError, match="requires a Celery app instance"):
            CeleryBeatBackend(celery_app=None)

    def test_start_registers_beat_schedule(self, mock_celery_env):
        """start() registers task in beat_schedule."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)

        async def tick():
            pass

        backend.start(tick, interval_seconds=30.0)

        assert "spine_scheduler_tick" in mock_celery_env.conf.beat_schedule
        entry = mock_celery_env.conf.beat_schedule["spine_scheduler_tick"]
        assert entry["task"] == "spine.scheduling.tick"
        assert entry["schedule"] == 30.0
        assert backend._running is True

    def test_stop_unregisters_beat_schedule(self, mock_celery_env):
        """stop() removes task from beat_schedule."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)

        async def tick():
            pass

        backend.start(tick, interval_seconds=10.0)
        assert "spine_scheduler_tick" in mock_celery_env.conf.beat_schedule

        backend.stop()
        assert "spine_scheduler_tick" not in mock_celery_env.conf.beat_schedule
        assert backend._running is False

    def test_health_before_start(self, mock_celery_env):
        """health() returns unhealthy before start."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)
        h = backend.health()

        assert h["healthy"] is False
        assert h["backend"] == "celery_beat"
        assert h["tick_count"] == 0
        assert h["last_tick"] is None
        assert h["task_registered"] is False
        assert h["experimental"] is True

    def test_health_after_start(self, mock_celery_env):
        """health() returns healthy after start."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)

        async def tick():
            pass

        backend.start(tick, interval_seconds=10.0)

        # Simulate ticks
        backend._tick_count = 3
        backend._last_tick = datetime(2026, 2, 1, tzinfo=UTC)

        h = backend.health()
        assert h["healthy"] is True
        assert h["tick_count"] == 3
        assert h["last_tick"] == "2026-02-01T00:00:00+00:00"
        assert h["task_registered"] is True

    def test_health_after_stop(self, mock_celery_env):
        """health() returns unhealthy after stop."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)

        async def tick():
            pass

        backend.start(tick, interval_seconds=10.0)
        backend.stop()

        h = backend.health()
        assert h["healthy"] is False
        assert h["task_registered"] is False

    def test_multiple_start_stop_cycles(self, mock_celery_env):
        """Backend handles multiple start/stop cycles."""
        from spine.core.scheduling.celery_backend import CeleryBeatBackend

        backend = CeleryBeatBackend(celery_app=mock_celery_env)

        async def tick():
            pass

        # Cycle 1
        backend.start(tick, interval_seconds=10.0)
        assert backend._running is True
        backend.stop()
        assert backend._running is False

        # Cycle 2
        backend.start(tick, interval_seconds=20.0)
        assert backend._running is True
        entry = mock_celery_env.conf.beat_schedule["spine_scheduler_tick"]
        assert entry["schedule"] == 20.0
        backend.stop()

    def test_protocol_compliance_via_lazy_import(self):
        """CeleryBeatBackend is accessible via __getattr__ on scheduling package."""
        from spine.core.scheduling import __all__

        assert "CeleryBeatBackend" in __all__
