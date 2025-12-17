"""Tests for spine.core.config.components — enums and validation."""

from __future__ import annotations

import pytest

from spine.core.config.components import (
    CacheBackend,
    ComponentWarning,
    DatabaseBackend,
    MetricsBackend,
    SchedulerBackend,
    TracingBackend,
    WorkerBackend,
    validate_component_combination,
)


# ── Enum membership ──────────────────────────────────────────────────────


class TestEnums:
    def test_database_backend_values(self):
        assert set(DatabaseBackend) == {DatabaseBackend.SQLITE, DatabaseBackend.POSTGRES, DatabaseBackend.TIMESCALE}

    def test_scheduler_backend_values(self):
        assert set(SchedulerBackend) == {
            SchedulerBackend.THREAD,
            SchedulerBackend.APSCHEDULER,
            SchedulerBackend.CELERY_BEAT,
        }

    def test_cache_backend_values(self):
        assert set(CacheBackend) == {CacheBackend.NONE, CacheBackend.REDIS, CacheBackend.MEMCACHED}

    def test_worker_backend_values(self):
        assert set(WorkerBackend) == {WorkerBackend.INPROCESS, WorkerBackend.CELERY, WorkerBackend.RQ}

    def test_metrics_backend_values(self):
        assert set(MetricsBackend) == {MetricsBackend.NONE, MetricsBackend.PROMETHEUS}

    def test_tracing_backend_values(self):
        assert set(TracingBackend) == {TracingBackend.NONE, TracingBackend.OPENTELEMETRY}

    def test_str_enum_behaviour(self):
        """Enum members are strings for easy serialisation."""
        assert DatabaseBackend.SQLITE == "sqlite"
        assert SchedulerBackend.THREAD == "thread"
        assert str(CacheBackend.REDIS) == "CacheBackend.REDIS"


# ── Component warning dataclass ──────────────────────────────────────────


class TestComponentWarning:
    def test_frozen(self):
        w = ComponentWarning(severity="warning", message="test", suggestion="fix it")
        with pytest.raises(AttributeError):
            w.severity = "error"  # type: ignore[misc]

    def test_fields(self):
        w = ComponentWarning(severity="info", message="hello", suggestion="do X")
        assert w.severity == "info"
        assert w.message == "hello"
        assert w.suggestion == "do X"


# ── Validation: happy paths ─────────────────────────────────────────────


class TestValidationHappy:
    def test_minimal_defaults(self):
        """All defaults (sqlite/thread/none/inprocess) → no warnings."""
        warnings = validate_component_combination()
        assert warnings == []

    def test_standard_combo(self):
        """postgres + apscheduler + inprocess → no warnings."""
        warnings = validate_component_combination(
            database=DatabaseBackend.POSTGRES,
            scheduler=SchedulerBackend.APSCHEDULER,
        )
        assert warnings == []

    def test_full_combo(self):
        """Full tier (timescale/celery_beat/redis/celery/prometheus) → info only."""
        warnings = validate_component_combination(
            database=DatabaseBackend.TIMESCALE,
            scheduler=SchedulerBackend.CELERY_BEAT,
            cache=CacheBackend.REDIS,
            worker=WorkerBackend.CELERY,
            metrics=MetricsBackend.PROMETHEUS,
            tracing=TracingBackend.OPENTELEMETRY,
        )
        # No errors, no warnings — only possible info
        assert all(w.severity in ("info",) for w in warnings) if warnings else True


# ── Validation: warnings ────────────────────────────────────────────────


class TestValidationWarnings:
    def test_sqlite_celery_warning(self):
        """SQLite + Celery workers → WAL-lock warning."""
        warnings = validate_component_combination(
            database=DatabaseBackend.SQLITE,
            worker=WorkerBackend.CELERY,
            cache=CacheBackend.REDIS,  # required for celery
        )
        assert any("WAL-lock" in w.message for w in warnings)

    def test_apscheduler_celery_warning(self):
        """APScheduler + Celery workers → unusual combo warning."""
        warnings = validate_component_combination(
            scheduler=SchedulerBackend.APSCHEDULER,
            worker=WorkerBackend.CELERY,
            cache=CacheBackend.REDIS,
            database=DatabaseBackend.POSTGRES,
        )
        assert any("APScheduler" in w.message for w in warnings)

    def test_timescale_no_prometheus_info(self):
        """TimescaleDB without Prometheus → info suggestion."""
        warnings = validate_component_combination(
            database=DatabaseBackend.TIMESCALE,
        )
        assert any("Prometheus" in w.message for w in warnings)


# ── Validation: errors (ValueError) ────────────────────────────────────


class TestValidationErrors:
    def test_celery_beat_no_redis_raises(self):
        """Celery Beat without Redis → ValueError."""
        with pytest.raises(ValueError, match="Celery Beat"):
            validate_component_combination(
                scheduler=SchedulerBackend.CELERY_BEAT,
                cache=CacheBackend.NONE,
            )

    def test_rq_no_redis_raises(self):
        """RQ workers without Redis → ValueError."""
        with pytest.raises(ValueError, match="RQ workers"):
            validate_component_combination(
                worker=WorkerBackend.RQ,
                cache=CacheBackend.NONE,
            )

    def test_celery_worker_no_redis_raises(self):
        """Celery workers without Redis → ValueError."""
        with pytest.raises(ValueError, match="Celery workers"):
            validate_component_combination(
                worker=WorkerBackend.CELERY,
                cache=CacheBackend.NONE,
            )
