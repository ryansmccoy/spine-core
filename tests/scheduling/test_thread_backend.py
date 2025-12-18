"""Tests for ThreadSchedulerBackend."""

import asyncio
import time
from datetime import datetime, UTC

import pytest

from spine.core.scheduling import ThreadSchedulerBackend
from spine.core.scheduling.protocol import SchedulerBackend


class TestThreadSchedulerBackend:
    """Test ThreadSchedulerBackend implementation."""

    def test_implements_protocol(self):
        """Backend implements SchedulerBackend protocol."""
        backend = ThreadSchedulerBackend()
        assert isinstance(backend, SchedulerBackend)
        assert backend.name == "thread"

    def test_start_and_stop(self):
        """Backend starts and stops cleanly."""
        backend = ThreadSchedulerBackend()
        tick_count = 0

        async def tick():
            nonlocal tick_count
            tick_count += 1

        backend.start(tick, interval_seconds=0.1)
        assert backend.is_running

        # Wait for a few ticks
        time.sleep(0.35)

        backend.stop()
        assert not backend.is_running

        # Should have ticked at least 2 times
        assert tick_count >= 2

    def test_health_before_start(self):
        """Health returns unhealthy before start."""
        backend = ThreadSchedulerBackend()
        health = backend.health()
        
        assert health["healthy"] is False
        assert health["backend"] == "thread"
        assert health["tick_count"] == 0
        assert health["last_tick"] is None

    def test_health_after_start(self):
        """Health returns healthy after start."""
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=0.1)
        time.sleep(0.15)

        health = backend.health()
        assert health["healthy"] is True
        assert health["tick_count"] >= 1
        assert health["last_tick"] is not None

        backend.stop()

    def test_double_start_ignored(self):
        """Double start is ignored with warning."""
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=1.0)
        backend.start(tick, interval_seconds=1.0)  # Should be ignored

        assert backend.is_running
        backend.stop()

    def test_tick_callback_exception_handled(self):
        """Exceptions in tick callback don't crash backend."""
        backend = ThreadSchedulerBackend()
        error_count = 0

        async def failing_tick():
            nonlocal error_count
            error_count += 1
            raise ValueError("Test error")

        backend.start(failing_tick, interval_seconds=0.1)
        time.sleep(0.35)
        backend.stop()

        # Should have tried multiple times despite errors
        assert error_count >= 2

    def test_tick_count_property(self):
        """tick_count property tracks ticks."""
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        assert backend.tick_count == 0

        backend.start(tick, interval_seconds=0.1)
        time.sleep(0.25)
        backend.stop()

        assert backend.tick_count >= 2

    def test_last_tick_property(self):
        """last_tick property tracks last tick time."""
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        assert backend.last_tick is None

        backend.start(tick, interval_seconds=0.1)
        time.sleep(0.15)
        backend.stop()

        assert backend.last_tick is not None
        assert isinstance(backend.last_tick, datetime)

    def test_get_health_structured(self):
        """get_health() returns BackendHealth object."""
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=0.1)
        time.sleep(0.15)

        health = backend.get_health()
        
        assert health.healthy is True
        assert health.backend == "thread"
        assert health.tick_count >= 1
        assert "interval_seconds" in health.extra

        backend.stop()
