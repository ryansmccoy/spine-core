"""Tests for spine.core.scheduling.health — health checks and tick stability.

Tests SchedulerHealthReport, check_tick_interval_stability, and get_ntp_time
without requiring real network access or a running scheduler.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from spine.core.scheduling.health import (
    SchedulerHealthReport,
    check_scheduler_health,
    check_tick_interval_stability,
    get_ntp_time,
)


class TestSchedulerHealthReport:
    def test_defaults(self):
        r = SchedulerHealthReport(healthy=True)
        assert r.healthy is True
        assert r.checks == {}
        assert r.warnings == []
        assert r.errors == []

    def test_to_dict(self):
        r = SchedulerHealthReport(
            healthy=False,
            checks={"backend_running": False},
            errors=["Backend down"],
        )
        d = r.to_dict()
        assert d["healthy"] is False
        assert d["checks"]["backend_running"] is False
        assert "Backend down" in d["errors"]

    def test_unhealthy_with_errors(self):
        r = SchedulerHealthReport(healthy=True, errors=["broken"])
        assert len(r.errors) == 1


class TestCheckTickIntervalStability:
    def test_insufficient_data(self):
        result = check_tick_interval_stability([])
        assert result["stable"] is True
        assert result["message"] == "Insufficient data"

    def test_single_tick(self):
        result = check_tick_interval_stability([datetime.now(UTC)])
        assert result["stable"] is True

    def test_stable_ticks(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        ticks = [base + timedelta(seconds=i * 10) for i in range(10)]
        result = check_tick_interval_stability(ticks, expected_interval=10.0)
        assert result["stable"] is True
        assert result["samples"] == 9
        assert abs(result["avg_interval"] - 10.0) < 0.01
        assert result["jitter_pct"] < 1.0

    def test_unstable_ticks(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        ticks = [
            base,
            base + timedelta(seconds=5),   # way too fast
            base + timedelta(seconds=25),  # way too slow
            base + timedelta(seconds=35),  # normal
        ]
        result = check_tick_interval_stability(ticks, expected_interval=10.0, tolerance=0.3)
        assert result["stable"] is False
        assert result["max_deviation"] > 5.0

    def test_metrics_present(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        ticks = [base + timedelta(seconds=i * 10) for i in range(5)]
        result = check_tick_interval_stability(ticks)
        assert "std_dev" in result
        assert "jitter_pct" in result
        assert "min_interval" in result
        assert "max_interval" in result


class TestGetNtpTime:
    @patch("spine.core.scheduling.health.socket.socket")
    def test_timeout_returns_none(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.recvfrom.side_effect = TimeoutError("timeout")
        mock_socket_cls.return_value = mock_sock

        result = get_ntp_time(timeout=0.1)
        assert result is None

    @patch("spine.core.scheduling.health.socket.socket")
    def test_short_response_returns_none(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.recvfrom.return_value = (b'\x00' * 10, ("pool.ntp.org", 123))
        mock_socket_cls.return_value = mock_sock

        result = get_ntp_time()
        assert result is None


class TestCheckSchedulerHealth:
    def _mock_service(self, **overrides):
        service = MagicMock()
        service.backend.health.return_value = {"healthy": True}
        service.is_running = True

        stats = MagicMock()
        stats.last_tick = datetime.now(UTC) - timedelta(seconds=5)
        stats.tick_count = 100
        stats.schedules_processed = 50
        stats.schedules_skipped = 2
        stats.schedules_failed = 1
        service.get_stats.return_value = stats

        service.repository.count_enabled.return_value = 10
        service.lock_manager.list_active_locks.return_value = []

        for k, v in overrides.items():
            setattr(service, k, v)
        return service

    def test_healthy_service(self):
        service = self._mock_service()
        report = check_scheduler_health(service, check_ntp=False)
        assert report.healthy is True
        assert report.checks["backend_running"] is True
        assert report.checks["tick_recent"] is True

    def test_backend_unhealthy(self):
        service = self._mock_service()
        service.backend.health.return_value = {"healthy": False}
        report = check_scheduler_health(service, check_ntp=False)
        assert report.healthy is False
        assert "Backend is not running" in report.errors

    def test_backend_health_exception(self):
        service = self._mock_service()
        service.backend.health.side_effect = Exception("crash")
        report = check_scheduler_health(service, check_ntp=False)
        assert report.healthy is False
        assert report.checks["backend_running"] is False

    def test_stale_tick_warning(self):
        service = self._mock_service()
        stats = service.get_stats.return_value
        stats.last_tick = datetime.now(UTC) - timedelta(seconds=120)
        report = check_scheduler_health(
            service, check_ntp=False, tick_age_threshold_seconds=60.0,
        )
        assert report.checks["tick_recent"] is False
        assert any("tick" in w.lower() for w in report.warnings)

    def test_no_ticks_yet(self):
        service = self._mock_service()
        stats = service.get_stats.return_value
        stats.last_tick = None
        report = check_scheduler_health(service, check_ntp=False)
        assert report.checks["tick_recent"] is False

    def test_high_failure_rate_warning(self):
        service = self._mock_service()
        stats = service.get_stats.return_value
        stats.schedules_processed = 50
        stats.schedules_failed = 20  # > 10% of total
        report = check_scheduler_health(service, check_ntp=False)
        assert any("failure rate" in w.lower() for w in report.warnings)
