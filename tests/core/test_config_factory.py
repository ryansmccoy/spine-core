"""Tests for spine.core.config.factory — component factory functions.

Mocks heavy dependencies (sqlalchemy, redis, celery) to test factory
logic without requiring those packages at runtime.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from spine.core.config.components import (
    CacheBackend,
    DatabaseBackend,
    EventBackend,
    SchedulerBackend,
    WorkerBackend,
)


def _settings(**overrides) -> SimpleNamespace:
    """Create a minimal settings-like object."""
    defaults = dict(
        database_url="sqlite:///test.db",
        database_backend=DatabaseBackend.SQLITE,
        database_echo=False,
        database_pool_size=5,
        database_max_overflow=10,
        scheduler_backend=SchedulerBackend.THREAD,
        cache_backend=CacheBackend.NONE,
        worker_backend=WorkerBackend.INPROCESS,
        event_backend=EventBackend.MEMORY,
        redis_url="redis://localhost:6379",
        redis_max_connections=10,
        event_redis_url="redis://localhost:6379/1",
        celery_broker_url="redis://localhost:6379/0",
        celery_result_backend="redis://localhost:6379/1",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestCreateDatabaseEngine:
    @patch("sqlalchemy.create_engine")
    def test_sqlite_backend(self, mock_create):
        from spine.core.config.factory import create_database_engine

        s = _settings(database_backend=DatabaseBackend.SQLITE)
        create_database_engine(s)
        mock_create.assert_called_once()
        kwargs = mock_create.call_args
        assert kwargs.kwargs.get("connect_args") == {"check_same_thread": False}

    @patch("sqlalchemy.create_engine")
    def test_postgres_backend(self, mock_create):
        from spine.core.config.factory import create_database_engine

        s = _settings(
            database_backend=DatabaseBackend.POSTGRES,
            database_url="postgresql://localhost/test",
        )
        create_database_engine(s)
        kwargs = mock_create.call_args
        assert kwargs.kwargs.get("pool_size") == 5


class TestCreateSchedulerBackend:
    def test_thread_scheduler(self):
        from spine.core.config.factory import create_scheduler_backend

        s = _settings(scheduler_backend=SchedulerBackend.THREAD)
        backend = create_scheduler_backend(s)
        assert backend is not None

    def test_apscheduler_backend(self):
        pytest.importorskip("apscheduler", reason="APScheduler not installed")
        from spine.core.config.factory import create_scheduler_backend

        s = _settings(scheduler_backend=SchedulerBackend.APSCHEDULER)
        backend = create_scheduler_backend(s)
        assert backend is not None


class TestCreateCacheClient:
    def test_none_cache(self):
        from spine.core.config.factory import create_cache_client

        s = _settings(cache_backend=CacheBackend.NONE)
        client = create_cache_client(s)
        # NullCache always returns None for get, True for set/delete
        assert client.get("any") is None
        assert client.set("k", "v") is True
        assert client.delete("k") is True


class TestCreateWorkerExecutor:
    def test_inprocess_executor(self):
        from spine.core.config.factory import create_worker_executor

        s = _settings(worker_backend=WorkerBackend.INPROCESS)
        executor = create_worker_executor(s)
        # _InProcessExecutor.submit runs fn synchronously
        result = executor.submit(lambda x: x * 2, 5)
        assert result == 10


class TestCreateEventBus:
    def test_none_backend(self):
        from spine.core.config.factory import create_event_bus

        s = _settings(event_backend=EventBackend.NONE)
        assert create_event_bus(s) is None

    def test_memory_backend(self):
        from spine.core.config.factory import create_event_bus

        s = _settings(event_backend=EventBackend.MEMORY)
        bus = create_event_bus(s)
        assert bus is not None
