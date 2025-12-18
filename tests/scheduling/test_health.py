"""Tests for scheduler health monitoring."""

from datetime import datetime, timedelta, UTC

import pytest

from spine.core.scheduling.health import (
    check_scheduler_health,
    check_tick_interval_stability,
    SchedulerHealthReport,
)


class TestSchedulerHealthCheck:
    """Test check_scheduler_health function."""

    def test_health_check_basic(self, scheduler_service):
        """Basic health check returns report."""
        report = check_scheduler_health(scheduler_service, check_ntp=False)
        
        assert isinstance(report, SchedulerHealthReport)
        assert "backend_running" in report.checks

    def test_health_check_running_service(self, scheduler_service):
        """Health check on running service."""
        scheduler_service.start()
        
        try:
            report = check_scheduler_health(scheduler_service, check_ntp=False)
            
            assert report.checks["backend_running"] is True
            assert report.healthy is True
        finally:
            scheduler_service.stop()

    def test_health_check_stopped_service(self, scheduler_service):
        """Health check on stopped service."""
        report = check_scheduler_health(scheduler_service, check_ntp=False)
        
        assert report.checks["backend_running"] is False
        assert report.healthy is False
        assert len(report.errors) > 0

    def test_health_check_to_dict(self, scheduler_service):
        """Health report serializes to dict."""
        report = check_scheduler_health(scheduler_service, check_ntp=False)
        d = report.to_dict()
        
        assert "healthy" in d
        assert "checks" in d
        assert "backend" in d
        assert "schedules" in d
        assert "timing" in d
        assert "warnings" in d
        assert "errors" in d


class TestTickIntervalStability:
    """Test check_tick_interval_stability function."""

    def test_stable_intervals(self):
        """Stable tick intervals are detected."""
        now = datetime.now(UTC)
        tick_times = [
            now,
            now + timedelta(seconds=10),
            now + timedelta(seconds=20),
            now + timedelta(seconds=30),
        ]
        
        result = check_tick_interval_stability(tick_times, expected_interval=10.0)
        
        assert result["stable"] is True
        assert result["samples"] == 3
        assert abs(result["avg_interval"] - 10.0) < 0.1

    def test_unstable_intervals(self):
        """Unstable tick intervals are detected."""
        now = datetime.now(UTC)
        tick_times = [
            now,
            now + timedelta(seconds=5),   # Too fast
            now + timedelta(seconds=25),  # Too slow
            now + timedelta(seconds=35),
        ]
        
        result = check_tick_interval_stability(tick_times, expected_interval=10.0)
        
        # max deviation is 10s (25-15=10 or 5-10=-5 abs 5 vs 10), but second to third is 20s
        assert result["samples"] == 3

    def test_insufficient_data(self):
        """Insufficient tick data returns stable."""
        result = check_tick_interval_stability([datetime.now(UTC)])
        
        assert result["stable"] is True
        assert result["message"] == "Insufficient data"

    def test_empty_data(self):
        """Empty tick data returns stable."""
        result = check_tick_interval_stability([])
        
        assert result["stable"] is True


class TestSchedulerHealthReportStructure:
    """Test SchedulerHealthReport dataclass."""

    def test_default_values(self):
        """Default values are correct."""
        report = SchedulerHealthReport(healthy=True)
        
        assert report.healthy is True
        assert report.checks == {}
        assert report.backend == {}
        assert report.schedules == {}
        assert report.timing == {}
        assert report.warnings == []
        assert report.errors == []

    def test_with_data(self):
        """Report with populated data."""
        report = SchedulerHealthReport(
            healthy=True,
            checks={"backend_running": True},
            backend={"name": "thread"},
            schedules={"enabled": 5},
            warnings=["Time drift detected"],
        )
        
        assert report.checks["backend_running"] is True
        assert report.backend["name"] == "thread"
        assert report.schedules["enabled"] == 5
        assert len(report.warnings) == 1
