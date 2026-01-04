"""Execution repository - CRUD operations for executions and events."""

from datetime import datetime
from typing import Any

import ulid
import structlog

from market_spine.db import get_connection

logger = structlog.get_logger()


class ExecutionRepository:
    """Repository for execution CRUD operations."""

    @staticmethod
    def create(
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        logical_key: str | None = None,
    ) -> str:
        """
        Create a new execution record.

        Args:
            pipeline_name: Name of the pipeline to execute
            params: Parameters to pass to the pipeline
            logical_key: Optional unique key for concurrency control

        Returns:
            The new execution ID
        """
        execution_id = str(ulid.new())
        params = params or {}

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO executions (id, pipeline_name, params, logical_key, status)
                VALUES (%s, %s, %s, %s, 'pending')
                """,
                (execution_id, pipeline_name, params, logical_key),
            )
            conn.commit()

        logger.info(
            "execution_created",
            execution_id=execution_id,
            pipeline_name=pipeline_name,
            logical_key=logical_key,
        )

        return execution_id

    @staticmethod
    def get(execution_id: str) -> dict | None:
        """Get an execution by ID."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, pipeline_name, params, logical_key, status, backend,
                       backend_run_id, parent_execution_id, created_at, started_at,
                       completed_at, error_message
                FROM executions
                WHERE id = %s
                """,
                (execution_id,),
            )
            row = result.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_executions(
        status: str | None = None,
        pipeline_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List executions with optional filters."""
        conditions = []
        params = []

        if status:
            conditions.append("status = %s")
            params.append(status)
        if pipeline_name:
            conditions.append("pipeline_name = %s")
            params.append(pipeline_name)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with get_connection() as conn:
            result = conn.execute(
                f"""
                SELECT id, pipeline_name, status, backend, created_at, 
                       started_at, completed_at
                FROM executions
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            )
            return [dict(row) for row in result.fetchall()]

    @staticmethod
    def update_status(
        execution_id: str,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """Update execution status."""
        with get_connection() as conn:
            if status == "running":
                result = conn.execute(
                    """
                    UPDATE executions 
                    SET status = %s, started_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (status, execution_id),
                )
            elif status in ("completed", "failed", "cancelled"):
                result = conn.execute(
                    """
                    UPDATE executions 
                    SET status = %s, completed_at = NOW(), error_message = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (status, error_message, execution_id),
                )
            else:
                result = conn.execute(
                    """
                    UPDATE executions 
                    SET status = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (status, execution_id),
                )

            updated = result.fetchone() is not None
            conn.commit()

            if updated:
                logger.info(
                    "execution_status_updated",
                    execution_id=execution_id,
                    status=status,
                )

            return updated

    @staticmethod
    def set_backend(execution_id: str, backend: str, backend_run_id: str | None = None) -> bool:
        """Set the backend for an execution."""
        with get_connection() as conn:
            result = conn.execute(
                """
                UPDATE executions 
                SET backend = %s, backend_run_id = %s
                WHERE id = %s
                RETURNING id
                """,
                (backend, backend_run_id, execution_id),
            )
            updated = result.fetchone() is not None
            conn.commit()
            return updated

    @staticmethod
    def check_logical_key_conflict(logical_key: str) -> str | None:
        """
        Check if an active execution exists for the given logical key.

        Returns:
            The existing execution ID if conflict exists, None otherwise
        """
        if not logical_key:
            return None

        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id FROM executions
                WHERE logical_key = %s 
                  AND status IN ('pending', 'queued', 'running')
                LIMIT 1
                """,
                (logical_key,),
            )
            row = result.fetchone()
            return row["id"] if row else None


class ExecutionEventRepository:
    """Repository for execution event operations."""

    @staticmethod
    def emit(
        execution_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> str | None:
        """
        Emit an execution event.

        Args:
            execution_id: The execution this event belongs to
            event_type: Type of event (e.g., 'stage_started', 'stage_completed')
            payload: Event payload data
            idempotency_key: Optional key for deduplication

        Returns:
            Event ID if created, None if deduplicated
        """
        event_id = str(ulid.new())
        payload = payload or {}

        with get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO execution_events (id, execution_id, event_type, payload, idempotency_key)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (event_id, execution_id, event_type, payload, idempotency_key),
                )
                conn.commit()
                return event_id
            except Exception as e:
                # Likely duplicate idempotency_key
                if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                    logger.debug("event_deduplicated", idempotency_key=idempotency_key)
                    conn.rollback()
                    return None
                raise

    @staticmethod
    def get_events(execution_id: str) -> list[dict]:
        """Get all events for an execution."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, execution_id, event_type, payload, created_at
                FROM execution_events
                WHERE execution_id = %s
                ORDER BY created_at
                """,
                (execution_id,),
            )
            return [dict(row) for row in result.fetchall()]
