"""Execution ledger - persistent record of all executions and events."""

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from market_spine.core.database import get_pool
from market_spine.core.models import (
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    EventType,
    TriggerSource,
)
from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


class ExecutionLedger:
    """Manages the execution ledger (executions + events)."""

    def __init__(self, conn: psycopg.Connection | None = None):
        """Initialize with optional connection."""
        self._conn = conn

    def _get_conn(self) -> psycopg.Connection:
        """Get connection from pool or use provided one."""
        if self._conn is not None:
            return self._conn
        return get_pool().connection()

    def create_execution(self, execution: Execution) -> Execution:
        """Create a new execution record."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO executions (
                        id, pipeline, params, status, lane, trigger_source,
                        parent_execution_id, created_at, retry_count
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        execution.id,
                        execution.pipeline,
                        psycopg.types.json.Json(execution.params),
                        execution.status.value,
                        execution.lane,
                        execution.trigger_source.value,
                        execution.parent_execution_id,
                        execution.created_at,
                        execution.retry_count,
                    ),
                )
                conn.commit()

        # Record creation event
        self.record_event(execution.id, EventType.CREATED, {"pipeline": execution.pipeline})
        logger.info(
            "execution_created",
            execution_id=execution.id,
            pipeline=execution.pipeline,
        )
        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        """Get execution by ID."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, pipeline, params, status, lane, trigger_source,
                           parent_execution_id, created_at, started_at, completed_at,
                           result, error, retry_count
                    FROM executions
                    WHERE id = %s
                    """,
                    (execution_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_execution(row)

    def update_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update execution status."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                now = datetime.utcnow()

                if status == ExecutionStatus.RUNNING:
                    cur.execute(
                        """
                        UPDATE executions
                        SET status = %s, started_at = %s
                        WHERE id = %s
                        """,
                        (status.value, now, execution_id),
                    )
                    self.record_event(execution_id, EventType.STARTED, {})
                elif status == ExecutionStatus.COMPLETED:
                    cur.execute(
                        """
                        UPDATE executions
                        SET status = %s, completed_at = %s, result = %s
                        WHERE id = %s
                        """,
                        (
                            status.value,
                            now,
                            psycopg.types.json.Json(result) if result else None,
                            execution_id,
                        ),
                    )
                    self.record_event(execution_id, EventType.COMPLETED, result or {})
                elif status == ExecutionStatus.FAILED:
                    cur.execute(
                        """
                        UPDATE executions
                        SET status = %s, completed_at = %s, error = %s
                        WHERE id = %s
                        """,
                        (status.value, now, error, execution_id),
                    )
                    self.record_event(execution_id, EventType.FAILED, {"error": error})
                else:
                    cur.execute(
                        """
                        UPDATE executions
                        SET status = %s
                        WHERE id = %s
                        """,
                        (status.value, execution_id),
                    )
                conn.commit()

        logger.info(
            "execution_status_updated",
            execution_id=execution_id,
            status=status.value,
        )

    def record_event(
        self,
        execution_id: str,
        event_type: EventType,
        data: dict[str, Any],
    ) -> ExecutionEvent:
        """Record an execution event."""
        event = ExecutionEvent.create(execution_id, event_type, data)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO execution_events (id, execution_id, event_type, timestamp, data)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        event.id,
                        event.execution_id,
                        event.event_type.value,
                        event.timestamp,
                        psycopg.types.json.Json(event.data),
                    ),
                )
                conn.commit()
        return event

    def get_events(self, execution_id: str) -> list[ExecutionEvent]:
        """Get all events for an execution."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, execution_id, event_type, timestamp, data
                    FROM execution_events
                    WHERE execution_id = %s
                    ORDER BY timestamp ASC
                    """,
                    (execution_id,),
                )
                return [self._row_to_event(row) for row in cur.fetchall()]

    def list_executions(
        self,
        pipeline: str | None = None,
        status: ExecutionStatus | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        """List executions with optional filters."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                query = "SELECT * FROM executions WHERE 1=1"
                params: list[Any] = []

                if pipeline:
                    query += " AND pipeline = %s"
                    params.append(pipeline)
                if status:
                    query += " AND status = %s"
                    params.append(status.value)

                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                return [self._row_to_execution(row) for row in cur.fetchall()]

    def get_metrics(self) -> dict[str, Any]:
        """Get execution metrics from ledger."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Overall counts by status
                cur.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM executions
                    GROUP BY status
                    """
                )
                status_counts = {row["status"]: row["count"] for row in cur.fetchall()}

                # Recent executions (last hour)
                cur.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM executions
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                    """
                )
                recent_count = cur.fetchone()["count"]  # type: ignore

                # Average duration for completed executions
                cur.execute(
                    """
                    SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration
                    FROM executions
                    WHERE status = 'completed' AND started_at IS NOT NULL
                    """
                )
                row = cur.fetchone()
                avg_duration = row["avg_duration"] if row else None  # type: ignore

                return {
                    "status_counts": status_counts,
                    "recent_executions_1h": recent_count,
                    "avg_duration_seconds": float(avg_duration) if avg_duration else None,
                }

    def _row_to_execution(self, row: dict[str, Any]) -> Execution:
        """Convert database row to Execution."""
        return Execution(
            id=row["id"],
            pipeline=row["pipeline"],
            params=row["params"] or {},
            status=ExecutionStatus(row["status"]),
            lane=row["lane"],
            trigger_source=TriggerSource(row["trigger_source"]),
            parent_execution_id=row["parent_execution_id"],
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            result=row.get("result"),
            error=row.get("error"),
            retry_count=row.get("retry_count", 0),
        )

    def _row_to_event(self, row: dict[str, Any]) -> ExecutionEvent:
        """Convert database row to ExecutionEvent."""
        return ExecutionEvent(
            id=row["id"],
            execution_id=row["execution_id"],
            event_type=EventType(row["event_type"]),
            timestamp=row["timestamp"],
            data=row["data"] or {},
        )
