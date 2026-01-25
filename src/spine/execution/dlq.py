"""Dead Letter Queue (DLQ) manager.

Captures failed executions for manual inspection and retry. Dead letters
persist until explicitly resolved.

Example:
    >>> from spine.execution.dlq import DLQManager
    >>> from spine.execution.models import Execution
    >>>
    >>> dlq = DLQManager(conn, max_retries=3)
    >>>
    >>> # Add a failed execution
    >>> entry = dlq.add_to_dlq(
    ...     execution_id="exec-123",
    ...     pipeline="finra.otc.ingest",
    ...     params={"week_ending": "2025-01-09"},
    ...     error="Connection timeout",
    ... )
    >>>
    >>> # Later: retry or resolve
    >>> dlq.retry(entry.id)
    >>> dlq.resolve(entry.id, resolved_by="user@example.com")
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import DeadLetter


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class DLQManager:
    """Manages the dead letter queue for failed executions.
    
    The DLQ captures executions that fail after all retries are exhausted.
    Entries can be manually retried or resolved (marked as handled).
    """

    def __init__(self, conn, max_retries: int = 3):
        """Initialize with a database connection.
        
        Args:
            conn: Database connection (sqlite3.Connection or psycopg.Connection)
            max_retries: Default max retries for new entries
        """
        self._conn = conn
        self._max_retries = max_retries

    def add_to_dlq(
        self,
        execution_id: str,
        pipeline: str,
        params: dict[str, Any],
        error: str,
        retry_count: int = 0,
        max_retries: int | None = None,
    ) -> DeadLetter:
        """Add a failed execution to the DLQ.
        
        Args:
            execution_id: Original execution ID
            pipeline: Pipeline that failed
            params: Pipeline parameters
            error: Error message/stack trace
            retry_count: How many times already retried
            max_retries: Max retries (defaults to manager default)
            
        Returns:
            Created DeadLetter entry
        """
        entry = DeadLetter(
            id=str(uuid.uuid4()),
            execution_id=execution_id,
            pipeline=pipeline,
            params=params,
            error=error,
            retry_count=retry_count,
            max_retries=max_retries or self._max_retries,
            created_at=utcnow(),
        )

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO core_dead_letters (
                id, execution_id, pipeline, params, error,
                retry_count, max_retries, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.execution_id,
                entry.pipeline,
                json.dumps(entry.params),
                entry.error,
                entry.retry_count,
                entry.max_retries,
                entry.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return entry

    def get(self, dlq_id: str) -> DeadLetter | None:
        """Get a dead letter entry by ID.
        
        Args:
            dlq_id: DLQ entry ID
            
        Returns:
            DeadLetter or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, execution_id, pipeline, params, error,
                   retry_count, max_retries, created_at,
                   last_retry_at, resolved_at, resolved_by
            FROM core_dead_letters
            WHERE id = ?
            """,
            (dlq_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dead_letter(row)

    def list_unresolved(
        self,
        pipeline: str | None = None,
        limit: int = 100,
    ) -> list[DeadLetter]:
        """List unresolved dead letter entries.
        
        Args:
            pipeline: Filter by pipeline name
            limit: Max results
            
        Returns:
            List of DeadLetter entries
        """
        cursor = self._conn.cursor()

        query = """
            SELECT id, execution_id, pipeline, params, error,
                   retry_count, max_retries, created_at,
                   last_retry_at, resolved_at, resolved_by
            FROM core_dead_letters
            WHERE resolved_at IS NULL
        """
        params: list[Any] = []

        if pipeline:
            query += " AND pipeline = ?"
            params.append(pipeline)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_dead_letter(row) for row in cursor.fetchall()]

    def list_all(
        self,
        pipeline: str | None = None,
        include_resolved: bool = True,
        limit: int = 100,
    ) -> list[DeadLetter]:
        """List all dead letter entries.
        
        Args:
            pipeline: Filter by pipeline name
            include_resolved: Include resolved entries
            limit: Max results
            
        Returns:
            List of DeadLetter entries
        """
        cursor = self._conn.cursor()

        query = """
            SELECT id, execution_id, pipeline, params, error,
                   retry_count, max_retries, created_at,
                   last_retry_at, resolved_at, resolved_by
            FROM core_dead_letters
            WHERE 1=1
        """
        params: list[Any] = []

        if pipeline:
            query += " AND pipeline = ?"
            params.append(pipeline)

        if not include_resolved:
            query += " AND resolved_at IS NULL"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_dead_letter(row) for row in cursor.fetchall()]

    def mark_retry_attempted(self, dlq_id: str) -> bool:
        """Mark that a retry was attempted.
        
        Args:
            dlq_id: DLQ entry ID
            
        Returns:
            True if updated, False if not found
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE core_dead_letters
            SET retry_count = retry_count + 1,
                last_retry_at = ?
            WHERE id = ? AND resolved_at IS NULL
            """,
            (utcnow().isoformat(), dlq_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def resolve(
        self,
        dlq_id: str,
        resolved_by: str | None = None,
    ) -> bool:
        """Mark a dead letter as resolved.
        
        Args:
            dlq_id: DLQ entry ID
            resolved_by: Who resolved it (email, system name, etc.)
            
        Returns:
            True if resolved, False if not found or already resolved
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE core_dead_letters
            SET resolved_at = ?, resolved_by = ?
            WHERE id = ? AND resolved_at IS NULL
            """,
            (utcnow().isoformat(), resolved_by, dlq_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count_unresolved(self, pipeline: str | None = None) -> int:
        """Count unresolved dead letter entries.
        
        Args:
            pipeline: Filter by pipeline name
            
        Returns:
            Count of unresolved entries
        """
        cursor = self._conn.cursor()

        if pipeline:
            cursor.execute(
                """
                SELECT COUNT(*) FROM core_dead_letters
                WHERE resolved_at IS NULL AND pipeline = ?
                """,
                (pipeline,),
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) FROM core_dead_letters
                WHERE resolved_at IS NULL
                """
            )

        row = cursor.fetchone()
        return row[0] if row else 0

    def can_retry(self, dlq_id: str) -> bool:
        """Check if a dead letter entry can be retried.
        
        Args:
            dlq_id: DLQ entry ID
            
        Returns:
            True if can retry, False otherwise
        """
        entry = self.get(dlq_id)
        if entry is None:
            return False
        return entry.can_retry()

    def cleanup_resolved(self, days: int = 90) -> int:
        """Delete resolved entries older than N days.
        
        Args:
            days: Delete entries resolved more than this many days ago
            
        Returns:
            Number of entries deleted
        """
        from datetime import timedelta

        cursor = self._conn.cursor()
        cutoff = utcnow() - timedelta(days=days)
        cursor.execute(
            """
            DELETE FROM core_dead_letters
            WHERE resolved_at IS NOT NULL AND created_at < ?
            """,
            (cutoff.isoformat(),),
        )
        self._conn.commit()
        return cursor.rowcount

    def _row_to_dead_letter(self, row: tuple) -> DeadLetter:
        """Convert a database row to a DeadLetter object."""
        return DeadLetter(
            id=row[0],
            execution_id=row[1],
            pipeline=row[2],
            params=json.loads(row[3]) if row[3] else {},
            error=row[4],
            retry_count=row[5] or 0,
            max_retries=row[6] or 3,
            created_at=datetime.fromisoformat(row[7]) if row[7] else None,
            last_retry_at=datetime.fromisoformat(row[8]) if row[8] else None,
            resolved_at=datetime.fromisoformat(row[9]) if row[9] else None,
            resolved_by=row[10],
        )
