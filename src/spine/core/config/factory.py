"""
Factory functions that create component instances from settings.

Manifesto:
    Each factory uses lazy imports so that optional heavy dependencies
    (``sqlalchemy``, ``redis``, ``celery``, …) are only loaded when the
    corresponding backend is actually selected.  This keeps
    ``import spine.core`` fast and dependency-free.

Features:
    - ``create_database_engine()`` — SQLAlchemy engine from settings
    - ``create_scheduler_backend()`` — Thread / APScheduler / Celery
    - ``create_cache_client()`` — InMemory / Redis cache
    - ``create_worker_executor()`` — Thread / Process / Celery executor
    - ``create_event_bus()`` — InMemory / Redis event bus

Tags:
    spine-core, configuration, factory-pattern, lazy-imports,
    sqlalchemy, redis, celery

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .components import CacheBackend, DatabaseBackend, EventBackend, SchedulerBackend, WorkerBackend

if TYPE_CHECKING:
    from .settings import SpineCoreSettings


def create_database_engine(settings: SpineCoreSettings) -> Any:
    """Create a SQLAlchemy :class:`~sqlalchemy.engine.Engine`.

    Uses *settings.database_backend* to choose connection arguments:
    SQLite gets ``check_same_thread=False``; PostgreSQL / TimescaleDB
    get connection-pool tuning.
    """
    from sqlalchemy import create_engine

    if settings.database_backend == DatabaseBackend.SQLITE:
        return create_engine(
            settings.database_url,
            echo=settings.database_echo,
            connect_args={"check_same_thread": False},
        )
    else:
        return create_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )


def create_scheduler_backend(settings: SpineCoreSettings) -> Any:
    """Create a scheduler backend instance.

    Maps *settings.scheduler_backend* to the matching concrete class
    from :mod:`spine.core.scheduling`.
    """
    match settings.scheduler_backend:
        case SchedulerBackend.THREAD:
            from spine.core.scheduling import ThreadSchedulerBackend

            return ThreadSchedulerBackend()
        case SchedulerBackend.APSCHEDULER:
            from spine.core.scheduling import APSchedulerBackend

            return APSchedulerBackend()
        case SchedulerBackend.CELERY_BEAT:
            # Celery Beat adapter — import may fail if celery is not installed
            try:
                from spine.core.scheduling import CeleryBeatBackend
            except ImportError as exc:
                raise ImportError(
                    "celery_beat scheduler requires the 'celery' package. "
                    "Install with: pip install celery"
                ) from exc
            return CeleryBeatBackend(broker_url=settings.celery_broker_url)


def create_cache_client(settings: SpineCoreSettings) -> Any:
    """Create a cache client based on *settings.cache_backend*."""
    match settings.cache_backend:
        case CacheBackend.NONE:
            return _NullCache()
        case CacheBackend.REDIS:
            try:
                import redis
            except ImportError as exc:
                raise ImportError(
                    "Redis cache requires the 'redis' package. Install with: pip install redis"
                ) from exc
            return redis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
            )
        case CacheBackend.MEMCACHED:
            try:
                from pymemcache.client.base import Client
            except ImportError as exc:
                raise ImportError(
                    "Memcached cache requires 'pymemcache'. Install with: pip install pymemcache"
                ) from exc
            host_port = settings.redis_url.replace("memcached://", "")
            host, _, port = host_port.partition(":")
            return Client((host, int(port) if port else 11211))


def create_worker_executor(settings: SpineCoreSettings) -> Any:
    """Create a task executor based on *settings.worker_backend*.

    Falls back to a simple in-process executor when no external
    worker library is installed.
    """
    match settings.worker_backend:
        case WorkerBackend.INPROCESS:
            return _InProcessExecutor()
        case WorkerBackend.CELERY:
            try:
                from celery import Celery
            except ImportError as exc:
                raise ImportError(
                    "Celery worker requires 'celery'. Install with: pip install celery"
                ) from exc
            return Celery(broker=settings.celery_broker_url, backend=settings.celery_result_backend)
        case WorkerBackend.RQ:
            try:
                import redis as _redis
                from rq import Queue
            except ImportError as exc:
                raise ImportError(
                    "RQ worker requires 'rq' and 'redis'. Install with: pip install rq redis"
                ) from exc
            conn = _redis.from_url(settings.redis_url)
            return Queue(connection=conn)


# ── Lightweight fallback implementations ─────────────────────────────────


class _NullCache:
    """No-op cache that satisfies the cache-client interface."""

    def get(self, key: str) -> None:
        return None

    def set(self, key: str, value: Any, **kwargs: Any) -> bool:
        return True

    def delete(self, key: str) -> bool:
        return True


def create_event_bus(settings: SpineCoreSettings) -> Any:
    """Create an event bus based on *settings.event_backend*.

    Returns an :class:`~spine.core.events.EventBus` implementation.
    """
    match settings.event_backend:
        case EventBackend.NONE:
            return None
        case EventBackend.MEMORY:
            from spine.core.events.memory import InMemoryEventBus

            return InMemoryEventBus()
        case EventBackend.REDIS:
            from spine.core.events.redis import RedisEventBus

            return RedisEventBus(url=settings.event_redis_url)


class _InProcessExecutor:
    """Simple synchronous executor for the ``inprocess`` worker backend."""

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run *fn* synchronously and return its result."""
        return fn(*args, **kwargs)
