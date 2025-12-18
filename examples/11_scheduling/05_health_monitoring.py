#!/usr/bin/env python3
"""Health Monitoring — NTP drift detection and tick interval stability analysis.

WHY SCHEDULER HEALTH MONITORING
───────────────────────────────
A scheduler that ticks too fast wastes resources; one that ticks too slow
misses deadlines.  Clock drift (especially in containers) can cause
schedules to fire at wrong times.  The health subsystem detects both
problems before they affect business outcomes.

ARCHITECTURE
────────────
    SchedulerService.health()
         │
         ├─▶ BackendHealth          ─ is the timer running?
         ├─▶ check_ntp_drift()      ─ system clock vs NTP
         └─▶ check_tick_stability() ─ are ticks evenly spaced?
              │
              ▼
         SchedulerHealthReport
           .backend_health    ─ healthy / degraded / unhealthy
           .ntp_drift_ms      ─ clock offset in milliseconds
           .tick_stability    ─ coefficient of variation
           .recommendations   ─ human-readable actions

HEALTH THRESHOLDS
─────────────────
    Metric             Healthy      Degraded     Unhealthy
    ────────────────── ──────────── ──────────── ─────────────
    NTP drift          < 100ms      < 500ms      >= 500ms
    Tick coefficient   < 0.1        < 0.3        >= 0.3
    Missed ticks       0            1-2          3+

BEST PRACTICES
──────────────
• Log SchedulerHealthReport on every tick in production.
• Alert on degraded before it becomes unhealthy.
• In containers, enable NTP sync (chrony or systemd-timesyncd).
• If tick stability degrades, increase the tick interval.

Run: python examples/11_scheduling/05_health_monitoring.py

See Also:
    04_scheduler_service — the service that emits health reports
    10_operations/04_health_and_capabilities — aggregate health checks
    01_backend_basics — backend health protocol
"""

from datetime import UTC, datetime, timedelta

from spine.core.scheduling.health import (
    SchedulerHealthReport,
    check_tick_interval_stability,
)


def main():
    print("=" * 60)
    print("Scheduling — Health Monitoring")
    print("=" * 60)

    # --- 1. SchedulerHealthReport structure -------------------------------
    print("\n[1] SchedulerHealthReport Structure")

    report = SchedulerHealthReport(
        healthy=True,
        checks={
            "backend_running": True,
            "tick_recent": True,
            "time_drift_ok": True,
        },
        backend={"name": "thread", "healthy": True, "tick_count": 42},
        schedules={"enabled": 5, "processed": 120, "failed": 2},
        timing={"last_tick_age_seconds": 3.2, "tick_count": 42},
        warnings=["High failure rate: 2/122 (1.6%)"],
    )

    print(f"  healthy   : {report.healthy}")
    print(f"  checks    : {report.checks}")
    print(f"  schedules : {report.schedules}")
    print(f"  warnings  : {report.warnings}")
    print(f"  errors    : {report.errors}")

    d = report.to_dict()
    print(f"  to_dict() keys: {sorted(d.keys())}")

    # --- 2. Tick interval stability — stable case -------------------------
    print("\n[2] Tick Stability — Stable Ticks (10s interval)")

    now = datetime.now(UTC)
    stable_ticks = [
        now + timedelta(seconds=i * 10)
        for i in range(10)
    ]

    result = check_tick_interval_stability(stable_ticks, expected_interval=10.0)
    print(f"  stable       : {result['stable']}")
    print(f"  samples      : {result['samples']}")
    print(f"  avg_interval : {result['avg_interval']:.2f}s")
    print(f"  std_dev      : {result['std_dev']:.4f}")
    print(f"  jitter_pct   : {result['jitter_pct']:.2f}%")

    # --- 3. Tick interval stability — unstable case -----------------------
    print("\n[3] Tick Stability — Jittery Ticks")

    jittery_ticks = [
        now,
        now + timedelta(seconds=5),    # 5s (too fast)
        now + timedelta(seconds=25),   # 20s (too slow)
        now + timedelta(seconds=35),   # 10s (ok)
        now + timedelta(seconds=38),   # 3s  (way too fast)
        now + timedelta(seconds=50),   # 12s (ok-ish)
    ]

    result = check_tick_interval_stability(jittery_ticks, expected_interval=10.0)
    print(f"  stable       : {result['stable']}")
    print(f"  samples      : {result['samples']}")
    print(f"  avg_interval : {result['avg_interval']:.2f}s")
    print(f"  std_dev      : {result['std_dev']:.2f}")
    print(f"  jitter_pct   : {result['jitter_pct']:.1f}%")
    print(f"  min_interval : {result['min_interval']:.1f}s")
    print(f"  max_interval : {result['max_interval']:.1f}s")
    print(f"  max_deviation: {result['max_deviation']:.1f}s")

    # --- 4. Insufficient data edge case -----------------------------------
    print("\n[4] Edge Case — Insufficient Data")

    single = check_tick_interval_stability([now])
    print(f"  1 sample   : stable={single['stable']}, msg='{single.get('message', '')}'")

    empty = check_tick_interval_stability([])
    print(f"  0 samples  : stable={empty['stable']}, msg='{empty.get('message', '')}'")

    # --- 5. Simulating a health report with issues ------------------------
    print("\n[5] Unhealthy Report Example")

    bad_report = SchedulerHealthReport(
        healthy=False,
        checks={
            "backend_running": False,
            "tick_recent": False,
            "time_drift_ok": True,
        },
        errors=["Backend is not running"],
        warnings=[
            "Last tick was 120.5s ago (threshold: 60s)",
            "High failure rate: 15/30 (50.0%)",
        ],
    )

    print(f"  healthy  : {bad_report.healthy}")
    print(f"  errors   : {bad_report.errors}")
    print(f"  warnings :")
    for w in bad_report.warnings:
        print(f"    ⚠ {w}")

    print("\n✓ Health monitoring complete.")


if __name__ == "__main__":
    main()
