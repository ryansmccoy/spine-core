"""Tests for spine.core.config.factory and container."""

from __future__ import annotations

import pytest

from spine.core.config.components import CacheBackend, DatabaseBackend, SchedulerBackend, WorkerBackend
from spine.core.config.container import SpineContainer, get_container
from spine.core.config.factory import (
    _InProcessExecutor,
    _NullCache,
    create_cache_client,
    create_database_engine,
    create_worker_executor,
)
from spine.core.config.settings import SpineCoreSettings, clear_settings_cache


@pytest.fixture(autouse=True)
def _clean():
    clear_settings_cache()
    yield
    clear_settings_cache()
    # Reset global container
    import spine.core.config.container as _mod
    _mod._global_container = None


# ── NullCache ────────────────────────────────────────────────────────────


class TestNullCache:
    def test_get_returns_none(self):
        c = _NullCache()
        assert c.get("any") is None

    def test_set_returns_true(self):
        c = _NullCache()
        assert c.set("k", "v") is True

    def test_delete_returns_true(self):
        c = _NullCache()
        assert c.delete("k") is True


# ── InProcessExecutor ────────────────────────────────────────────────────


class TestInProcessExecutor:
    def test_submit_runs_synchronously(self):
        executor = _InProcessExecutor()
        result = executor.submit(lambda x: x * 2, 5)
        assert result == 10


# ── Factory functions ────────────────────────────────────────────────────


class TestCreateDatabaseEngine:
    def test_sqlite_engine(self):
        settings = SpineCoreSettings(database_backend=DatabaseBackend.SQLITE, database_url="sqlite:///:memory:")
        engine = create_database_engine(settings)
        assert engine is not None
        assert "sqlite" in str(engine.url)
        engine.dispose()

    def test_sqlite_check_same_thread(self):
        settings = SpineCoreSettings(database_backend=DatabaseBackend.SQLITE, database_url="sqlite:///:memory:")
        engine = create_database_engine(settings)
        # Verify the engine was created (check_same_thread is internal)
        assert engine is not None
        engine.dispose()


class TestCreateCacheClient:
    def test_none_returns_null_cache(self):
        settings = SpineCoreSettings(cache_backend=CacheBackend.NONE)
        client = create_cache_client(settings)
        assert isinstance(client, _NullCache)

    def test_redis_import_error(self, monkeypatch: pytest.MonkeyPatch):
        """Redis client requires redis package."""
        settings = SpineCoreSettings(
            cache_backend=CacheBackend.REDIS,
            worker_backend=WorkerBackend.INPROCESS,
        )
        # We can only test that it either works (redis installed) or raises ImportError
        try:
            client = create_cache_client(settings)
            assert client is not None
        except ImportError:
            pass  # Expected if redis not installed


class TestCreateWorkerExecutor:
    def test_inprocess_executor(self):
        settings = SpineCoreSettings(worker_backend=WorkerBackend.INPROCESS)
        executor = create_worker_executor(settings)
        assert isinstance(executor, _InProcessExecutor)

    def test_celery_import_error(self):
        """Celery executor requires celery package."""
        settings = SpineCoreSettings(
            worker_backend=WorkerBackend.CELERY,
            cache_backend=CacheBackend.REDIS,
        )
        try:
            executor = create_worker_executor(settings)
            assert executor is not None
        except ImportError:
            pass  # Expected if celery not installed


# ── SpineContainer ───────────────────────────────────────────────────────


class TestSpineContainer:
    def test_lazy_settings(self):
        container = SpineContainer()
        assert container._settings is None
        _ = container.settings
        assert container._settings is not None

    def test_explicit_settings(self):
        settings = SpineCoreSettings()
        container = SpineContainer(settings)
        assert container.settings is settings

    def test_cache_property(self):
        container = SpineContainer(SpineCoreSettings())
        cache = container.cache
        assert isinstance(cache, _NullCache)

    def test_executor_property(self):
        container = SpineContainer(SpineCoreSettings())
        executor = container.executor
        assert isinstance(executor, _InProcessExecutor)

    def test_close(self):
        container = SpineContainer(SpineCoreSettings())
        _ = container.cache
        container.close()  # Should not raise

    def test_context_manager(self):
        with SpineContainer(SpineCoreSettings()) as c:
            assert isinstance(c.cache, _NullCache)
        # After exit, close is called


class TestGetContainer:
    def test_singleton(self):
        c1 = get_container()
        c2 = get_container()
        assert c1 is c2
