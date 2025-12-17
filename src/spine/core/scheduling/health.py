"""Scheduler health checks and drift detection.

This module provides health monitoring for the scheduler system,
including time drift detection and NTP synchronization checks.

┌──────────────────────────────────────────────────────────────────────────────┐
│  SCHEDULER HEALTH MONITORING                                                  │
│                                                                               │
│  Health Checks:                                                               │
│  1. Backend Health: Is the timing backend running?                           │
│  2. Tick Health: Are ticks happening at expected intervals?                  │
│  3. Time Drift: Is system clock synchronized with NTP?                       │
│  4. Schedule Health: Are schedules being processed?                          │
│                                                                               │
│  Time Drift Detection:                                                        │
│  ┌────────────────────────────────────────────────────────────────────┐      │
│  │   System Clock        NTP Server                                   │      │
│  │       │                   │                                        │      │
│  │       │  Query NTP time   │                                        │      │
│  │       ├──────────────────►│                                        │      │
│  │       │                   │                                        │      │
│  │       │  ◄───────────────┤  Response: 2024-01-15T10:00:00.123Z    │      │
│  │       │                   │                                        │      │
│  │       │                                                            │      │
│  │   Local: 2024-01-15T10:00:01.500Z                                  │      │
│  │   Drift: 1377ms ⚠️ WARNING (> 1000ms threshold)                   │      │
│  │                                                                    │      │
│  └────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  Why Time Drift Matters:                                                      │
│  - Cron schedules depend on accurate time                                    │
│  - Distributed locks use timestamp-based expiry                              │
│  - Misfire detection requires clock synchronization                          │
│  - Audit logs need consistent timestamps                                     │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import socket
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .service import SchedulerService

logger = logging.getLogger(__name__)


# NTP epoch starts on 1900-01-01, Unix epoch on 1970-01-01
NTP_DELTA = 2208988800


@dataclass
class SchedulerHealthReport:
    """Complete scheduler health report."""

    healthy: bool
    checks: dict[str, bool] = field(default_factory=dict)
    backend: dict[str, Any] = field(default_factory=dict)
    schedules: dict[str, int] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "checks": self.checks,
            "backend": self.backend,
            "schedules": self.schedules,
            "timing": self.timing,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def check_scheduler_health(
    service: SchedulerService,
    check_ntp: bool = True,
    drift_threshold_ms: float = 1000.0,
    tick_age_threshold_seconds: float = 60.0,
) -> SchedulerHealthReport:
    """Comprehensive scheduler health check.

    Args:
        service: SchedulerService to check
        check_ntp: Whether to check NTP drift (may be slow)
        drift_threshold_ms: Time drift warning threshold
        tick_age_threshold_seconds: Max age of last tick before warning

    Returns:
        SchedulerHealthReport with all checks
    """
    report = SchedulerHealthReport(healthy=True)
    now = datetime.now(UTC)

    # === Backend Health ===
    try:
        backend_health = service.backend.health()
        report.backend = backend_health
        is_healthy = backend_health.get("healthy", False)
        report.checks["backend_running"] = is_healthy
        if not is_healthy:
            report.healthy = False
            report.errors.append("Backend is not running")
    except Exception as e:
        report.checks["backend_running"] = False
        report.healthy = False
        report.errors.append(f"Backend health check failed: {e}")

    # === Tick Health ===
    stats = service.get_stats()
    last_tick = stats.last_tick

    if last_tick:
        tick_age = (now - last_tick).total_seconds()
        report.timing["last_tick_age_seconds"] = tick_age
        report.timing["last_tick"] = last_tick.isoformat()

        tick_ok = tick_age < tick_age_threshold_seconds
        report.checks["tick_recent"] = tick_ok
        if not tick_ok:
            report.warnings.append(
                f"Last tick was {tick_age:.1f}s ago (threshold: {tick_age_threshold_seconds}s)"
            )
    else:
        report.checks["tick_recent"] = False
        if service.is_running:
            report.warnings.append("No ticks recorded yet")

    report.timing["tick_count"] = stats.tick_count

    # === Schedule Stats ===
    report.schedules["enabled"] = service.repository.count_enabled()
    report.schedules["processed"] = stats.schedules_processed
    report.schedules["skipped"] = stats.schedules_skipped
    report.schedules["failed"] = stats.schedules_failed

    # Check for high failure rate
    total = stats.schedules_processed + stats.schedules_failed
    if total > 10 and stats.schedules_failed / total > 0.1:
        report.warnings.append(
            f"High failure rate: {stats.schedules_failed}/{total} "
            f"({stats.schedules_failed / total * 100:.1f}%)"
        )

    # === Time Drift ===
    if check_ntp:
        try:
            ntp_time = get_ntp_time()
            if ntp_time:
                drift_ms = abs((now - ntp_time).total_seconds() * 1000)
                report.timing["drift_ms"] = drift_ms
                report.timing["ntp_time"] = ntp_time.isoformat()

                drift_ok = drift_ms < drift_threshold_ms
                report.checks["time_drift_ok"] = drift_ok
                if not drift_ok:
                    report.warnings.append(
                        f"Time drift: {drift_ms:.0f}ms (threshold: {drift_threshold_ms}ms)"
                    )
            else:
                report.checks["time_drift_ok"] = True  # Assume OK if NTP unavailable
                report.timing["drift_ms"] = None
        except Exception as e:
            logger.debug(f"NTP check failed: {e}")
            report.timing["drift_ms"] = None
            report.checks["time_drift_ok"] = True  # Assume OK

    # === Lock Health ===
    try:
        active_locks = service.lock_manager.list_active_locks()
        report.schedules["active_locks"] = len(active_locks)
    except Exception as e:
        logger.warning(f"Lock health check failed: {e}")
        report.schedules["active_locks"] = -1

    # === Final Assessment ===
    # Healthy if backend running and no errors
    if report.errors:
        report.healthy = False

    return report


def get_ntp_time(
    ntp_server: str = "pool.ntp.org",
    timeout: float = 2.0,
) -> datetime | None:
    """Get current time from NTP server.

    Uses simple SNTP protocol for quick time check.

    Args:
        ntp_server: NTP server hostname
        timeout: Socket timeout in seconds

    Returns:
        UTC datetime from NTP, or None if unavailable
    """
    try:
        # NTP message format
        msg = b'\x1b' + 47 * b'\0'  # LI=0, VN=3, Mode=3 (client)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        sock.sendto(msg, (ntp_server, 123))
        data, _ = sock.recvfrom(1024)
        sock.close()

        if len(data) < 48:
            return None

        # Extract transmit timestamp (bytes 40-47)
        t = struct.unpack('!12I', data)[10]
        t -= NTP_DELTA

        return datetime.fromtimestamp(t, tz=UTC)

    except (TimeoutError, OSError) as e:
        logger.debug(f"NTP query failed: {e}")
        return None


def check_tick_interval_stability(
    tick_times: list[datetime],
    expected_interval: float = 10.0,
    tolerance: float = 0.5,
) -> dict[str, Any]:
    """Analyze tick interval stability.

    Args:
        tick_times: List of tick timestamps
        expected_interval: Expected interval in seconds
        tolerance: Acceptable deviation as fraction (0.5 = 50%)

    Returns:
        Analysis result with jitter and stability metrics
    """
    if len(tick_times) < 2:
        return {
            "stable": True,
            "samples": len(tick_times),
            "message": "Insufficient data",
        }

    intervals = []
    for i in range(1, len(tick_times)):
        delta = (tick_times[i] - tick_times[i - 1]).total_seconds()
        intervals.append(delta)

    avg = sum(intervals) / len(intervals)
    variance = sum((x - avg) ** 2 for x in intervals) / len(intervals)
    std_dev = variance ** 0.5

    # Jitter as percentage of expected interval
    jitter_pct = (std_dev / expected_interval) * 100

    # Check stability
    max_deviation = max(abs(x - expected_interval) for x in intervals)
    stable = max_deviation <= expected_interval * tolerance

    return {
        "stable": stable,
        "samples": len(intervals),
        "avg_interval": avg,
        "expected_interval": expected_interval,
        "std_dev": std_dev,
        "jitter_pct": jitter_pct,
        "max_deviation": max_deviation,
        "min_interval": min(intervals),
        "max_interval": max(intervals),
    }
