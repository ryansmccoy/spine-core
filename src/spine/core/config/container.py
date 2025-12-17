"""
Lazy-initialised dependency-injection container.

:class:`SpineContainer` holds references to the major backend
components (database engine, scheduler, cache, worker executor) and
creates them on first access using the factory functions.

Usage::

    from spine.core.config import SpineContainer

    container = SpineContainer()
    engine    = container.engine       # lazy-created
    scheduler = container.scheduler    # same pattern

    # Or initialise with explicit settings:
    container = SpineContainer(get_settings(tier="full"))

    # As a context manager for automatic cleanup:
    with SpineContainer() as c:
        c.engine.execute(...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .factory import (
    create_cache_client,
    create_database_engine,
    create_event_bus,
    create_scheduler_backend,
    create_worker_executor,
)
from .settings import SpineCoreSettings, get_settings

if TYPE_CHECKING:
    pass


class SpineContainer:
    """Lazy-initialised dependency container.

    Components are created on first property access and disposed via
    :meth:`close` (or the context-manager protocol).
    """

    def __init__(self, settings: SpineCoreSettings | None = None) -> None:
        self._settings = settings
        self._engine: Any | None = None
        self._scheduler: Any | None = None
        self._cache: Any | None = None
        self._executor: Any | None = None
        self._event_bus: Any | None = None

    # ── Properties (lazy) ────────────────────────────────────────

    @property
    def settings(self) -> SpineCoreSettings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @property
    def engine(self) -> Any:
        """SQLAlchemy :class:`~sqlalchemy.engine.Engine`."""
        if self._engine is None:
            self._engine = create_database_engine(self.settings)
        return self._engine

    @property
    def scheduler(self) -> Any:
        """Scheduler backend instance."""
        if self._scheduler is None:
            self._scheduler = create_scheduler_backend(self.settings)
        return self._scheduler

    @property
    def cache(self) -> Any:
        """Cache client (Redis, Memcached, or NullCache)."""
        if self._cache is None:
            self._cache = create_cache_client(self.settings)
        return self._cache

    @property
    def executor(self) -> Any:
        """Worker / task executor."""
        if self._executor is None:
            self._executor = create_worker_executor(self.settings)
        return self._executor

    @property
    def event_bus(self) -> Any:
        """Event bus (in-memory, Redis, or None)."""
        if self._event_bus is None:
            self._event_bus = create_event_bus(self.settings)
            # Also register as global singleton so get_event_bus() returns it
            if self._event_bus is not None:
                from spine.core.events import set_event_bus
                set_event_bus(self._event_bus)
        return self._event_bus

    # ── Lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        """Dispose of managed resources."""
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception:
                pass
        if self._scheduler is not None:
            if hasattr(self._scheduler, "stop"):
                try:
                    self._scheduler.stop()
                except Exception:
                    pass
        if self._event_bus is not None:
            if hasattr(self._event_bus, "close"):
                import asyncio
                import logging
                try:
                    asyncio.run(self._event_bus.close())
                except RuntimeError:
                    # Already inside a running loop — schedule gracefully
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._event_bus.close())
                    except RuntimeError:
                        pass  # No running loop and asyncio.run failed — give up
                except Exception:
                    logging.getLogger(__name__).debug(
                        "Failed to close event bus during container shutdown", exc_info=True
                    )

    def __enter__(self) -> SpineContainer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ── Global convenience ───────────────────────────────────────────────────

_global_container: SpineContainer | None = None


def get_container() -> SpineContainer:
    """Get (or create) a module-level :class:`SpineContainer`."""
    global _global_container
    if _global_container is None:
        _global_container = SpineContainer()
    return _global_container
