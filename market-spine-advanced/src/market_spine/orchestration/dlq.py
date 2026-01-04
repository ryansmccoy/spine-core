"""Dead Letter Queue (DLQ) management."""

from datetime import datetime, timedelta
from typing import Any

import ulid
import structlog
from psycopg.types.json import Json

from market_spine.db import get_connection

logger = structlog.get_logger()


class DLQManager:
    """
    Dead Letter Queue manager for failed executions.

    Handles:
    - Moving failed executions to DLQ
    - Listing DLQ items
    - Retrying executions (creates new execution with parent link)
    - DLQ cleanup

    All methods are class methods for convenient static access.
    """

    @classmethod
    def move_to_dlq(cls, execution_id: str, error_message: str | None = None) -> bool:
        """
        Move an execution to the DLQ.

        Returns:
            True if moved successfully
        """
        with get_connection() as conn:
            result = conn.execute(
                """
                UPDATE executions
                SET status = 'dlq', error_message = COALESCE(%s, error_message), completed_at = NOW()
                WHERE id = %s AND status NOT IN ('dlq', 'completed', 'retried')
                RETURNING id
                """,
                (error_message, execution_id),
            )

            if result.fetchone():
                conn.commit()
                logger.info("execution_moved_to_dlq", execution_id=execution_id)
                return True

            return False

    @classmethod
    def list_dlq(
        cls,
        pipeline_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List executions in the DLQ."""
        conditions = ["status = 'dlq'"]
        params: list = []

        if pipeline_name:
            conditions.append("pipeline_name = %s")
            params.append(pipeline_name)

        where_clause = " AND ".join(conditions)

        with get_connection() as conn:
            result = conn.execute(
                f"""
                SELECT id, pipeline_name, params, error_message, 
                       retry_count, max_retries, created_at, completed_at
                FROM executions
                WHERE {where_clause}
                ORDER BY completed_at DESC
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            )
            return [dict(row) for row in result.fetchall()]

    @classmethod
    def retry(cls, execution_id: str) -> str | None:
        """
        Retry a DLQ execution.

        Creates a NEW execution with parent_execution_id pointing to the failed one.
        This preserves the audit trail.

        Returns:
            New execution ID, or None if cannot retry
        """
        with get_connection() as conn:
            # Get the failed execution
            result = conn.execute(
                """
                SELECT id, pipeline_name, params, retry_count, max_retries
                FROM executions
                WHERE id = %s AND status = 'dlq'
                """,
                (execution_id,),
            )
            row = result.fetchone()

            if not row:
                logger.warning("dlq_retry_not_found", execution_id=execution_id)
                return None

            # Check retry limit
            if row["retry_count"] >= row["max_retries"]:
                logger.warning(
                    "dlq_retry_limit_exceeded",
                    execution_id=execution_id,
                    retry_count=row["retry_count"],
                    max_retries=row["max_retries"],
                )
                return None

            # Create new execution
            new_id = str(ulid.new())
            new_retry_count = row["retry_count"] + 1

            conn.execute(
                """
                INSERT INTO executions (
                    id, pipeline_name, params, parent_execution_id,
                    retry_count, max_retries, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                """,
                (
                    new_id,
                    row["pipeline_name"],
                    Json(row["params"]) if row["params"] else None,
                    execution_id,
                    new_retry_count,
                    row["max_retries"],
                ),
            )

            # Update original execution status to 'retried'
            conn.execute(
                """
                UPDATE executions
                SET status = 'retried', retry_count = %s
                WHERE id = %s
                """,
                (new_retry_count, execution_id),
            )

            conn.commit()

            logger.info(
                "dlq_retry_created",
                original_id=execution_id,
                new_id=new_id,
                retry_count=new_retry_count,
            )

            return new_id

    @classmethod
    def get_retryable(cls, limit: int = 100) -> list[dict]:
        """
        Get DLQ items that can be retried (retry_count < max_retries).

        Returns:
            List of retryable DLQ executions
        """
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, pipeline_name, params, error_message,
                       retry_count, max_retries, created_at, completed_at
                FROM executions
                WHERE status = 'dlq' AND retry_count < max_retries
                ORDER BY completed_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in result.fetchall()]

    @classmethod
    def auto_retry(cls, limit: int = 100) -> int:
        """
        Automatically retry all eligible DLQ executions.

        Returns:
            Number of executions retried
        """
        retryable = cls.get_retryable(limit=limit)
        retried_count = 0

        for item in retryable:
            new_id = cls.retry(item["id"])
            if new_id:
                retried_count += 1

        logger.info("auto_retry_complete", count=retried_count)
        return retried_count

    @classmethod
    def retry_all(cls, pipeline_name: str | None = None) -> dict[str, Any]:
        """
        Retry all eligible DLQ executions.

        Returns:
            Summary of retry results
        """
        dlq_items = cls.list_dlq(pipeline_name=pipeline_name, limit=1000)

        retried = 0
        skipped = 0
        new_ids = []

        for item in dlq_items:
            if item["retry_count"] >= item["max_retries"]:
                skipped += 1
                continue

            new_id = cls.retry(item["id"])
            if new_id:
                retried += 1
                new_ids.append(new_id)
            else:
                skipped += 1

        logger.info("dlq_retry_all_complete", retried=retried, skipped=skipped)

        return {
            "retried": retried,
            "skipped": skipped,
            "new_execution_ids": new_ids,
        }

    @classmethod
    def purge(cls, older_than_days: int = 30) -> int:
        """
        Purge old DLQ executions.

        Returns:
            Number of executions purged
        """
        cutoff = datetime.now() - timedelta(days=older_than_days)

        with get_connection() as conn:
            result = conn.execute(
                """
                DELETE FROM executions
                WHERE status = 'dlq' AND completed_at < %s
                RETURNING id
                """,
                (cutoff,),
            )
            deleted = len(result.fetchall())
            conn.commit()

        logger.info("dlq_purged", deleted=deleted, older_than_days=older_than_days)
        return deleted

    @classmethod
    def get_stats(cls) -> dict[str, Any]:
        """Get DLQ statistics."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE retry_count >= max_retries) as exhausted,
                    COUNT(*) FILTER (WHERE retry_count < max_retries) as retriable
                FROM executions
                WHERE status = 'dlq'
                """,
            )
            row = result.fetchone()

            # By pipeline
            result = conn.execute(
                """
                SELECT pipeline_name, COUNT(*) as count
                FROM executions
                WHERE status = 'dlq'
                GROUP BY pipeline_name
                ORDER BY count DESC
                """,
            )
            by_pipeline = {r["pipeline_name"]: r["count"] for r in result.fetchall()}

        return {
            "total": row["total"],
            "exhausted": row["exhausted"],
            "retriable": row["retriable"],
            "by_pipeline": by_pipeline,
        }
