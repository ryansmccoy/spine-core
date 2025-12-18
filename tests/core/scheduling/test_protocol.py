"""Tests for spine.core.scheduling.protocol — Backend protocol + BackendHealth."""

from __future__ import annotations

from datetime import datetime, timezone

from spine.core.scheduling.protocol import BackendHealth, SchedulerBackend


# ── BackendHealth ────────────────────────────────────────────────────────


class TestBackendHealth:
    def test_construction_defaults(self):
        h = BackendHealth(healthy=True, backend="thread")
        assert h.healthy is True
        assert h.backend == "thread"
        assert h.tick_count == 0
        assert h.last_tick is None
        assert h.drift_ms is None
        assert h.extra == {}

    def test_to_dict(self):
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        h = BackendHealth(
            healthy=True,
            backend="thread",
            tick_count=42,
            last_tick=ts,
            drift_ms=1.5,
            extra={"interval": 10.0},
        )
        d = h.to_dict()
        assert d["healthy"] is True
        assert d["backend"] == "thread"
        assert d["tick_count"] == 42
        assert d["last_tick"] == ts.isoformat()
        assert d["drift_ms"] == 1.5
        assert d["interval"] == 10.0  # extra merged into dict

    def test_to_dict_none_last_tick(self):
        h = BackendHealth(healthy=False, backend="test")
        d = h.to_dict()
        assert d["last_tick"] is None


# ── SchedulerBackend protocol ────────────────────────────────────────────


class TestSchedulerBackendProtocol:
    def test_thread_backend_satisfies_protocol(self):
        """ThreadSchedulerBackend must implement SchedulerBackend."""
        from spine.core.scheduling.thread_backend import ThreadSchedulerBackend

        backend = ThreadSchedulerBackend()
        assert isinstance(backend, SchedulerBackend)

    def test_protocol_has_required_methods(self):
        assert hasattr(SchedulerBackend, "start")
        assert hasattr(SchedulerBackend, "stop")
        assert hasattr(SchedulerBackend, "health")
