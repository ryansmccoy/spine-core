"""Celery Beat scheduler backend (experimental).

Wraps Celery Beat periodic task scheduling to provide the
``SchedulerBackend`` protocol.  This is intended for deployments that
already use Celery as a task broker and want the scheduler tick to be
driven by Celery Beat rather than a local thread or APScheduler.

Requires a Celery application instance and the ``celery`` package::

    pip install celery

.. warning::

    This backend is **experimental**.  Celery Beat integration requires
    a running Celery worker and Beat process.  The ``start()`` method
    only *registers* the periodic task — it does **not** start Beat.
    You must run ``celery -A <app> beat`` separately.

Architecture
~~~~~~~~~~~~

Unlike ``ThreadSchedulerBackend`` and ``APSchedulerBackend`` which
control their own timing loop, ``CeleryBeatBackend`` delegates timing
to the Celery Beat process.  The tick callback is wrapped in a Celery
task and scheduled via the Beat configuration.

::

    ┌──────────────┐   beat_schedule   ┌──────────────┐
    │ Celery Beat  │ ───────────────► │ Celery Worker│
    │ (timing)     │                  │ (execution)  │
    └──────────────┘                  └──────┬───────┘
                                             │
                                      tick_callback()
                                             │
                                      ┌──────▼───────┐
                                      │  Scheduler   │
                                      │  Service     │
                                      └──────────────┘
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from .protocol import TickCallback

logger = logging.getLogger(__name__)


def _require_celery():
    """Validate that celery is installed."""
    try:
        import celery  # noqa: F401

        return celery
    except ImportError:
        raise ImportError(
            "Celery is required for CeleryBeatBackend. "
            "Install it with: pip install celery"
        ) from None


class CeleryBeatBackend:
    """Celery Beat scheduler backend (experimental).

    Implements the ``SchedulerBackend`` protocol by registering a
    periodic task in the Celery Beat schedule.

    .. warning::

        This backend requires an external Celery Beat process to be
        running.  ``start()`` only registers the task in the schedule —
        it does **not** launch Beat.

    Example::

        >>> from celery import Celery
        >>> app = Celery("spine", broker="redis://localhost:6379/0")
        >>> backend = CeleryBeatBackend(celery_app=app)
        >>> backend.start(tick_callback, interval_seconds=10.0)
        >>> # Run separately: celery -A spine beat --loglevel=info
    """

    name: str = "celery_beat"

    def __init__(self, celery_app: Any = None) -> None:
        _require_celery()
        if celery_app is None:
            raise ValueError(
                "CeleryBeatBackend requires a Celery app instance. "
                "Pass celery_app=<your Celery app>."
            )
        self._celery = celery_app
        self._tick_count: int = 0
        self._last_tick: datetime | None = None
        self._callback: TickCallback | None = None
        self._running: bool = False
        self._task_name: str = "spine.scheduling.tick"

    # ------------------------------------------------------------------
    # SchedulerBackend protocol
    # ------------------------------------------------------------------

    def start(
        self,
        tick_callback: TickCallback,
        interval_seconds: float = 10.0,
    ) -> None:
        """Register the tick callback as a Celery Beat periodic task.

        .. note::

            This does NOT start Celery Beat.  You must run the Beat
            process separately.

        Args:
            tick_callback: Async function called on each tick.
            interval_seconds: How often to tick (default: 10 s).
        """
        self._callback = tick_callback

        # Register the tick task with Celery
        @self._celery.task(name=self._task_name, bind=False)
        def spine_tick_task() -> None:
            self._tick_count += 1
            self._last_tick = datetime.now(UTC)
            try:
                asyncio.run(tick_callback())
            except Exception:
                logger.exception("Celery Beat tick failed")

        # Add to Beat schedule
        self._celery.conf.beat_schedule = getattr(
            self._celery.conf, "beat_schedule", {}
        )
        self._celery.conf.beat_schedule["spine_scheduler_tick"] = {
            "task": self._task_name,
            "schedule": interval_seconds,
        }

        self._running = True
        logger.info(
            "CeleryBeatBackend registered tick task (interval=%.1fs). "
            "Ensure Celery Beat is running.",
            interval_seconds,
        )

    def stop(self) -> None:
        """Unregister the tick task from Celery Beat schedule.

        Note: This does NOT stop the Celery Beat process.
        """
        beat_schedule = getattr(self._celery.conf, "beat_schedule", {})
        beat_schedule.pop("spine_scheduler_tick", None)
        self._running = False
        logger.info("CeleryBeatBackend unregistered tick task")

    def health(self) -> dict[str, Any]:
        """Return backend health status.

        Returns:
            dict with healthy flag, tick_count, last_tick, and
            whether the task is registered in the Beat schedule.
        """
        beat_schedule = getattr(self._celery.conf, "beat_schedule", {})
        task_registered = "spine_scheduler_tick" in beat_schedule

        return {
            "healthy": self._running and task_registered,
            "backend": self.name,
            "tick_count": self._tick_count,
            "last_tick": self._last_tick.isoformat() if self._last_tick else None,
            "task_registered": task_registered,
            "experimental": True,
        }
