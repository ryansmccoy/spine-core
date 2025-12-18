"""Tests for spine.core.scheduling.health — Health monitoring structures."""

from __future__ import annotations

from spine.core.scheduling.health import SchedulerHealthReport


class TestSchedulerHealthReport:
    def test_construction_defaults(self):
        r = SchedulerHealthReport(healthy=True)
        assert r.healthy is True
        assert r.checks == {}
        assert r.backend == {}
        assert r.schedules == {}
        assert r.timing == {}
        assert r.warnings == []
        assert r.errors == []

    def test_to_dict(self):
        r = SchedulerHealthReport(
            healthy=False,
            checks={"backend_running": False},
            backend={"healthy": False, "backend": "thread"},
            warnings=["Tick drift detected"],
            errors=["Backend not running"],
        )
        d = r.to_dict()
        assert d["healthy"] is False
        assert d["checks"]["backend_running"] is False
        assert len(d["warnings"]) == 1
        assert len(d["errors"]) == 1

    def test_accumulate_warnings(self):
        r = SchedulerHealthReport(healthy=True)
        r.warnings.append("warn-1")
        r.warnings.append("warn-2")
        assert len(r.warnings) == 2

    def test_accumulate_errors(self):
        r = SchedulerHealthReport(healthy=True)
        r.errors.append("err-1")
        r.healthy = False
        assert r.healthy is False
        assert len(r.errors) == 1
