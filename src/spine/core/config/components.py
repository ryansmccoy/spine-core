"""
Component backend enumerations and compatibility validation.

Each enum represents a pluggable backend dimension.  The
:func:`validate_component_combination` function checks that a set of
chosen backends is consistent (e.g. Celery-beat requires Redis).

Example::

    from spine.core.config.components import (
        DatabaseBackend, SchedulerBackend, validate_component_combination,
    )

    warnings = validate_component_combination(
        database=DatabaseBackend.SQLITE,
        scheduler=SchedulerBackend.CELERY_BEAT,
    )
    for w in warnings:
        print(w.severity, w.message)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ── Backend enumerations ─────────────────────────────────────────────────


class DatabaseBackend(str, Enum):
    """Supported database backends."""

    SQLITE = "sqlite"
    POSTGRES = "postgres"
    TIMESCALE = "timescale"


class SchedulerBackend(str, Enum):
    """Supported scheduler backends."""

    THREAD = "thread"
    APSCHEDULER = "apscheduler"
    CELERY_BEAT = "celery_beat"


class CacheBackend(str, Enum):
    """Supported cache backends."""

    NONE = "none"
    REDIS = "redis"
    MEMCACHED = "memcached"


class WorkerBackend(str, Enum):
    """Supported task-worker backends."""

    INPROCESS = "inprocess"
    CELERY = "celery"
    RQ = "rq"


class MetricsBackend(str, Enum):
    """Supported metrics backends."""

    NONE = "none"
    PROMETHEUS = "prometheus"


class TracingBackend(str, Enum):
    """Supported distributed-tracing backends."""

    NONE = "none"
    OPENTELEMETRY = "opentelemetry"


class EventBackend(str, Enum):
    """Supported event bus backends."""

    NONE = "none"
    MEMORY = "memory"
    REDIS = "redis"


# ── Compatibility validation ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ComponentWarning:
    """A warning or error raised by component-combination validation."""

    severity: str  # "info", "warning", or "error"
    message: str
    suggestion: str


def validate_component_combination(
    *,
    database: DatabaseBackend = DatabaseBackend.SQLITE,
    scheduler: SchedulerBackend = SchedulerBackend.THREAD,
    cache: CacheBackend = CacheBackend.NONE,
    worker: WorkerBackend = WorkerBackend.INPROCESS,
    metrics: MetricsBackend = MetricsBackend.NONE,
    tracing: TracingBackend = TracingBackend.NONE,
) -> list[ComponentWarning]:
    """Return compatibility warnings for the given backend choices.

    Raises :class:`ValueError` for *error*-severity issues (combinations
    that cannot work at runtime).
    """
    warnings: list[ComponentWarning] = []

    # Rule 1 — SQLite + Celery workers → warning (WAL-lock contention)
    if database == DatabaseBackend.SQLITE and worker == WorkerBackend.CELERY:
        warnings.append(
            ComponentWarning(
                severity="warning",
                message="SQLite with Celery workers may cause WAL-lock contention under write-heavy loads.",
                suggestion="Use PostgreSQL or TimescaleDB for production Celery workloads.",
            )
        )

    # Rule 2 — Celery Beat requires Redis (or similar broker)
    if scheduler == SchedulerBackend.CELERY_BEAT and cache == CacheBackend.NONE:
        raise ValueError(
            "Celery Beat scheduler requires a Redis (or compatible) cache/broker backend. "
            "Set cache_backend='redis' when using scheduler_backend='celery_beat'."
        )

    # Rule 3 — APScheduler + Celery workers → warning
    if scheduler == SchedulerBackend.APSCHEDULER and worker == WorkerBackend.CELERY:
        warnings.append(
            ComponentWarning(
                severity="warning",
                message="APScheduler with Celery workers is unusual. Consider celery_beat for native Celery scheduling.",
                suggestion="Switch scheduler_backend to 'celery_beat' when using Celery workers.",
            )
        )

    # Rule 4 — TimescaleDB implies postgres driver needed
    if database == DatabaseBackend.TIMESCALE and metrics == MetricsBackend.NONE:
        warnings.append(
            ComponentWarning(
                severity="info",
                message="TimescaleDB is optimised for time-series metrics. Consider enabling Prometheus.",
                suggestion="Set metrics_backend='prometheus' to take full advantage of TimescaleDB.",
            )
        )

    # Rule 5 — RQ workers require Redis
    if worker == WorkerBackend.RQ and cache == CacheBackend.NONE:
        raise ValueError(
            "RQ workers require a Redis backend. "
            "Set cache_backend='redis' when using worker_backend='rq'."
        )

    # Rule 6 — Celery workers require Redis (broker)
    if worker == WorkerBackend.CELERY and cache == CacheBackend.NONE:
        raise ValueError(
            "Celery workers require a Redis (or compatible) broker. "
            "Set cache_backend='redis' when using worker_backend='celery'."
        )

    return warnings
