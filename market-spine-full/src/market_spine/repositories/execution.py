"""Execution repository - wraps ledger with additional query methods."""

from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

from market_spine.core.database import get_pool
from market_spine.core.models import ExecutionStatus


class ExecutionRepository:
    """Additional execution queries not in the ledger."""

    def __init__(self, conn: psycopg.Connection | None = None):
        """Initialize with optional connection."""
        self._conn = conn

    def _get_conn(self) -> psycopg.Connection:
        """Get connection from pool or use provided one."""
        if self._conn is not None:
            return self._conn
        return get_pool().connection()

    def get_stale_executions(
        self,
        older_than_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Find executions that are stuck in RUNNING state."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
                cur.execute(
                    """
                    SELECT id, pipeline, started_at
                    FROM executions
                    WHERE status = %s AND started_at < %s
                    """,
                    (ExecutionStatus.RUNNING.value, cutoff),
                )
                return list(cur.fetchall())

    def get_execution_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get execution statistics for the given time period."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cutoff = datetime.utcnow() - timedelta(hours=hours)

                # Counts by status
                cur.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM executions
                    WHERE created_at > %s
                    GROUP BY status
                    """,
                    (cutoff,),
                )
                status_counts = {row["status"]: row["count"] for row in cur.fetchall()}

                # Counts by pipeline
                cur.execute(
                    """
                    SELECT pipeline, COUNT(*) as count
                    FROM executions
                    WHERE created_at > %s
                    GROUP BY pipeline
                    """,
                    (cutoff,),
                )
                pipeline_counts = {row["pipeline"]: row["count"] for row in cur.fetchall()}

                # Average duration
                cur.execute(
                    """
                    SELECT pipeline,
                           AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration
                    FROM executions
                    WHERE created_at > %s
                      AND status = 'completed'
                      AND started_at IS NOT NULL
                    GROUP BY pipeline
                    """,
                    (cutoff,),
                )
                avg_durations = {
                    row["pipeline"]: float(row["avg_duration"]) if row["avg_duration"] else None
                    for row in cur.fetchall()
                }

                return {
                    "period_hours": hours,
                    "status_counts": status_counts,
                    "pipeline_counts": pipeline_counts,
                    "avg_duration_by_pipeline": avg_durations,
                }

    def cleanup_old_executions(self, days: int = 90) -> int:
        """Delete executions older than the given number of days."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cutoff = datetime.utcnow() - timedelta(days=days)

                # First delete events
                cur.execute(
                    """
                    DELETE FROM execution_events
                    WHERE execution_id IN (
                        SELECT id FROM executions WHERE created_at < %s
                    )
                    """,
                    (cutoff,),
                )

                # Then delete executions
                cur.execute(
                    "DELETE FROM executions WHERE created_at < %s",
                    (cutoff,),
                )
                conn.commit()
                return cur.rowcount

    def cleanup_old_dead_letters(self, days: int = 90) -> int:
        """Delete resolved dead letters older than the given number of days."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cutoff = datetime.utcnow() - timedelta(days=days)
                cur.execute(
                    """
                    DELETE FROM dead_letters
                    WHERE resolved_at IS NOT NULL AND created_at < %s
                    """,
                    (cutoff,),
                )
                conn.commit()
                return cur.rowcount
