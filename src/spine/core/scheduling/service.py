"""Scheduler service - main orchestrator.

Manifesto:
    The SchedulerService is the central coordinator that combines backend
    (timing), repository (data), lock manager (safety), and dispatcher
    (execution) into a unified scheduling system.  The beat-as-poller
    pattern decouples timing from schedule evaluation for testability.

The SchedulerService is the central coordinator for schedule execution.
It combines backend (timing), repository (data), lock manager (safety),
and dispatcher (execution) into a unified scheduling system.

Tags:
    spine-core, scheduling, orchestrator, beat-as-poller, service

Doc-Types:
    api-reference, architecture-diagram


┌──────────────────────────────────────────────────────────────────────────────┐
│  SCHEDULER SERVICE ARCHITECTURE                                               │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐      │
│  │                    SchedulerService                                │      │
│  │                                                                    │      │
│  │   Dependencies:                                                    │      │
│  │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │      │
│  │   │  Backend        │  │  Repository     │  │  LockManager    │  │      │
│  │   │  (timing)       │  │  (data)         │  │  (safety)       │  │      │
│  │   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │      │
│  │            │                    │                    │           │      │
│  │            ▼                    ▼                    ▼           │      │
│  │   ┌────────────────────────────────────────────────────────────┐ │      │
│  │   │                       _tick()                              │ │      │
│  │   │                                                            │ │      │
│  │   │   1. cleanup_expired_locks()                               │ │      │
│  │   │   2. get_due_schedules(now)                                │ │      │
│  │   │   3. for each due schedule:                                │ │      │
│  │   │      ├── acquire_schedule_lock()                           │ │      │
│  │   │      ├── _dispatch(schedule)  ──► dispatcher.submit()      │ │      │
│  │   │      ├── mark_run_completed()                              │ │      │
│  │   │      └── release_schedule_lock()                           │ │      │
│  │   └────────────────────────────────────────────────────────────┘ │      │
│  │                                                                    │      │
│  │   Public API:                                                      │      │
│  │   ├── start()          Start scheduler loop                       │      │
│  │   ├── stop()           Stop scheduler gracefully                  │      │
│  │   ├── trigger(name)    Manual trigger of schedule                 │      │
│  │   └── health()         Get service health status                  │      │
│  │                                                                    │      │
│  └────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  Beat-as-Poller Pattern:                                                      │
│  - Backend ticks at fixed interval (e.g., 10s)                               │
│  - Each tick, service queries repository for due schedules                   │
│  - This decouples timing backend from schedule evaluation                    │
│  - Enables easy testing with mock ticks                                      │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .lock_manager import LockManager
from .protocol import BackendHealth, SchedulerBackend
from .repository import ScheduleRepository

if TYPE_CHECKING:
    from spine.core.models.scheduler import Schedule
    from spine.execution.dispatcher import EventDispatcher

logger = logging.getLogger(__name__)


@dataclass
class SchedulerStats:
    """Statistics for scheduler service."""

    tick_count: int = 0
    schedules_processed: int = 0
    schedules_skipped: int = 0
    schedules_failed: int = 0
    last_tick: datetime | None = None
    last_error: str | None = None


@dataclass
class SchedulerHealth:
    """Health status for scheduler service."""

    healthy: bool
    backend: BackendHealth | dict
    schedules_enabled: int = 0
    active_locks: int = 0
    last_tick: datetime | None = None
    drift_ms: float | None = None
    drift_warning: bool = False
    stats: SchedulerStats = field(default_factory=SchedulerStats)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "backend": self.backend.to_dict() if isinstance(self.backend, BackendHealth) else self.backend,
            "schedules_enabled": self.schedules_enabled,
            "active_locks": self.active_locks,
            "last_tick": self.last_tick.isoformat() if self.last_tick else None,
            "drift_ms": self.drift_ms,
            "drift_warning": self.drift_warning,
            "stats": {
                "tick_count": self.stats.tick_count,
                "schedules_processed": self.stats.schedules_processed,
                "schedules_skipped": self.stats.schedules_skipped,
                "schedules_failed": self.stats.schedules_failed,
            },
        }


class SchedulerService:
    """Main scheduler orchestrator — beat-as-poller pattern.

    Coordinates backend timing, schedule repository, distributed locks,
    and work dispatch into a unified scheduling service.

    Example:
        >>> from spine.core.scheduling import (
        ...     SchedulerService,
        ...     ThreadSchedulerBackend,
        ...     ScheduleRepository,
        ...     LockManager,
        ... )
        >>> from spine.execution import EventDispatcher
        >>>
        >>> # Create components
        >>> backend = ThreadSchedulerBackend()
        >>> repo = ScheduleRepository(conn)
        >>> locks = LockManager(conn)
        >>> dispatcher = EventDispatcher(executor)
        >>>
        >>> # Create and start service
        >>> service = SchedulerService(
        ...     backend=backend,
        ...     repository=repo,
        ...     lock_manager=locks,
        ...     dispatcher=dispatcher,
        ... )
        >>> service.start()
        >>>
        >>> # Later...
        >>> service.stop()
    """

    def __init__(
        self,
        backend: SchedulerBackend,
        repository: ScheduleRepository,
        lock_manager: LockManager,
        dispatcher: EventDispatcher | None = None,
        interval_seconds: float = 10.0,
    ) -> None:
        """Initialize scheduler service.

        Args:
            backend: Timing backend (Thread, APScheduler, Celery)
            repository: Schedule data repository
            lock_manager: Distributed lock manager
            dispatcher: Work dispatcher (optional for testing)
            interval_seconds: Tick interval (default: 10s)
        """
        self.backend = backend
        self.repository = repository
        self.lock_manager = lock_manager
        self.dispatcher = dispatcher
        self.interval = interval_seconds

        self._stats = SchedulerStats()
        self._running = False

    # === Lifecycle ===

    def start(self) -> None:
        """Start the scheduler service.

        Begins the backend tick loop.
        """
        if self._running:
            logger.warning("SchedulerService already running")
            return

        logger.info(
            f"Starting SchedulerService with {self.backend.name} backend "
            f"(interval={self.interval}s)"
        )
        self.backend.start(self._tick, self.interval)
        self._running = True

    def stop(self) -> None:
        """Stop the scheduler service gracefully.

        Waits for current tick to complete.
        """
        if not self._running:
            return

        logger.info("Stopping SchedulerService...")
        self.backend.stop()
        self._running = False
        logger.info("SchedulerService stopped")

    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running

    # === Tick Processing ===

    async def _tick(self) -> None:
        """Single scheduler tick — check and dispatch due schedules.

        Called by backend at each interval.
        """
        self._stats.tick_count += 1
        self._stats.last_tick = datetime.now(UTC)

        try:
            # Periodic lock cleanup
            if self._stats.tick_count % 6 == 0:  # Every ~minute
                self.lock_manager.cleanup_expired_locks()

            # Get due schedules
            now = datetime.now(UTC)
            due_schedules = self.repository.get_due_schedules(now)

            if not due_schedules:
                logger.debug("No schedules due")
                return

            logger.info(f"Found {len(due_schedules)} due schedule(s)")

            # Process each due schedule
            for schedule in due_schedules:
                await self._process_schedule(schedule)

        except Exception as e:
            self._stats.last_error = str(e)
            logger.exception(f"Tick failed: {e}")

    async def _process_schedule(self, schedule: Schedule) -> None:
        """Process a single due schedule.

        Args:
            schedule: Schedule to process
        """
        # Try to acquire lock
        if not self.lock_manager.acquire_schedule_lock(schedule.id):
            logger.debug(f"Schedule {schedule.name} locked by another instance")
            self._stats.schedules_skipped += 1
            return

        try:
            # Check misfire grace
            if not self._within_grace_period(schedule):
                logger.warning(f"Schedule {schedule.name} missed grace period, skipping")
                self._stats.schedules_skipped += 1
                self._reschedule(schedule, "MISSED")
                return

            # Dispatch
            run_id = await self._dispatch(schedule)
            logger.info(f"Dispatched schedule {schedule.name} -> run {run_id}")

            # Update schedule
            self.repository.mark_run_completed(schedule.id, "COMPLETED")
            self._stats.schedules_processed += 1

        except Exception as e:
            logger.exception(f"Schedule {schedule.name} failed: {e}")
            self.repository.mark_run_completed(schedule.id, "FAILED", error=str(e))
            self._stats.schedules_failed += 1

        finally:
            self.lock_manager.release_schedule_lock(schedule.id)

    async def _dispatch(self, schedule: Schedule) -> str:
        """Dispatch schedule target to EventDispatcher.

        Args:
            schedule: Schedule to dispatch

        Returns:
            run_id from dispatcher
        """
        params = json.loads(schedule.params) if schedule.params else {}

        if not self.dispatcher:
            # Testing mode — record run and return sentinel
            self.repository.mark_run_started(schedule.id, "test-run-id")
            logger.info(f"Would dispatch {schedule.target_type}:{schedule.target_name}")
            return "test-run-id"

        if schedule.target_type == "workflow":
            run_id = await self.dispatcher.submit_workflow(
                schedule.target_name, {**params, "trigger_source": "schedule"}
            )
        elif schedule.target_type == "operation":
            run_id = await self.dispatcher.submit_operation(
                schedule.target_name, {**params, "trigger_source": "schedule"}
            )
        else:
            raise ValueError(f"Unknown target_type: {schedule.target_type}")

        # Record the run with the actual dispatcher run_id
        self.repository.mark_run_started(schedule.id, run_id)
        return run_id

    def _within_grace_period(self, schedule: Schedule) -> bool:
        """Check if schedule is within misfire grace period.

        Args:
            schedule: Schedule to check

        Returns:
            True if within grace, False if missed
        """
        if not schedule.next_run_at:
            return True

        scheduled_time = datetime.fromisoformat(schedule.next_run_at)
        grace_seconds = schedule.misfire_grace_seconds or 60
        now = datetime.now(UTC)

        # Normalize to UTC
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=UTC)

        deadline = scheduled_time + timedelta(seconds=grace_seconds)
        return now <= deadline

    def _reschedule(self, schedule: Schedule, status: str) -> None:
        """Reschedule without executing.

        Args:
            schedule: Schedule to reschedule
            status: Status to record (MISSED, SKIPPED)
        """
        self.repository.mark_run_completed(schedule.id, status)

    # === Manual Operations ===

    async def trigger(self, schedule_name: str, params: dict | None = None) -> str:
        """Manually trigger a schedule.

        Args:
            schedule_name: Name of schedule to trigger
            params: Override parameters (optional)

        Returns:
            run_id from dispatcher

        Raises:
            KeyError: If schedule not found
        """
        schedule = self.repository.get_by_name(schedule_name)
        if not schedule:
            raise KeyError(f"Schedule not found: {schedule_name}")

        # Override params if provided
        if params:
            # Create synthetic schedule with merged params
            original_params = json.loads(schedule.params) if schedule.params else {}
            merged = {**original_params, **params}
            from dataclasses import replace as _dc_replace
            schedule = _dc_replace(schedule, params=json.dumps(merged))

        return await self._dispatch(schedule)

    def pause(self, schedule_name: str) -> bool:
        """Pause a schedule.

        Args:
            schedule_name: Name of schedule to pause

        Returns:
            True if paused, False if not found
        """
        from .repository import ScheduleUpdate

        schedule = self.repository.get_by_name(schedule_name)
        if not schedule:
            return False

        self.repository.update(schedule.id, ScheduleUpdate(enabled=False))
        logger.info(f"Paused schedule: {schedule_name}")
        return True

    def resume(self, schedule_name: str) -> bool:
        """Resume a paused schedule.

        Args:
            schedule_name: Name of schedule to resume

        Returns:
            True if resumed, False if not found
        """
        from .repository import ScheduleUpdate

        schedule = self.repository.get_by_name(schedule_name)
        if not schedule:
            return False

        self.repository.update(schedule.id, ScheduleUpdate(enabled=True))
        logger.info(f"Resumed schedule: {schedule_name}")
        return True

    # === Health & Stats ===

    def health(self) -> SchedulerHealth:
        """Get scheduler health status.

        Returns:
            SchedulerHealth with detailed status
        """
        backend_health = self.backend.health()
        active_locks = len(self.lock_manager.list_active_locks())

        return SchedulerHealth(
            healthy=self._running and backend_health.get("healthy", False),
            backend=backend_health,
            schedules_enabled=self.repository.count_enabled(),
            active_locks=active_locks,
            last_tick=self._stats.last_tick,
            stats=self._stats,
        )

    def get_stats(self) -> SchedulerStats:
        """Get scheduler statistics.

        Returns:
            Current SchedulerStats
        """
        return self._stats

    def reset_stats(self) -> None:
        """Reset scheduler statistics."""
        self._stats = SchedulerStats()
