"""Schedule management for periodic pipeline execution."""

from datetime import datetime, timezone
from typing import Any

import ulid
from croniter import croniter
import structlog
from psycopg.types.json import Json

from market_spine.db import get_connection

logger = structlog.get_logger()


class ScheduleManager:
    """
    Schedule manager for periodic pipeline execution.

    Handles:
    - Creating/updating/deleting schedules
    - Computing next run times
    - Checking for due schedules

    All methods are class methods for convenient static access.
    """

    @classmethod
    def create_schedule(
        cls,
        pipeline_name: str,
        cron_expression: str,
        params: dict | None = None,
        name: str | None = None,
        timezone_str: str = "UTC",
        enabled: bool = True,
    ) -> str:
        """
        Create a new schedule.

        Args:
            pipeline_name: Pipeline to execute
            cron_expression: Cron expression (e.g., "0 6 * * *" for 6 AM daily)
            params: Pipeline parameters
            name: Schedule name (defaults to pipeline_name if not provided)
            timezone_str: Timezone for schedule (default: UTC)
            enabled: Whether schedule is active

        Returns:
            Schedule ID
        """
        schedule_id = str(ulid.new())
        params = params or {}
        name = name or pipeline_name

        # Validate cron expression
        try:
            cron = croniter(cron_expression)
            next_run = cron.get_next(datetime)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {cron_expression}") from e

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO schedules (
                    id, name, pipeline_name, params, cron_expression,
                    timezone, enabled, next_run_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    schedule_id,
                    name,
                    pipeline_name,
                    Json(params),
                    cron_expression,
                    timezone_str,
                    enabled,
                    next_run,
                ),
            )
            conn.commit()

        logger.info(
            "schedule_created",
            schedule_id=schedule_id,
            name=name,
            pipeline_name=pipeline_name,
            cron_expression=cron_expression,
        )

        return schedule_id

    @classmethod
    def get(cls, schedule_id: str) -> dict | None:
        """Get a schedule by ID."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, name, pipeline_name, params, cron_expression,
                       timezone, enabled, last_run_at, next_run_at,
                       created_at, updated_at
                FROM schedules
                WHERE id = %s
                """,
                (schedule_id,),
            )
            row = result.fetchone()
            return dict(row) if row else None

    @classmethod
    def get_by_name(cls, name: str) -> dict | None:
        """Get a schedule by name."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, name, pipeline_name, params, cron_expression,
                       timezone, enabled, last_run_at, next_run_at,
                       created_at, updated_at
                FROM schedules
                WHERE name = %s
                """,
                (name,),
            )
            row = result.fetchone()
            return dict(row) if row else None

    @classmethod
    def list_schedules(
        cls,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        """List all schedules."""
        with get_connection() as conn:
            if enabled_only:
                result = conn.execute(
                    """
                    SELECT id, name, pipeline_name, params, cron_expression,
                           timezone, enabled, last_run_at, next_run_at
                    FROM schedules
                    WHERE enabled = true
                    ORDER BY next_run_at
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                result = conn.execute(
                    """
                    SELECT id, name, pipeline_name, params, cron_expression,
                           timezone, enabled, last_run_at, next_run_at
                    FROM schedules
                    ORDER BY name
                    LIMIT %s
                    """,
                    (limit,),
                )
            return [dict(row) for row in result.fetchall()]

    @classmethod
    def update_schedule(
        cls,
        schedule_id: str,
        cron_expression: str | None = None,
        params: dict | None = None,
        enabled: bool | None = None,
    ) -> bool:
        """Update a schedule."""
        updates = []
        values: list = []

        if cron_expression is not None:
            # Validate and compute next run
            try:
                cron = croniter(cron_expression)
                next_run = cron.get_next(datetime)
            except Exception as e:
                raise ValueError(f"Invalid cron expression: {cron_expression}") from e

            updates.append("cron_expression = %s")
            values.append(cron_expression)
            updates.append("next_run_at = %s")
            values.append(next_run)

        if params is not None:
            updates.append("params = %s")
            values.append(Json(params))

        if enabled is not None:
            updates.append("enabled = %s")
            values.append(enabled)

        if not updates:
            return False

        updates.append("updated_at = NOW()")
        values.append(schedule_id)

        with get_connection() as conn:
            result = conn.execute(
                f"""
                UPDATE schedules
                SET {", ".join(updates)}
                WHERE id = %s
                RETURNING id
                """,
                tuple(values),
            )
            updated = result.fetchone() is not None
            conn.commit()

        if updated:
            logger.info("schedule_updated", schedule_id=schedule_id)

        return updated

    @classmethod
    def delete_schedule(cls, schedule_id: str) -> bool:
        """Delete a schedule."""
        with get_connection() as conn:
            result = conn.execute(
                "DELETE FROM schedules WHERE id = %s RETURNING id",
                (schedule_id,),
            )
            deleted = result.fetchone() is not None
            conn.commit()

        if deleted:
            logger.info("schedule_deleted", schedule_id=schedule_id)

        return deleted

    @classmethod
    def enable_schedule(cls, schedule_id: str) -> bool:
        """Enable a schedule."""
        return cls.update_schedule(schedule_id, enabled=True)

    @classmethod
    def disable_schedule(cls, schedule_id: str) -> bool:
        """Disable a schedule."""
        return cls.update_schedule(schedule_id, enabled=False)

    @classmethod
    def get_due_schedules(cls) -> list[dict]:
        """Get schedules that are due to run."""
        now = datetime.now(timezone.utc)

        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, name, pipeline_name, params, cron_expression, timezone
                FROM schedules
                WHERE enabled = true AND next_run_at <= %s
                ORDER BY next_run_at
                """,
                (now,),
            )
            return [dict(row) for row in result.fetchall()]

    @classmethod
    def mark_run(cls, schedule_id: str) -> None:
        """
        Mark a schedule as run and compute next run time.
        """
        with get_connection() as conn:
            # Get current schedule
            result = conn.execute(
                "SELECT cron_expression FROM schedules WHERE id = %s",
                (schedule_id,),
            )
            row = result.fetchone()

            if not row:
                return

            # Compute next run
            cron = croniter(row["cron_expression"])
            next_run = cron.get_next(datetime)

            # Update
            conn.execute(
                """
                UPDATE schedules
                SET last_run_at = NOW(), next_run_at = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (next_run, schedule_id),
            )
            conn.commit()

        logger.debug("schedule_marked_run", schedule_id=schedule_id, next_run=next_run)
