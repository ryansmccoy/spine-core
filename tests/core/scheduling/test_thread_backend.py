"""Tests for spine.core.scheduling.thread_backend — Thread-based scheduler."""

from __future__ import annotations

import asyncio
import time

import pytest

from spine.core.scheduling.protocol import BackendHealth, SchedulerBackend
from spine.core.scheduling.thread_backend import ThreadSchedulerBackend


class TestThreadBackendInit:
    def test_default_state(self):
        backend = ThreadSchedulerBackend()
        assert backend.name == "thread"
        assert backend.is_running is False
        assert backend.tick_count == 0
        assert backend.last_tick is None

    def test_satisfies_protocol(self):
        backend = ThreadSchedulerBackend()
        assert isinstance(backend, SchedulerBackend)


class TestThreadBackendHealth:
    def test_health_when_stopped(self):
        backend = ThreadSchedulerBackend()
        h = backend.health()
        assert h["healthy"] is False
        assert h["backend"] == "thread"
        assert h["tick_count"] == 0
        assert h["last_tick"] is None

    def test_get_health_returns_backend_health(self):
        backend = ThreadSchedulerBackend()
        h = backend.get_health()
        assert isinstance(h, BackendHealth)
        assert h.healthy is False
        assert h.backend == "thread"


class TestThreadBackendStartStop:
    def test_start_and_stop(self):
        backend = ThreadSchedulerBackend()
        calls = []

        async def tick():
            calls.append(1)

        backend.start(tick, interval_seconds=0.05)
        assert backend.is_running is True

        time.sleep(0.15)  # Allow ~2-3 ticks
        backend.stop()

        assert backend.is_running is False
        assert backend.tick_count > 0
        assert len(calls) > 0

    def test_double_start_is_noop(self):
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=60.0)
        backend.start(tick, interval_seconds=60.0)  # Should warn, not crash
        backend.stop()

    def test_stop_when_not_started(self):
        backend = ThreadSchedulerBackend()
        backend.stop()  # Should be safe no-op

    def test_health_when_running(self):
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=0.05)
        time.sleep(0.12)

        h = backend.health()
        assert h["healthy"] is True
        assert h["tick_count"] > 0
        assert h["last_tick"] is not None

        backend.stop()

    def test_tick_callback_receives_no_args(self):
        backend = ThreadSchedulerBackend()
        received = []

        async def tick():
            received.append(True)

        backend.start(tick, interval_seconds=0.05)
        time.sleep(0.12)
        backend.stop()

        assert len(received) > 0

    def test_tick_exception_does_not_crash_backend(self):
        backend = ThreadSchedulerBackend()
        call_count = []

        async def bad_tick():
            call_count.append(1)
            if len(call_count) == 1:
                raise RuntimeError("boom")

        backend.start(bad_tick, interval_seconds=0.05)
        time.sleep(0.2)  # Give time for recovery ticks
        backend.stop()

        # Should have continued ticking after error
        assert len(call_count) > 1

    def test_last_tick_updated(self):
        backend = ThreadSchedulerBackend()

        async def tick():
            pass

        backend.start(tick, interval_seconds=0.05)
        time.sleep(0.12)
        backend.stop()

        assert backend.last_tick is not None
