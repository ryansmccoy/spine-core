"""Tests for health checks."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from spine.execution.health import (
    HealthStatus,
    HealthThresholds,
    HealthCheckResult,
    HealthReport,
    ExecutionHealthChecker,
    create_health_endpoint_handler,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestHealthThresholds:
    """Tests for HealthThresholds configuration."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = HealthThresholds()
        assert thresholds.dlq_warning_count == 10
        assert thresholds.dlq_critical_count == 50
        assert thresholds.failure_rate_warning == 10.0
        assert thresholds.failure_rate_critical == 25.0
        assert thresholds.stale_warning_minutes == 30
        assert thresholds.stale_critical_minutes == 60

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = HealthThresholds(
            dlq_warning_count=5,
            dlq_critical_count=20,
            failure_rate_warning=5.0,
            failure_rate_critical=15.0,
            stale_warning_minutes=15,
            stale_critical_minutes=45,
        )
        assert thresholds.dlq_warning_count == 5
        assert thresholds.dlq_critical_count == 20
        assert thresholds.failure_rate_warning == 5.0
        assert thresholds.stale_warning_minutes == 15


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_healthy_result(self):
        """Test creating a healthy result."""
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
        )
        assert result.name == "test_check"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
        assert result.details == {}

    def test_result_with_details(self):
        """Test result with details."""
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.DEGRADED,
            message="High latency",
            details={"latency_ms": 500},
        )
        assert result.details == {"latency_ms": 500}


class TestHealthReport:
    """Tests for HealthReport dataclass."""

    def test_healthy_report(self):
        """Test creating a healthy report."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.HEALTHY, "OK"),
        ]
        report = HealthReport(
            status=HealthStatus.HEALTHY,
            checks=checks,
        )
        assert report.status == HealthStatus.HEALTHY
        assert report.healthy is True
        assert len(report.checks) == 2

    def test_unhealthy_report(self):
        """Test unhealthy report."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
            HealthCheckResult("check2", HealthStatus.UNHEALTHY, "Failed"),
        ]
        report = HealthReport(
            status=HealthStatus.UNHEALTHY,
            checks=checks,
        )
        assert report.status == HealthStatus.UNHEALTHY
        assert report.healthy is False

    def test_report_to_dict(self):
        """Test report serialization."""
        checks = [
            HealthCheckResult("check1", HealthStatus.HEALTHY, "OK"),
        ]
        report = HealthReport(
            status=HealthStatus.HEALTHY,
            checks=checks,
        )
        
        data = report.to_dict()
        
        assert data["status"] == "healthy"
        assert len(data["checks"]) == 1
        assert data["checks"][0]["name"] == "check1"
        assert "timestamp" in data


class MockLedger:
    """Mock ExecutionLedger for testing."""

    def __init__(self, raise_error=False):
        self.raise_error = raise_error

    def list_executions(self, limit=10):
        if self.raise_error:
            raise ConnectionError("Database error")
        return []


class MockRepository:
    """Mock ExecutionRepository for testing."""

    def __init__(self):
        self.stale_executions = []
        self.execution_stats = {
            "status_counts": {
                "completed": 90,
                "failed": 10,
            }
        }

    def get_stale_executions(self, older_than_minutes: int):
        return self.stale_executions

    def get_execution_stats(self, hours: int = 1):
        return self.execution_stats


class MockDLQManager:
    """Mock DLQManager for testing."""

    def __init__(self):
        self.unresolved_count = 0

    def count_unresolved(self):
        return self.unresolved_count


class MockConcurrencyGuard:
    """Mock ConcurrencyGuard for testing."""

    def __init__(self):
        self.active_locks = []

    def list_active_locks(self):
        return self.active_locks


class TestExecutionHealthChecker:
    """Tests for ExecutionHealthChecker."""

    def test_all_healthy(self):
        """Test all checks healthy."""
        ledger = MockLedger()
        dlq = MockDLQManager()
        dlq.unresolved_count = 0
        repo = MockRepository()
        repo.execution_stats = {"status_counts": {"completed": 100, "failed": 0}}
        guard = MockConcurrencyGuard()
        
        checker = ExecutionHealthChecker(
            ledger=ledger,
            dlq=dlq,
            repo=repo,
            guard=guard,
        )
        
        report = checker.check()
        
        assert report.status == HealthStatus.HEALTHY

    def test_database_check_healthy(self):
        """Test database connectivity check."""
        ledger = MockLedger()
        
        checker = ExecutionHealthChecker(ledger=ledger)
        
        report = checker.check()
        
        db_check = next(c for c in report.checks if c.name == "database")
        assert db_check.status == HealthStatus.HEALTHY

    def test_database_check_unhealthy(self):
        """Test database connectivity failure."""
        ledger = MockLedger(raise_error=True)
        
        checker = ExecutionHealthChecker(ledger=ledger)
        
        report = checker.check()
        
        db_check = next(c for c in report.checks if c.name == "database")
        assert db_check.status == HealthStatus.UNHEALTHY

    def test_dlq_warning(self):
        """Test DLQ depth warning threshold."""
        ledger = MockLedger()
        dlq = MockDLQManager()
        dlq.unresolved_count = 15  # Above warning (10), below critical (50)
        
        checker = ExecutionHealthChecker(ledger=ledger, dlq=dlq)
        
        report = checker.check()
        
        dlq_check = next(c for c in report.checks if c.name == "dlq")
        assert dlq_check.status == HealthStatus.DEGRADED

    def test_dlq_critical(self):
        """Test DLQ depth critical threshold."""
        ledger = MockLedger()
        dlq = MockDLQManager()
        dlq.unresolved_count = 100  # Above critical (50)
        
        checker = ExecutionHealthChecker(ledger=ledger, dlq=dlq)
        
        report = checker.check()
        
        dlq_check = next(c for c in report.checks if c.name == "dlq")
        assert dlq_check.status == HealthStatus.UNHEALTHY

    def test_failure_rate_warning(self):
        """Test failure rate warning threshold."""
        ledger = MockLedger()
        repo = MockRepository()
        repo.execution_stats = {"status_counts": {"completed": 85, "failed": 15}}  # 15%
        
        checker = ExecutionHealthChecker(ledger=ledger, repo=repo)
        
        report = checker.check()
        
        failure_check = next(c for c in report.checks if c.name == "failure_rate")
        assert failure_check.status == HealthStatus.DEGRADED

    def test_failure_rate_critical(self):
        """Test failure rate critical threshold."""
        ledger = MockLedger()
        repo = MockRepository()
        repo.execution_stats = {"status_counts": {"completed": 70, "failed": 30}}  # 30%
        
        checker = ExecutionHealthChecker(ledger=ledger, repo=repo)
        
        report = checker.check()
        
        failure_check = next(c for c in report.checks if c.name == "failure_rate")
        assert failure_check.status == HealthStatus.UNHEALTHY

    def test_stale_executions_warning(self):
        """Test stale executions warning."""
        ledger = MockLedger()
        repo = MockRepository()
        repo.stale_executions = [MagicMock()]  # 1 stale execution
        
        checker = ExecutionHealthChecker(ledger=ledger, repo=repo)
        
        report = checker.check()
        
        stale_check = next(c for c in report.checks if c.name == "stale_executions")
        assert stale_check.status == HealthStatus.DEGRADED

    def test_lock_contention_warning(self):
        """Test lock contention warning."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        guard.active_locks = [MagicMock(lock_key=f"lock_{i}") for i in range(7)]  # Above warning (5)
        
        checker = ExecutionHealthChecker(ledger=ledger, guard=guard)
        
        report = checker.check()
        
        lock_check = next(c for c in report.checks if c.name == "locks")
        assert lock_check.status == HealthStatus.DEGRADED

    def test_overall_status_aggregation(self):
        """Test overall status is worst of all checks."""
        ledger = MockLedger()
        dlq = MockDLQManager()
        dlq.unresolved_count = 100  # Critical - UNHEALTHY
        repo = MockRepository()
        repo.execution_stats = {"status_counts": {"completed": 85, "failed": 15}}  # Warning - DEGRADED
        
        checker = ExecutionHealthChecker(ledger=ledger, dlq=dlq, repo=repo)
        
        report = checker.check()
        
        # Overall should be UNHEALTHY (worst)
        assert report.status == HealthStatus.UNHEALTHY

    def test_custom_thresholds(self):
        """Test using custom thresholds."""
        ledger = MockLedger()
        dlq = MockDLQManager()
        dlq.unresolved_count = 8  # Would be warning at default (10), healthy at custom (15)
        
        thresholds = HealthThresholds(
            dlq_warning_count=15,
            dlq_critical_count=30,
        )
        
        checker = ExecutionHealthChecker(
            ledger=ledger,
            dlq=dlq,
            thresholds=thresholds,
        )
        
        report = checker.check()
        
        dlq_check = next(c for c in report.checks if c.name == "dlq")
        assert dlq_check.status == HealthStatus.HEALTHY


class TestHealthEndpointHandler:
    """Tests for health endpoint handler."""

    def test_healthy_status_code(self):
        """Test healthy returns 200."""
        ledger = MockLedger()
        checker = ExecutionHealthChecker(ledger=ledger)
        
        response = create_health_endpoint_handler(checker)
        
        assert response["_status_code"] == 200
        assert response["status"] == "healthy"

    def test_degraded_status_code(self):
        """Test degraded returns 200."""
        ledger = MockLedger()
        dlq = MockDLQManager()
        dlq.unresolved_count = 15  # Warning level
        checker = ExecutionHealthChecker(ledger=ledger, dlq=dlq)
        
        response = create_health_endpoint_handler(checker)
        
        assert response["_status_code"] == 200
        assert response["status"] == "degraded"

    def test_unhealthy_status_code(self):
        """Test unhealthy returns 503."""
        ledger = MockLedger(raise_error=True)
        checker = ExecutionHealthChecker(ledger=ledger)
        
        response = create_health_endpoint_handler(checker)
        
        assert response["_status_code"] == 503
        assert response["status"] == "unhealthy"
