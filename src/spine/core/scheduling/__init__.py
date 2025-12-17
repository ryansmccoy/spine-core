"""Scheduler package for spine-core.

┌──────────────────────────────────────────────────────────────────────────────┐
│  SPINE SCHEDULER - Production-Grade Cron Scheduling                          │
│                                                                               │
│  A full-featured scheduling system with:                                      │
│  - Pluggable timing backends (Thread, APScheduler, Celery Beat)              │
│  - Cron and interval schedule types                                          │
│  - Distributed locks for multi-instance deployments                          │
│  - Misfire detection and grace periods                                       │
│  - Health monitoring and time drift detection                                │
│                                                                               │
│  Quick Start:                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │   from spine.core.scheduling import (                                │   │
│  │       SchedulerService,                                              │   │
│  │       ThreadSchedulerBackend,                                        │   │
│  │       ScheduleRepository,                                            │   │
│  │       LockManager,                                                   │   │
│  │   )                                                                  │   │
│  │                                                                      │   │
│  │   # Create scheduler                                                 │   │
│  │   backend = ThreadSchedulerBackend()                                 │   │
│  │   repo = ScheduleRepository(conn)                                    │   │
│  │   locks = LockManager(conn)                                          │   │
│  │   service = SchedulerService(backend, repo, locks, dispatcher)       │   │
│  │                                                                      │   │
│  │   # Start scheduling                                                 │   │
│  │   service.start()                                                    │   │
│  │                                                                      │   │
│  │   # Create a schedule                                                │   │
│  │   repo.create(ScheduleCreate(                                        │   │
│  │       name="daily-report",                                           │   │
│  │       target_type="workflow",                                        │   │
│  │       target_name="generate-report",                                 │   │
│  │       cron_expression="0 8 * * *",                                   │   │
│  │   ))                                                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  Architecture:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                     │    │
│  │   ┌──────────────┐    tick()    ┌──────────────────────────────┐  │    │
│  │   │  Backend     │ ───────────► │   SchedulerService           │  │    │
│  │   │ (timing)     │              │                              │  │    │
│  │   └──────────────┘              │  ┌──────────┐ ┌───────────┐  │  │    │
│  │                                 │  │ Repo     │ │ LockMgr   │  │  │    │
│  │   Backends:                     │  │ (data)   │ │ (safety)  │  │  │    │
│  │   • Thread (default)            │  └──────────┘ └───────────┘  │  │    │
│  │   • APScheduler                 │              │               │  │    │
│  │   • Celery Beat                 │              ▼               │  │    │
│  │                                 │       ┌──────────────┐       │  │    │
│  │                                 │       │  Dispatcher  │       │  │    │
│  │                                 │       │ (execution)  │       │  │    │
│  │                                 │       └──────────────┘       │  │    │
│  │                                 └──────────────────────────────┘  │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
│  Dependencies:                                                                │
│  - croniter: Cron expression parsing (pip install croniter)                 │
│  - apscheduler: APScheduler backend (optional)                              │
│  - celery: Celery Beat backend (optional)                                   │
│                                                                               │
│  Tables (from 03_scheduler.sql):                                              │
│  - core_schedules: Schedule definitions                                      │
│  - core_schedule_runs: Execution history                                     │
│  - core_schedule_locks: Distributed locks                                    │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

# Protocol
from .protocol import BackendHealth, SchedulerBackend

# Backends
from .thread_backend import ThreadSchedulerBackend

# Optional backends (lazy imports — require extras)
# APSchedulerBackend:  pip install spine-core[apscheduler]
# CeleryBeatBackend:   pip install celery


def __getattr__(name: str):  # noqa: N807
    """Lazy import optional backends to avoid ImportError when extras are missing."""
    if name == "APSchedulerBackend":
        from .apscheduler_backend import APSchedulerBackend

        return APSchedulerBackend
    if name == "CeleryBeatBackend":
        from .celery_backend import CeleryBeatBackend

        return CeleryBeatBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Repository
# Health
from .health import (
    SchedulerHealthReport,
    check_scheduler_health,
    check_tick_interval_stability,
    get_ntp_time,
)

# Lock Manager
from .lock_manager import LockManager
from .repository import (
    ScheduleCreate,
    ScheduleRepository,
    ScheduleRunCreate,
    ScheduleUpdate,
)

# Service
from .service import SchedulerHealth, SchedulerService, SchedulerStats

__all__ = [
    # Protocol
    "SchedulerBackend",
    "BackendHealth",
    # Backends
    "ThreadSchedulerBackend",
    "APSchedulerBackend",
    "CeleryBeatBackend",
    # Repository
    "ScheduleRepository",
    "ScheduleCreate",
    "ScheduleUpdate",
    "ScheduleRunCreate",
    # Lock Manager
    "LockManager",
    # Service
    "SchedulerService",
    "SchedulerStats",
    "SchedulerHealth",
    # Health
    "check_scheduler_health",
    "SchedulerHealthReport",
    "get_ntp_time",
    "check_tick_interval_stability",
]


def create_scheduler(
    conn,
    dispatcher=None,
    interval_seconds: float = 10.0,
    instance_id: str | None = None,
) -> SchedulerService:
    """Factory function to create a complete scheduler service.

    This is the recommended way to create a scheduler with all components
    properly wired together.

    Args:
        conn: Database connection
        dispatcher: EventDispatcher for work execution (optional)
        interval_seconds: Tick interval (default: 10s)
        instance_id: Unique instance ID for distributed locks

    Returns:
        Configured SchedulerService

    Example:
        >>> scheduler = create_scheduler(conn, dispatcher)
        >>> scheduler.start()
    """
    backend = ThreadSchedulerBackend()
    repository = ScheduleRepository(conn)
    lock_manager = LockManager(conn, instance_id=instance_id)

    return SchedulerService(
        backend=backend,
        repository=repository,
        lock_manager=lock_manager,
        dispatcher=dispatcher,
        interval_seconds=interval_seconds,
    )
