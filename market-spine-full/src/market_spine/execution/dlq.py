"""Dead Letter Queue manager."""

from datetime import datetime
from typing import Any
import uuid

import psycopg
from psycopg.rows import dict_row

from market_spine.core.database import get_pool
from market_spine.core.models import DeadLetter, TriggerSource
from market_spine.core.settings import get_settings
from market_spine.observability.logging import get_logger
from market_spine.observability.metrics import dead_letters_counter

logger = get_logger(__name__)


class DLQManager:
    """Manages the dead letter queue for failed executions."""

    def __init__(self, conn: psycopg.Connection | None = None):
        """Initialize with optional connection."""
        self._conn = conn
        self._settings = get_settings()

    def _get_conn(self) -> psycopg.Connection:
        """Get connection from pool or use provided one."""
        if self._conn is not None:
            return self._conn
        return get_pool().connection()

    def add_to_dlq(
        self,
        execution_id: str,
        pipeline: str,
        params: dict[str, Any],
        error: str,
        retry_count: int = 0,
    ) -> DeadLetter:
        """Add a failed execution to the DLQ."""
        dlq_entry = DeadLetter(
            id=str(uuid.uuid4()),
            execution_id=execution_id,
            pipeline=pipeline,
            params=params,
            error=error,
            retry_count=retry_count,
            max_retries=self._settings.max_retries,
            created_at=datetime.utcnow(),
        )

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dead_letters (
                        id, execution_id, pipeline, params, error,
                        retry_count, max_retries, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        dlq_entry.id,
                        dlq_entry.execution_id,
                        dlq_entry.pipeline,
                        psycopg.types.json.Json(dlq_entry.params),
                        dlq_entry.error,
                        dlq_entry.retry_count,
                        dlq_entry.max_retries,
                        dlq_entry.created_at,
                    ),
                )
                conn.commit()

        logger.warning(
            "execution_added_to_dlq",
            execution_id=execution_id,
            pipeline=pipeline,
            error=error,
            retry_count=retry_count,
        )
        dead_letters_counter.labels(pipeline=pipeline).inc()
        return dlq_entry

    def get_dead_letter(self, dlq_id: str) -> DeadLetter | None:
        """Get a dead letter entry by ID."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, execution_id, pipeline, params, error,
                           retry_count, max_retries, created_at,
                           last_retry_at, resolved_at, resolved_by
                    FROM dead_letters
                    WHERE id = %s
                    """,
                    (dlq_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_dead_letter(row)

    def list_dead_letters(
        self,
        include_resolved: bool = False,
        limit: int = 100,
    ) -> list[DeadLetter]:
        """List dead letter entries."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if include_resolved:
                    cur.execute(
                        """
                        SELECT * FROM dead_letters
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM dead_letters
                        WHERE resolved_at IS NULL
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                return [self._row_to_dead_letter(row) for row in cur.fetchall()]

    def can_retry(self, dlq_id: str) -> bool:
        """Check if a dead letter can be retried."""
        entry = self.get_dead_letter(dlq_id)
        if entry is None:
            return False
        if entry.resolved_at is not None:
            return False
        return entry.retry_count < entry.max_retries

    def mark_retrying(self, dlq_id: str) -> None:
        """Mark a dead letter as being retried."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dead_letters
                    SET retry_count = retry_count + 1,
                        last_retry_at = %s
                    WHERE id = %s
                    """,
                    (datetime.utcnow(), dlq_id),
                )
                conn.commit()

    def resolve(self, dlq_id: str, resolved_by: str = "retry") -> None:
        """Mark a dead letter as resolved."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dead_letters
                    SET resolved_at = %s, resolved_by = %s
                    WHERE id = %s
                    """,
                    (datetime.utcnow(), resolved_by, dlq_id),
                )
                conn.commit()

        logger.info("dead_letter_resolved", dlq_id=dlq_id, resolved_by=resolved_by)

    def prepare_retry(self, dlq_id: str) -> tuple[str, dict[str, Any], str] | None:
        """
        Prepare retry information for a dead letter.

        Returns tuple of (pipeline, params, parent_execution_id) or None if cannot retry.
        """
        entry = self.get_dead_letter(dlq_id)
        if entry is None:
            return None
        if not self.can_retry(dlq_id):
            return None

        self.mark_retrying(dlq_id)
        return (entry.pipeline, entry.params, entry.execution_id)

    def _row_to_dead_letter(self, row: dict[str, Any]) -> DeadLetter:
        """Convert database row to DeadLetter."""
        return DeadLetter(
            id=row["id"],
            execution_id=row["execution_id"],
            pipeline=row["pipeline"],
            params=row["params"] or {},
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            last_retry_at=row.get("last_retry_at"),
            resolved_at=row.get("resolved_at"),
            resolved_by=row.get("resolved_by"),
        )
