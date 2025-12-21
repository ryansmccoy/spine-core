"""Schedule repository - CRUD and cron evaluation.

Manifesto:
    Schedule persistence and next-run computation are pure data operations
    that belong in a repository, not in the service layer.  Separating
    them enables testing with in-memory connections and keeps the service
    focused on orchestration.

This module provides the data access layer for schedules, plus cron
expression evaluation using croniter.

Tags:
    spine-core, scheduling, repository, CRUD, cron, croniter

Doc-Types:
    api-reference, architecture-diagram


┌──────────────────────────────────────────────────────────────────────────────┐
│  SCHEDULE REPOSITORY                                                          │
│                                                                               │
│  Responsibility: Schedule persistence + next-run computation                 │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐      │
│  │                      ScheduleRepository                            │      │
│  │                                                                    │      │
│  │   CRUD Operations:                                                 │      │
│  │   ├── create(spec) → Schedule                                      │      │
│  │   ├── get(id) → Schedule | None                                   │      │
│  │   ├── get_by_name(name) → Schedule | None                         │      │
│  │   ├── update(id, updates) → Schedule | None                       │      │
│  │   ├── delete(id) → bool                                           │      │
│  │   └── list_enabled() → list[Schedule]                              │      │
│  │                                                                    │      │
│  │   Scheduling Operations:                                           │      │
│  │   ├── get_due_schedules(now) → list[Schedule]                      │      │
│  │   ├── compute_next_run(schedule, after) → datetime                 │      │
│  │   ├── mark_run_started(schedule_id, run_id) → None                 │      │
│  │   └── mark_run_completed(schedule_id, status, next_run) → None     │      │
│  │                                                                    │      │
│  │   Schedule Run Operations:                                         │      │
│  │   ├── create_run(schedule, run_id) → ScheduleRun                   │      │
│  │   ├── get_run(run_id) → ScheduleRun | None                         │      │
│  │   └── list_runs(schedule_id) → list[ScheduleRun]                   │      │
│  │                                                                    │      │
│  └────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  Cron Evaluation:                                                             │
│  - Uses croniter library for cron parsing                                     │
│  - Handles timezones via schedule.timezone field                              │
│  - Supports: cron, interval, once (date) schedule types                       │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from spine.core.dialect import Dialect, SQLiteDialect
from spine.core.models.scheduler import Schedule, ScheduleRun
from spine.core.protocols import Connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create/Update DTOs
# ---------------------------------------------------------------------------


@dataclass
class ScheduleCreate:
    """DTO for creating a new schedule."""

    name: str
    target_type: str  # operation, workflow
    target_name: str
    schedule_type: str = "cron"  # cron, interval, date
    cron_expression: str | None = None
    interval_seconds: int | None = None
    run_at: str | None = None
    timezone: str = "UTC"
    params: dict[str, Any] | None = None
    enabled: bool = True
    max_instances: int = 1
    misfire_grace_seconds: int = 60
    created_by: str | None = None


@dataclass
class ScheduleUpdate:
    """DTO for updating a schedule."""

    enabled: bool | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None
    timezone: str | None = None
    params: dict[str, Any] | None = None
    max_instances: int | None = None
    misfire_grace_seconds: int | None = None


@dataclass
class ScheduleRunCreate:
    """DTO for creating a schedule run record."""

    schedule_id: str
    schedule_name: str
    scheduled_at: datetime
    run_id: str | None = None
    execution_id: str | None = None


# ---------------------------------------------------------------------------
# Repository Implementation
# ---------------------------------------------------------------------------


class ScheduleRepository:
    """Repository for schedule CRUD and cron evaluation.

    Example:
        >>> repo = ScheduleRepository(conn)
        >>>
        >>> # Create schedule
        >>> schedule = repo.create(ScheduleCreate(
        ...     name="daily-report",
        ...     target_type="workflow",
        ...     target_name="generate-report",
        ...     cron_expression="0 8 * * *",
        ... ))
        >>>
        >>> # Get due schedules
        >>> due = repo.get_due_schedules(datetime.now(UTC))
        >>> for s in due:
        ...     print(f"Due: {s.name}")
    """

    def __init__(self, conn: Connection, dialect: Dialect | None = None) -> None:
        """Initialize repository with database connection.

        Args:
            conn: Database connection (any backend satisfying Connection protocol)
            dialect: SQL dialect for portable queries. Defaults to SQLiteDialect.
        """
        self.conn = conn
        self.dialect: Dialect = dialect or SQLiteDialect()

    def _ph(self, count: int) -> str:
        """Generate placeholder string for this dialect."""
        return self.dialect.placeholders(count)

    # === CRUD Operations ===

    def create(self, spec: ScheduleCreate) -> Schedule:
        """Create a new schedule.

        Args:
            spec: Schedule creation specification

        Returns:
            Created Schedule with generated ID
        """
        # Use uuid4 for schedule ID generation
        schedule_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        params_json = json.dumps(spec.params) if spec.params else None

        # Compute initial next_run_at
        next_run = self.compute_next_run_from_spec(spec, datetime.now(UTC))
        next_run_iso = next_run.isoformat() if next_run else None

        self.conn.execute(
            f"""
            INSERT INTO core_schedules (
                id, name, target_type, target_name, params,
                schedule_type, cron_expression, interval_seconds, run_at, timezone,
                enabled, max_instances, misfire_grace_seconds,
                next_run_at, created_at, updated_at, created_by
            ) VALUES ({self._ph(17)})
            """,
            (
                schedule_id,
                spec.name,
                spec.target_type,
                spec.target_name,
                params_json,
                spec.schedule_type,
                spec.cron_expression,
                spec.interval_seconds,
                spec.run_at,
                spec.timezone,
                1 if spec.enabled else 0,
                spec.max_instances,
                spec.misfire_grace_seconds,
                next_run_iso,
                now,
                now,
                spec.created_by,
            ),
        )
        self.conn.commit()

        return self.get(schedule_id)  # type: ignore

    def get(self, schedule_id: str) -> Schedule | None:
        """Get schedule by ID.

        Args:
            schedule_id: Schedule ULID

        Returns:
            Schedule if found, None otherwise
        """
        cursor = self.conn.execute(
            f"SELECT * FROM core_schedules WHERE id = {self._ph(1)}",
            (schedule_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_schedule(row)

    def get_by_name(self, name: str) -> Schedule | None:
        """Get schedule by name.

        Args:
            name: Schedule name

        Returns:
            Schedule if found, None otherwise
        """
        cursor = self.conn.execute(
            f"SELECT * FROM core_schedules WHERE name = {self._ph(1)}",
            (name,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_schedule(row)

    def update(self, schedule_id: str, updates: ScheduleUpdate) -> Schedule | None:
        """Update a schedule.

        Args:
            schedule_id: Schedule ID
            updates: Fields to update

        Returns:
            Updated Schedule if found, None otherwise
        """
        # Build dynamic update
        set_parts = []
        params: list[Any] = []

        if updates.enabled is not None:
            set_parts.append(f"enabled = {self._ph(1)}")
            params.append(1 if updates.enabled else 0)
        if updates.cron_expression is not None:
            set_parts.append(f"cron_expression = {self._ph(1)}")
            params.append(updates.cron_expression)
        if updates.interval_seconds is not None:
            set_parts.append(f"interval_seconds = {self._ph(1)}")
            params.append(updates.interval_seconds)
        if updates.timezone is not None:
            set_parts.append(f"timezone = {self._ph(1)}")
            params.append(updates.timezone)
        if updates.params is not None:
            set_parts.append(f"params = {self._ph(1)}")
            params.append(json.dumps(updates.params))
        if updates.max_instances is not None:
            set_parts.append(f"max_instances = {self._ph(1)}")
            params.append(updates.max_instances)
        if updates.misfire_grace_seconds is not None:
            set_parts.append(f"misfire_grace_seconds = {self._ph(1)}")
            params.append(updates.misfire_grace_seconds)

        if not set_parts:
            return self.get(schedule_id)

        set_parts.append(f"updated_at = {self._ph(1)}")
        params.append(datetime.now(UTC).isoformat())
        set_parts.append("version = version + 1")

        params.append(schedule_id)

        self.conn.execute(
            f"UPDATE core_schedules SET {', '.join(set_parts)} WHERE id = {self._ph(1)}",
            params,
        )
        self.conn.commit()

        return self.get(schedule_id)

    def delete(self, schedule_id: str) -> bool:
        """Delete a schedule.

        Args:
            schedule_id: Schedule ID

        Returns:
            True if deleted, False if not found
        """
        cursor = self.conn.execute(
            f"DELETE FROM core_schedules WHERE id = {self._ph(1)}",
            (schedule_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list_enabled(self) -> list[Schedule]:
        """List all enabled schedules.

        Returns:
            List of enabled Schedule objects
        """
        cursor = self.conn.execute(
            "SELECT * FROM core_schedules WHERE enabled = 1 ORDER BY name"
        )
        return [self._row_to_schedule(row) for row in cursor.fetchall()]

    def list_all(self) -> list[Schedule]:
        """List all schedules (enabled and disabled).

        Returns:
            List of all Schedule objects
        """
        cursor = self.conn.execute("SELECT * FROM core_schedules ORDER BY name")
        return [self._row_to_schedule(row) for row in cursor.fetchall()]

    def count_enabled(self) -> int:
        """Count enabled schedules.

        Returns:
            Number of enabled schedules
        """
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM core_schedules WHERE enabled = 1"
        )
        return cursor.fetchone()[0]

    # === Scheduling Operations ===

    def get_due_schedules(self, now: datetime) -> list[Schedule]:
        """Get all schedules that are due for execution.

        A schedule is due if:
        - enabled = 1
        - next_run_at <= now

        Args:
            now: Current timestamp

        Returns:
            List of due schedules
        """
        now_iso = now.isoformat()
        cursor = self.conn.execute(
            f"""
            SELECT * FROM core_schedules
            WHERE enabled = 1 AND next_run_at <= {self._ph(1)}
            ORDER BY next_run_at
            """,
            (now_iso,),
        )
        return [self._row_to_schedule(row) for row in cursor.fetchall()]

    def compute_next_run(self, schedule: Schedule, after: datetime) -> datetime | None:
        """Compute next run time for a schedule.

        Args:
            schedule: Schedule to compute for
            after: Compute next run after this time

        Returns:
            Next run datetime, or None if schedule type is 'date' and expired
        """
        if schedule.schedule_type == "cron":
            return self._compute_cron_next(schedule.cron_expression, after, schedule.timezone)
        elif schedule.schedule_type == "interval":
            if schedule.interval_seconds:
                return after + timedelta(seconds=schedule.interval_seconds)
            return None
        elif schedule.schedule_type == "date":
            # One-time schedule
            if schedule.run_at:
                run_at = datetime.fromisoformat(schedule.run_at)
                if run_at > after:
                    return run_at
            return None
        else:
            logger.warning(f"Unknown schedule_type: {schedule.schedule_type}")
            return None

    def compute_next_run_from_spec(
        self, spec: ScheduleCreate, after: datetime
    ) -> datetime | None:
        """Compute next run time from creation spec.

        Args:
            spec: Schedule creation spec
            after: Compute next run after this time

        Returns:
            Next run datetime
        """
        if spec.schedule_type == "cron":
            return self._compute_cron_next(spec.cron_expression, after, spec.timezone)
        elif spec.schedule_type == "interval":
            if spec.interval_seconds:
                return after + timedelta(seconds=spec.interval_seconds)
            return None
        elif spec.schedule_type == "date":
            if spec.run_at:
                return datetime.fromisoformat(spec.run_at)
            return None
        return None

    def _compute_cron_next(
        self,
        cron_expression: str | None,
        after: datetime,
        timezone: str = "UTC",
    ) -> datetime | None:
        """Compute next run time using croniter.

        Args:
            cron_expression: Cron expression (5-part)
            after: Compute next run after this time
            timezone: Timezone for evaluation

        Returns:
            Next run datetime in UTC
        """
        if not cron_expression:
            return None

        try:
            from croniter import croniter

            # Handle timezone
            if timezone != "UTC":
                try:
                    import zoneinfo

                    tz = zoneinfo.ZoneInfo(timezone)
                    after_local = after.astimezone(tz)
                except (ImportError, KeyError):
                    after_local = after
            else:
                after_local = after

            cron = croniter(cron_expression, after_local)
            next_run = cron.get_next(datetime)

            # Convert back to UTC
            if next_run.tzinfo is not None:
                return next_run.astimezone(UTC)
            return next_run

        except ImportError:
            logger.warning("croniter not installed; using fallback")
            # Fallback: next hour
            return after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        except Exception as e:
            logger.error(f"Cron parse error: {e}")
            return None

    def mark_run_started(
        self,
        schedule_id: str,
        run_id: str,
        scheduled_at: datetime | None = None,
    ) -> str:
        """Mark a schedule run as started.

        Creates a schedule_run record and updates last_run_at.

        Args:
            schedule_id: Schedule ID
            run_id: The workflow/operation run ID
            scheduled_at: When it was scheduled (default: now)

        Returns:
            Schedule run ID
        """
        schedule = self.get(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule not found: {schedule_id}")

        now = datetime.now(UTC)
        scheduled_at = scheduled_at or now
        schedule_run_id = str(uuid4())

        # Create schedule run record
        self.conn.execute(
            f"""
            INSERT INTO core_schedule_runs (
                id, schedule_id, schedule_name, scheduled_at, started_at, status, run_id, created_at
            ) VALUES ({self._ph(8)})
            """,
            (
                schedule_run_id,
                schedule_id,
                schedule.name,
                scheduled_at.isoformat(),
                now.isoformat(),
                "RUNNING",
                run_id,
                now.isoformat(),
            ),
        )

        # Update schedule
        self.conn.execute(
            f"UPDATE core_schedules SET last_run_at = {self._ph(1)}, last_run_status = {self._ph(1)}, updated_at = {self._ph(1)} WHERE id = {self._ph(1)}",
            (now.isoformat(), "RUNNING", now.isoformat(), schedule_id),
        )
        self.conn.commit()

        return schedule_run_id

    def mark_run_completed(
        self,
        schedule_id: str,
        status: str,
        next_run: datetime | None = None,
        error: str | None = None,
    ) -> None:
        """Mark a schedule run as completed.

        Updates next_run_at and last_run_status.

        Args:
            schedule_id: Schedule ID
            status: Final status (COMPLETED, FAILED, SKIPPED)
            next_run: Next run time (computed if not provided)
            error: Error message if failed
        """
        schedule = self.get(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule not found: {schedule_id}")

        now = datetime.now(UTC)

        # Compute next run if not provided
        if next_run is None:
            next_run = self.compute_next_run(schedule, now)

        # Update schedule
        self.conn.execute(
            f"""
            UPDATE core_schedules
            SET last_run_status = {self._ph(1)}, next_run_at = {self._ph(1)}, updated_at = {self._ph(1)}
            WHERE id = {self._ph(1)}
            """,
            (
                status,
                next_run.isoformat() if next_run else None,
                now.isoformat(),
                schedule_id,
            ),
        )

        # Update latest schedule run
        # SQLite doesn't support UPDATE ... ORDER BY ... LIMIT
        # Find the latest running run first
        cursor = self.conn.execute(
            f"""
            SELECT id FROM core_schedule_runs
            WHERE schedule_id = {self._ph(1)} AND status = 'RUNNING'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (schedule_id,),
        )
        row = cursor.fetchone()
        if row:
            self.conn.execute(
                f"""
                UPDATE core_schedule_runs
                SET status = {self._ph(1)}, completed_at = {self._ph(1)}, error = {self._ph(1)}
                WHERE id = {self._ph(1)}
                """,
                (status, now.isoformat(), error, row[0]),
            )
        self.conn.commit()

    # === Schedule Run Operations ===

    def get_run(self, run_id: str) -> ScheduleRun | None:
        """Get schedule run by ID.

        Args:
            run_id: Schedule run ID

        Returns:
            ScheduleRun if found, None otherwise
        """
        cursor = self.conn.execute(
            f"SELECT * FROM core_schedule_runs WHERE id = {self._ph(1)}",
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_schedule_run(row)

    def list_runs(
        self,
        schedule_id: str,
        limit: int = 50,
        status: str | None = None,
    ) -> list[ScheduleRun]:
        """List schedule runs.

        Args:
            schedule_id: Schedule ID to filter by
            limit: Max number of runs to return
            status: Optional status filter

        Returns:
            List of ScheduleRun objects
        """
        if status:
            cursor = self.conn.execute(
                f"""
                SELECT * FROM core_schedule_runs
                WHERE schedule_id = {self._ph(1)} AND status = {self._ph(1)}
                ORDER BY created_at DESC
                LIMIT {self._ph(1)}
                """,
                (schedule_id, status, limit),
            )
        else:
            cursor = self.conn.execute(
                f"""
                SELECT * FROM core_schedule_runs
                WHERE schedule_id = {self._ph(1)}
                ORDER BY created_at DESC
                LIMIT {self._ph(1)}
                """,
                (schedule_id, limit),
            )
        return [self._row_to_schedule_run(row) for row in cursor.fetchall()]

    # === Private Helpers ===

    def _row_to_schedule(self, row: tuple) -> Schedule:
        """Convert database row to Schedule model."""
        columns = [
            "id",
            "name",
            "target_type",
            "target_name",
            "params",
            "schedule_type",
            "cron_expression",
            "interval_seconds",
            "run_at",
            "timezone",
            "enabled",
            "max_instances",
            "misfire_grace_seconds",
            "last_run_at",
            "next_run_at",
            "last_run_status",
            "created_at",
            "updated_at",
            "created_by",
            "version",
        ]
        data = dict(zip(columns, row, strict=False))
        return Schedule(**data)

    def _row_to_schedule_run(self, row: tuple) -> ScheduleRun:
        """Convert database row to ScheduleRun model."""
        columns = [
            "id",
            "schedule_id",
            "schedule_name",
            "scheduled_at",
            "started_at",
            "completed_at",
            "status",
            "run_id",
            "execution_id",
            "error",
            "skip_reason",
            "created_at",
        ]
        data = dict(zip(columns, row, strict=False))
        return ScheduleRun(**data)
