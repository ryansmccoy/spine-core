"""Zero-dependency threading-based scheduler backend.

This is the DEFAULT backend for spine-core scheduling. It uses Python's
stdlib threading module and has no external dependencies.

┌──────────────────────────────────────────────────────────────────────────────┐
│  THREAD BACKEND ARCHITECTURE                                                  │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐      │
│  │                    ThreadSchedulerBackend                          │      │
│  │                                                                    │      │
│  │   start()                                                          │      │
│  │      │                                                             │      │
│  │      ▼                                                             │      │
│  │   ┌─────────────────────────────────────────────────────────┐     │      │
│  │   │              Daemon Thread (loop)                       │     │      │
│  │   │                                                         │     │      │
│  │   │   while not stop_event.wait(interval):                  │     │      │
│  │   │       tick_count += 1                                   │     │      │
│  │   │       last_tick = now()                                 │     │      │
│  │   │       asyncio.run(tick_callback())  ◄─────── Invoke     │     │      │
│  │   │                                                         │     │      │
│  │   └─────────────────────────────────────────────────────────┘     │      │
│  │                                                                    │      │
│  │   stop()                                                           │      │
│  │      │                                                             │      │
│  │      ▼                                                             │      │
│  │   stop_event.set()                                                 │      │
│  │   thread.join(timeout=5.0)                                         │      │
│  │                                                                    │      │
│  └────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  Key Design Decisions:                                                        │
│  1. Daemon thread — doesn't block process exit                               │
│  2. Event-based stop — graceful shutdown                                     │
│  3. asyncio.run per tick — keeps callback async-compatible                   │
│  4. Tick counting — observable scheduling health                             │
│                                                                               │
│  Why NOT asyncio.sleep in main loop?                                         │
│  - SchedulerService might be used in sync contexts                           │
│  - Threading is simpler for this use case                                    │
│  - APScheduler/Celery backends are inherently sync anyway                    │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from .protocol import BackendHealth, TickCallback

logger = logging.getLogger(__name__)


class ThreadSchedulerBackend:
    """Zero-dependency threading-based scheduler backend.

    This is the default backend for local/single-instance deployments.
    Uses Python's stdlib threading module.

    Example:
        >>> backend = ThreadSchedulerBackend()
        >>>
        >>> async def my_tick():
        ...     print("Tick!")
        ...
        >>> backend.start(my_tick, interval_seconds=5.0)
        >>> # ... later ...
        >>> backend.stop()
    """

    name = "thread"

    def __init__(self) -> None:
        """Initialize thread backend."""
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick_count = 0
        self._last_tick: datetime | None = None
        self._interval: float = 10.0
        self._started = False
        self._lock = threading.Lock()

    def start(
        self,
        tick_callback: TickCallback,
        interval_seconds: float = 10.0,
    ) -> None:
        """Start the scheduler loop in a daemon thread.

        Args:
            tick_callback: Async function to call on each tick.
            interval_seconds: How often to tick (default: 10s).
        """
        if self._started:
            logger.warning("ThreadSchedulerBackend already started")
            return

        self._interval = interval_seconds
        self._stop_event.clear()

        def _loop() -> None:
            logger.info(
                f"ThreadSchedulerBackend started (interval={interval_seconds}s)"
            )
            while not self._stop_event.wait(interval_seconds):
                with self._lock:
                    self._tick_count += 1
                    self._last_tick = datetime.now(UTC)

                try:
                    asyncio.run(tick_callback())
                except Exception as e:
                    logger.exception(f"Tick failed: {e}")

            logger.info("ThreadSchedulerBackend stopped")

        self._thread = threading.Thread(target=_loop, daemon=True, name="spine-scheduler")
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        """Stop the scheduler loop gracefully.

        Waits up to 5 seconds for the current tick to complete.
        """
        if not self._started:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("Scheduler thread did not stop cleanly")

        self._started = False
        logger.info("ThreadSchedulerBackend shutdown complete")

    def health(self) -> dict[str, Any]:
        """Return backend health status.

        Returns:
            dict with healthy, backend, tick_count, last_tick
        """
        return {
            "healthy": self._started and self._thread is not None and self._thread.is_alive(),
            "backend": self.name,
            "tick_count": self._tick_count,
            "last_tick": self._last_tick.isoformat() if self._last_tick else None,
            "interval_seconds": self._interval,
        }

    def get_health(self) -> BackendHealth:
        """Return structured health status."""
        return BackendHealth(
            healthy=self._started and self._thread is not None and self._thread.is_alive(),
            backend=self.name,
            tick_count=self._tick_count,
            last_tick=self._last_tick,
            extra={"interval_seconds": self._interval},
        )

    @property
    def is_running(self) -> bool:
        """Check if backend is currently running."""
        return self._started and self._thread is not None and self._thread.is_alive()

    @property
    def tick_count(self) -> int:
        """Get number of ticks executed."""
        return self._tick_count

    @property
    def last_tick(self) -> datetime | None:
        """Get timestamp of last tick."""
        return self._last_tick
