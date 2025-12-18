"""Health checks for execution infrastructure.

Provides health status for monitoring and alerting:
- DLQ depth and age
- Stale executions
- Lock contention
- Database connectivity

Example:
    >>> from spine.execution.health import ExecutionHealthChecker
    >>>
    >>> checker = ExecutionHealthChecker(ledger, dlq, guard, repo)
    >>> health = checker.check()
    >>> print(health.status)  # "healthy" | "degraded" | "unhealthy"
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .concurrency import ConcurrencyGuard
from .dlq import DLQManager
from .ledger import ExecutionLedger
from .repository import ExecutionRepository


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=utcnow)


@dataclass
class HealthReport:
    """Overall health report."""

    status: HealthStatus
    checks: list[HealthCheckResult]
    timestamp: datetime = field(default_factory=utcnow)

    @property
    def healthy(self) -> bool:
        """Check if overall status is healthy."""
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                    "details": check.details,
                }
                for check in self.checks
            ],
        }


@dataclass
class HealthThresholds:
    """Configurable thresholds for health checks."""

    # DLQ thresholds
    dlq_warning_count: int = 10
    dlq_critical_count: int = 50

    # Stale execution thresholds (minutes)
    stale_warning_minutes: int = 30
    stale_critical_minutes: int = 60
    stale_warning_count: int = 1
    stale_critical_count: int = 5

    # Failure rate thresholds (percentage)
    failure_rate_warning: float = 10.0
    failure_rate_critical: float = 25.0

    # Lock thresholds
    lock_warning_count: int = 5
    lock_critical_count: int = 10


class ExecutionHealthChecker:
    """Health checker for execution infrastructure.

    Checks:
    - database: Can connect and query
    - dlq: Dead letter queue depth
    - stale: Stuck/stale executions
    - failure_rate: Recent failure percentage
    - locks: Active lock count
    """

    def __init__(
        self,
        ledger: ExecutionLedger,
        dlq: DLQManager | None = None,
        guard: ConcurrencyGuard | None = None,
        repo: ExecutionRepository | None = None,
        thresholds: HealthThresholds | None = None,
    ):
        """Initialize health checker.

        Args:
            ledger: Execution ledger (required)
            dlq: DLQ manager (optional)
            guard: Concurrency guard (optional)
            repo: Execution repository (optional)
            thresholds: Custom thresholds
        """
        self._ledger = ledger
        self._dlq = dlq
        self._guard = guard
        self._repo = repo
        self._thresholds = thresholds or HealthThresholds()

    def check(self) -> HealthReport:
        """Run all health checks.

        Returns:
            HealthReport with overall status and individual checks
        """
        checks: list[HealthCheckResult] = []

        # Database connectivity
        checks.append(self._check_database())

        # DLQ depth
        if self._dlq is not None:
            checks.append(self._check_dlq())

        # Stale executions
        if self._repo is not None:
            checks.append(self._check_stale_executions())
            checks.append(self._check_failure_rate())

        # Lock contention
        if self._guard is not None:
            checks.append(self._check_locks())

        # Determine overall status
        statuses = [check.status for check in checks]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return HealthReport(status=overall, checks=checks)

    def _check_database(self) -> HealthCheckResult:
        """Check database connectivity."""
        try:
            # Simple query to verify connection
            self._ledger.list_executions(limit=1)
            return HealthCheckResult(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database connection OK",
                details={"query_successful": True},
            )
        except Exception as e:
            return HealthCheckResult(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {e}",
                details={"error": str(e)},
            )

    def _check_dlq(self) -> HealthCheckResult:
        """Check dead letter queue depth."""
        try:
            count = self._dlq.count_unresolved()
            thresholds = self._thresholds

            if count >= thresholds.dlq_critical_count:
                status = HealthStatus.UNHEALTHY
                message = f"DLQ critical: {count} unresolved items"
            elif count >= thresholds.dlq_warning_count:
                status = HealthStatus.DEGRADED
                message = f"DLQ warning: {count} unresolved items"
            else:
                status = HealthStatus.HEALTHY
                message = f"DLQ OK: {count} unresolved items"

            return HealthCheckResult(
                name="dlq",
                status=status,
                message=message,
                details={
                    "unresolved_count": count,
                    "warning_threshold": thresholds.dlq_warning_count,
                    "critical_threshold": thresholds.dlq_critical_count,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="dlq",
                status=HealthStatus.UNHEALTHY,
                message=f"DLQ check failed: {e}",
                details={"error": str(e)},
            )

    def _check_stale_executions(self) -> HealthCheckResult:
        """Check for stale/stuck executions."""
        try:
            thresholds = self._thresholds

            # Check for critical stale (longer threshold)
            critical_stale = self._repo.get_stale_executions(older_than_minutes=thresholds.stale_critical_minutes)

            # Check for warning stale (shorter threshold)
            warning_stale = self._repo.get_stale_executions(older_than_minutes=thresholds.stale_warning_minutes)

            critical_count = len(critical_stale)
            warning_count = len(warning_stale)

            if critical_count >= thresholds.stale_critical_count:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: {critical_count} executions stuck > {thresholds.stale_critical_minutes}min"
            elif warning_count >= thresholds.stale_warning_count:
                status = HealthStatus.DEGRADED
                message = f"Warning: {warning_count} executions stuck > {thresholds.stale_warning_minutes}min"
            else:
                status = HealthStatus.HEALTHY
                message = "No stale executions"

            return HealthCheckResult(
                name="stale_executions",
                status=status,
                message=message,
                details={
                    "stale_count_warning": warning_count,
                    "stale_count_critical": critical_count,
                    "warning_threshold_minutes": thresholds.stale_warning_minutes,
                    "critical_threshold_minutes": thresholds.stale_critical_minutes,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="stale_executions",
                status=HealthStatus.UNHEALTHY,
                message=f"Stale check failed: {e}",
                details={"error": str(e)},
            )

    def _check_failure_rate(self) -> HealthCheckResult:
        """Check recent failure rate."""
        try:
            stats = self._repo.get_execution_stats(hours=1)
            status_counts = stats.get("status_counts", {})

            completed = status_counts.get("completed", 0)
            failed = status_counts.get("failed", 0)
            total = completed + failed

            if total == 0:
                return HealthCheckResult(
                    name="failure_rate",
                    status=HealthStatus.HEALTHY,
                    message="No recent executions",
                    details={"total_executions": 0},
                )

            failure_rate = (failed / total) * 100
            thresholds = self._thresholds

            if failure_rate >= thresholds.failure_rate_critical:
                status = HealthStatus.UNHEALTHY
                message = f"Critical failure rate: {failure_rate:.1f}%"
            elif failure_rate >= thresholds.failure_rate_warning:
                status = HealthStatus.DEGRADED
                message = f"Elevated failure rate: {failure_rate:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Failure rate OK: {failure_rate:.1f}%"

            return HealthCheckResult(
                name="failure_rate",
                status=status,
                message=message,
                details={
                    "failure_rate_percent": failure_rate,
                    "completed": completed,
                    "failed": failed,
                    "total": total,
                    "warning_threshold": thresholds.failure_rate_warning,
                    "critical_threshold": thresholds.failure_rate_critical,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="failure_rate",
                status=HealthStatus.UNHEALTHY,
                message=f"Failure rate check failed: {e}",
                details={"error": str(e)},
            )

    def _check_locks(self) -> HealthCheckResult:
        """Check lock contention."""
        try:
            active_locks = self._guard.list_active_locks()
            lock_count = len(active_locks)
            thresholds = self._thresholds

            if lock_count >= thresholds.lock_critical_count:
                status = HealthStatus.UNHEALTHY
                message = f"High lock contention: {lock_count} active locks"
            elif lock_count >= thresholds.lock_warning_count:
                status = HealthStatus.DEGRADED
                message = f"Elevated locks: {lock_count} active locks"
            else:
                status = HealthStatus.HEALTHY
                message = f"Locks OK: {lock_count} active"

            return HealthCheckResult(
                name="locks",
                status=status,
                message=message,
                details={
                    "active_lock_count": lock_count,
                    "warning_threshold": thresholds.lock_warning_count,
                    "critical_threshold": thresholds.lock_critical_count,
                    "lock_keys": [lock.lock_key for lock in active_locks],
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="locks",
                status=HealthStatus.UNHEALTHY,
                message=f"Lock check failed: {e}",
                details={"error": str(e)},
            )


def create_health_endpoint_handler(
    checker: ExecutionHealthChecker,
) -> dict[str, Any]:
    """Create a health check response for HTTP endpoints.

    Returns dict suitable for JSON response with appropriate status code hint.
    """
    report = checker.check()
    response = report.to_dict()

    # Add status code hint
    if report.status == HealthStatus.HEALTHY:
        response["_status_code"] = 200
    elif report.status == HealthStatus.DEGRADED:
        response["_status_code"] = 200  # Still operational
    else:
        response["_status_code"] = 503  # Service unavailable

    return response
