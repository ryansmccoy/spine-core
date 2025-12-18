"""Execution ledger - persistent record of all executions and events.

The ExecutionLedger provides CRUD operations for executions and events,
backed by SQLite or PostgreSQL. It's the single source of truth for
execution state.
Architecture:

    .. code-block:: text

        ExecutionLedger — Single Source of Truth
        ┌───────────────────────────────────────────────────────────┐
        │                                                           │
        │  EXECUTION CRUD            EVENT RECORDING                │
        │  ─────────────             ────────────────                │
        │  create_execution()        record_event()                 │
        │  get_execution()           get_events()                   │
        │  get_by_idempotency_key()                                 │
        │  update_status()           Status→Event mapping:          │
        │  increment_retry()         PENDING  → CREATED             │
        │  list_executions()         RUNNING  → STARTED             │
        │                            COMPLETED→ COMPLETED           │
        │                            FAILED   → FAILED              │
        │                            TIMED_OUT→ TIMED_OUT           │
        │                                                           │
        ├───────────────────────────────────────────────────────────┤
        │  Tables:                                                  │
        │  ┌──────────────────┐     ┌──────────────────────────┐   │
        │  │ core_executions  │────>│ core_execution_events    │   │
        │  │ (state machine)  │     │ (append-only event log)  │   │
        │  └──────────────────┘     └──────────────────────────┘   │
        └───────────────────────────────────────────────────────────┘

    .. mermaid::

        erDiagram
            core_executions {
                text id PK
                text workflow
                text params
                text status
                text lane
                text trigger_source
                text parent_execution_id
                text created_at
                text started_at
                text completed_at
                text result
                text error
                int retry_count
                text idempotency_key
            }
            core_execution_events {
                text id PK
                text execution_id FK
                text event_type
                text timestamp
                text data
            }
            core_executions ||--o{ core_execution_events : "emits"
Example:
    >>> from spine.execution.ledger import ExecutionLedger
    >>> from spine.execution.models import Execution, EventType
    >>>
    >>> ledger = ExecutionLedger(conn)
    >>> execution = Execution.create(workflow="finra.otc.ingest")
    >>> ledger.create_execution(execution)
    >>> ledger.record_event(execution.id, EventType.STARTED)
"""

import json
from datetime import UTC, datetime
from typing import Any

from .models import (
    EventType,
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    TriggerSource,
)


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class ExecutionLedger:
    """Manages the execution ledger (executions + events).

    Provides CRUD operations for:
    - Executions (create, read, update status, list)
    - Events (record, list by execution)

    Works with SQLite (sqlite3 connection) or PostgreSQL (psycopg connection).
    """

    def __init__(self, conn):
        """Initialize with a database connection.

        Args:
            conn: Database connection (sqlite3.Connection or psycopg.Connection)
        """
        self._conn = conn

    # =========================================================================
    # EXECUTION CRUD
    # =========================================================================

    def create_execution(self, execution: Execution) -> Execution:
        """Create a new execution record.

        Args:
            execution: Execution to persist

        Returns:
            The same execution (for chaining)
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO core_executions (
                id, workflow, params, status, lane, trigger_source,
                parent_execution_id, created_at, retry_count, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.id,
                execution.workflow,
                json.dumps(execution.params),
                execution.status.value,
                execution.lane,
                execution.trigger_source.value,
                execution.parent_execution_id,
                execution.created_at.isoformat(),
                execution.retry_count,
                execution.idempotency_key,
            ),
        )
        self._conn.commit()

        # Record creation event
        self.record_event(execution.id, EventType.CREATED, {"workflow": execution.workflow})
        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        """Get execution by ID.

        Args:
            execution_id: Execution UUID

        Returns:
            Execution or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, workflow, params, status, lane, trigger_source,
                   parent_execution_id, created_at, started_at, completed_at,
                   result, error, retry_count, idempotency_key
            FROM core_executions
            WHERE id = ?
            """,
            (execution_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_execution(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> Execution | None:
        """Find execution by idempotency key.

        Args:
            idempotency_key: Unique idempotency key

        Returns:
            Execution or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, workflow, params, status, lane, trigger_source,
                   parent_execution_id, created_at, started_at, completed_at,
                   result, error, retry_count, idempotency_key
            FROM core_executions
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()
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
        """Update execution status.

        Args:
            execution_id: Execution UUID
            status: New status
            result: Optional result data (for COMPLETED)
            error: Optional error message (for FAILED)
        """
        cursor = self._conn.cursor()
        now = utcnow()

        # Determine which timestamp to update
        if status == ExecutionStatus.RUNNING:
            cursor.execute(
                """
                UPDATE core_executions
                SET status = ?, started_at = ?
                WHERE id = ?
                """,
                (status.value, now.isoformat(), execution_id),
            )
        elif status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ):
            cursor.execute(
                """
                UPDATE core_executions
                SET status = ?, completed_at = ?, result = ?, error = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    now.isoformat(),
                    json.dumps(result) if result else None,
                    error,
                    execution_id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE core_executions
                SET status = ?
                WHERE id = ?
                """,
                (status.value, execution_id),
            )

        self._conn.commit()

        # Record event - map status to corresponding event type
        status_to_event = {
            ExecutionStatus.PENDING: EventType.CREATED,
            ExecutionStatus.QUEUED: EventType.QUEUED,
            ExecutionStatus.RUNNING: EventType.STARTED,
            ExecutionStatus.COMPLETED: EventType.COMPLETED,
            ExecutionStatus.FAILED: EventType.FAILED,
            ExecutionStatus.CANCELLED: EventType.CANCELLED,
            ExecutionStatus.TIMED_OUT: EventType.TIMED_OUT,
        }
        event_type = status_to_event.get(status, EventType.PROGRESS)
        self.record_event(execution_id, event_type, {"result": result, "error": error})

    def increment_retry(self, execution_id: str) -> int:
        """Increment retry count and return new value.

        Args:
            execution_id: Execution UUID

        Returns:
            New retry count
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE core_executions
            SET retry_count = retry_count + 1
            WHERE id = ?
            """,
            (execution_id,),
        )
        self._conn.commit()

        # Get new count
        cursor.execute(
            "SELECT retry_count FROM core_executions WHERE id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()
        count = row[0] if row else 0

        self.record_event(execution_id, EventType.RETRIED, {"retry_count": count})
        return count

    def list_executions(
        self,
        workflow: str | None = None,
        status: ExecutionStatus | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[Execution]:
        """List executions with optional filters.

        Args:
            workflow: Filter by workflow name
            status: Filter by status
            limit: Max results
            since: Only executions created after this time

        Returns:
            List of Execution objects
        """
        cursor = self._conn.cursor()

        query = """
            SELECT id, workflow, params, status, lane, trigger_source,
                   parent_execution_id, created_at, started_at, completed_at,
                   result, error, retry_count, idempotency_key
            FROM core_executions
            WHERE 1=1
        """
        params: list[Any] = []

        if workflow:
            query += " AND workflow = ?"
            params.append(workflow)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if since:
            query += " AND created_at > ?"
            params.append(since.isoformat())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_execution(row) for row in cursor.fetchall()]

    # =========================================================================
    # EVENT RECORDING
    # =========================================================================

    def record_event(
        self,
        execution_id: str,
        event_type: "EventType | str",
        data: dict[str, Any] | None = None,
    ) -> ExecutionEvent:
        """Record an execution event.

        Args:
            execution_id: Execution UUID
            event_type: Type of event (EventType enum or string constant)
            data: Optional event data

        Returns:
            Created ExecutionEvent
        """
        event = ExecutionEvent.create(execution_id, event_type, data)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO core_execution_events (id, execution_id, event_type, timestamp, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.execution_id,
                event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                event.timestamp.isoformat(),
                json.dumps(event.data),
            ),
        )
        self._conn.commit()
        return event

    def get_events(self, execution_id: str) -> list[ExecutionEvent]:
        """Get all events for an execution.

        Args:
            execution_id: Execution UUID

        Returns:
            List of ExecutionEvent objects in chronological order
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, execution_id, event_type, timestamp, data
            FROM core_execution_events
            WHERE execution_id = ?
            ORDER BY timestamp ASC
            """,
            (execution_id,),
        )
        return [self._row_to_event(row) for row in cursor.fetchall()]

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _row_to_execution(self, row: tuple) -> Execution:
        """Convert a database row to an Execution object."""
        return Execution(
            id=row[0],
            workflow=row[1],
            params=json.loads(row[2]) if row[2] else {},
            status=ExecutionStatus(row[3]),
            lane=row[4],
            trigger_source=TriggerSource(row[5]),
            parent_execution_id=row[6],
            created_at=datetime.fromisoformat(row[7]) if row[7] else None,
            started_at=datetime.fromisoformat(row[8]) if row[8] else None,
            completed_at=datetime.fromisoformat(row[9]) if row[9] else None,
            result=json.loads(row[10]) if row[10] else None,
            error=row[11],
            retry_count=row[12] or 0,
            idempotency_key=row[13],
        )

    def _row_to_event(self, row: tuple) -> ExecutionEvent:
        """Convert a database row to an ExecutionEvent object."""
        return ExecutionEvent(
            id=row[0],
            execution_id=row[1],
            event_type=EventType(row[2]),
            timestamp=datetime.fromisoformat(row[3]) if row[3] else None,
            data=json.loads(row[4]) if row[4] else {},
        )
