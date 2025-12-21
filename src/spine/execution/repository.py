"""Execution Repository — analytics and maintenance queries.

Manifesto:
The :class:`ExecutionLedger` handles basic CRUD (create, update,
get-by-id).  The repository adds higher-level analytic queries
(stats over time, stale-execution detection, bulk cleanup) used
by health checks, dashboards, and scheduled maintenance jobs.

ARCHITECTURE
────────────
::

    ExecutionRepository(conn)
      ├── .get_execution_stats(hours)       ─ counts + durations
      ├── .get_stale_executions(minutes)    ─ stuck “running” rows
      ├── .get_operation_stats(operation)     ─ per-operation analytics
      ├── .cleanup_old(days)                ─ purge completed records
      └── .get_execution_timeline(hours)    ─ time-series for charts

Related modules:
    ledger.py  — basic CRUD (create / update / get)
    health.py  — uses repository for health scoring
    dlq.py     — dead-letter queue (failed executions)

Example::

    repo = ExecutionRepository(conn)
    stats = repo.get_execution_stats(hours=24)
    print(stats["status_counts"])  # {'completed': 50, 'failed': 5}
    stale = repo.get_stale_executions(older_than_minutes=60)

Tags:
    spine-core, execution, repository, persistence, query

Doc-Types:
    api-reference
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from .models import ExecutionStatus


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class ExecutionRepository:
    """Additional execution queries for analytics and maintenance.

    This wraps the ledger with higher-level query methods for:
    - Finding stuck/stale executions
    - Getting execution statistics
    - Cleaning up old records
    """

    def __init__(self, conn):
        """Initialize with a database connection.

        Args:
            conn: Database connection (sqlite3.Connection or psycopg.Connection)
        """
        self._conn = conn

    def get_stale_executions(
        self,
        older_than_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Find executions stuck in RUNNING state.

        Args:
            older_than_minutes: Consider "stale" if running longer than this

        Returns:
            List of execution info dicts
        """
        cursor = self._conn.cursor()
        cutoff = utcnow() - timedelta(minutes=older_than_minutes)

        cursor.execute(
            """
            SELECT id, workflow, started_at, lane
            FROM core_executions
            WHERE status = ? AND started_at < ?
            """,
            (ExecutionStatus.RUNNING.value, cutoff.isoformat()),
        )
        return [
            {
                "id": row[0],
                "workflow": row[1],
                "started_at": row[2],
                "lane": row[3],
            }
            for row in cursor.fetchall()
        ]

    def get_execution_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get execution statistics for the given time period.

        Args:
            hours: Time window to analyze

        Returns:
            Dict with status_counts, workflow_counts, avg_duration_by_workflow
        """
        cursor = self._conn.cursor()
        cutoff = utcnow() - timedelta(hours=hours)

        # Counts by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM core_executions
            WHERE created_at > ?
            GROUP BY status
            """,
            (cutoff.isoformat(),),
        )
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Counts by workflow
        cursor.execute(
            """
            SELECT workflow, COUNT(*) as count
            FROM core_executions
            WHERE created_at > ?
            GROUP BY workflow
            """,
            (cutoff.isoformat(),),
        )
        workflow_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Average duration for completed executions
        # SQLite doesn't have good datetime math, so we compute in Python
        cursor.execute(
            """
            SELECT workflow, started_at, completed_at
            FROM core_executions
            WHERE created_at > ?
              AND status = 'completed'
              AND started_at IS NOT NULL
              AND completed_at IS NOT NULL
            """,
            (cutoff.isoformat(),),
        )

        durations: dict[str, list[float]] = {}
        for row in cursor.fetchall():
            workflow = row[0]
            started = datetime.fromisoformat(row[1])
            completed = datetime.fromisoformat(row[2])
            duration = (completed - started).total_seconds()

            if workflow not in durations:
                durations[workflow] = []
            durations[workflow].append(duration)

        avg_durations = {workflow: sum(times) / len(times) for workflow, times in durations.items()}

        # Failure rate by workflow
        cursor.execute(
            """
            SELECT workflow,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM core_executions
            WHERE created_at > ?
            GROUP BY workflow
            """,
            (cutoff.isoformat(),),
        )
        failure_rates = {}
        for row in cursor.fetchall():
            workflow = row[0]
            completed = row[1] or 0
            failed = row[2] or 0
            total = completed + failed
            failure_rates[workflow] = (failed / total * 100) if total > 0 else 0.0

        return {
            "period_hours": hours,
            "status_counts": status_counts,
            "workflow_counts": workflow_counts,
            "avg_duration_by_workflow": avg_durations,
            "failure_rate_by_workflow": failure_rates,
        }

    def get_recent_failures(
        self,
        hours: int = 24,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent failed executions.

        Args:
            hours: Time window
            limit: Max results

        Returns:
            List of failure info dicts
        """
        cursor = self._conn.cursor()
        cutoff = utcnow() - timedelta(hours=hours)

        cursor.execute(
            """
            SELECT id, workflow, error, completed_at, retry_count
            FROM core_executions
            WHERE status = 'failed' AND created_at > ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (cutoff.isoformat(), limit),
        )
        return [
            {
                "id": row[0],
                "workflow": row[1],
                "error": row[2],
                "failed_at": row[3],
                "retry_count": row[4],
            }
            for row in cursor.fetchall()
        ]

    def cleanup_old_executions(self, days: int = 90) -> int:
        """Delete executions older than the given number of days.

        Also deletes associated events (via CASCADE or manual delete).

        Args:
            days: Delete executions older than this

        Returns:
            Number of executions deleted
        """
        cursor = self._conn.cursor()
        cutoff = utcnow() - timedelta(days=days)

        # First delete events (SQLite may not support CASCADE)
        cursor.execute(
            """
            DELETE FROM core_execution_events
            WHERE execution_id IN (
                SELECT id FROM core_executions WHERE created_at < ?
            )
            """,
            (cutoff.isoformat(),),
        )

        # Then delete executions
        cursor.execute(
            "DELETE FROM core_executions WHERE created_at < ?",
            (cutoff.isoformat(),),
        )
        count = cursor.rowcount
        self._conn.commit()
        return count

    def get_workflow_throughput(
        self,
        workflow: str,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Get throughput metrics for a specific workflow.

        Args:
            workflow: Workflow name
            hours: Time window

        Returns:
            Dict with total, completed, failed, avg_duration, max_duration
        """
        cursor = self._conn.cursor()
        cutoff = utcnow() - timedelta(hours=hours)

        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM core_executions
            WHERE workflow = ? AND created_at > ?
            GROUP BY status
            """,
            (workflow, cutoff.isoformat()),
        )
        counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Get durations
        cursor.execute(
            """
            SELECT started_at, completed_at
            FROM core_executions
            WHERE workflow = ?
              AND created_at > ?
              AND status = 'completed'
              AND started_at IS NOT NULL
              AND completed_at IS NOT NULL
            """,
            (workflow, cutoff.isoformat()),
        )

        durations = []
        for row in cursor.fetchall():
            started = datetime.fromisoformat(row[0])
            completed = datetime.fromisoformat(row[1])
            durations.append((completed - started).total_seconds())

        return {
            "workflow": workflow,
            "period_hours": hours,
            "total": sum(counts.values()),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "avg_duration_seconds": sum(durations) / len(durations) if durations else None,
            "max_duration_seconds": max(durations) if durations else None,
            "min_duration_seconds": min(durations) if durations else None,
        }

    def get_queue_depth(self) -> dict[str, int]:
        """Get current queue depth by lane.

        Returns:
            Dict mapping lane -> count of pending/queued executions
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT lane, COUNT(*) as count
            FROM core_executions
            WHERE status IN ('pending', 'queued')
            GROUP BY lane
            """
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
