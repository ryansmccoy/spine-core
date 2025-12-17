"""APScheduler-based scheduler backend.

Wraps APScheduler 3.x ``BackgroundScheduler`` to provide the
``SchedulerBackend`` protocol for production deployments that need
richer job-store features (database-backed job persistence, misfire
handling, etc.).

Requires the ``[apscheduler]`` extra::

    pip install spine-core[apscheduler]

.. note::

    For most use cases the zero-dependency ``ThreadSchedulerBackend``
    is sufficient.  Use this backend when you need APScheduler-specific
    capabilities like job stores or advanced misfire policies.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from .protocol import TickCallback

logger = logging.getLogger(__name__)


def _require_apscheduler():
    """Validate that apscheduler is installed."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: F401

        return BackgroundScheduler
    except ImportError:
        raise ImportError(
            "APScheduler is required for APSchedulerBackend. "
            "Install it with: pip install spine-core[apscheduler]"
        ) from None


class APSchedulerBackend:
    """APScheduler-based scheduler backend.

    Implements the ``SchedulerBackend`` protocol using APScheduler 3.x
    ``BackgroundScheduler``.  The scheduler runs an interval job that
    invokes the tick callback at the configured frequency.

    Example::

        >>> backend = APSchedulerBackend()
        >>> backend.start(tick_callback, interval_seconds=10.0)
        >>> # … later …
        >>> backend.stop()
    """

    name: str = "apscheduler"

    def __init__(self) -> None:
        BackgroundScheduler = _require_apscheduler()  # noqa: N806
        self._scheduler = BackgroundScheduler()
        self._tick_count: int = 0
        self._last_tick: datetime | None = None
        self._callback: TickCallback | None = None

    # ------------------------------------------------------------------
    # SchedulerBackend protocol
    # ------------------------------------------------------------------

    def start(
        self,
        tick_callback: TickCallback,
        interval_seconds: float = 10.0,
    ) -> None:
        """Start the APScheduler loop.

        Registers an interval job that calls *tick_callback* every
        *interval_seconds*.

        Args:
            tick_callback: Async function called on each tick.
            interval_seconds: How often to tick (default: 10 s).
        """
        self._callback = tick_callback

        def _tick_wrapper() -> None:
            self._tick_count += 1
            self._last_tick = datetime.now(UTC)
            try:
                asyncio.run(tick_callback())
            except Exception:
                logger.exception("APScheduler tick failed")

        self._scheduler.add_job(
            _tick_wrapper,
            "interval",
            seconds=interval_seconds,
            id="spine_scheduler_tick",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "APSchedulerBackend started (interval=%.1fs)", interval_seconds
        )

    def stop(self) -> None:
        """Stop the APScheduler loop gracefully.

        Waits for the current tick to finish before returning.
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("APSchedulerBackend stopped")

    def health(self) -> dict[str, Any]:
        """Return backend health status.

        Returns:
            dict with healthy, backend, tick_count, last_tick, and
            scheduled_jobs count.
        """
        running = self._scheduler.running if hasattr(self._scheduler, "running") else False
        return {
            "healthy": running,
            "backend": self.name,
            "tick_count": self._tick_count,
            "last_tick": self._last_tick.isoformat() if self._last_tick else None,
            "scheduled_jobs": len(self._scheduler.get_jobs()) if running else 0,
        }
