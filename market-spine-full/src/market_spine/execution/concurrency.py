"""Concurrency guard for preventing overlapping executions."""

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from market_spine.core.database import get_pool
from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


class ConcurrencyGuard:
    """
    Guards against concurrent execution of the same pipeline/params.

    Uses database-level locking to ensure only one execution runs at a time
    for a given lock key.
    """

    def __init__(self, conn: psycopg.Connection | None = None):
        """Initialize with optional connection."""
        self._conn = conn

    def _get_conn(self) -> psycopg.Connection:
        """Get connection from pool or use provided one."""
        if self._conn is not None:
            return self._conn
        return get_pool().connection()

    def acquire(
        self,
        lock_key: str,
        execution_id: str,
        timeout_seconds: int = 3600,
    ) -> bool:
        """
        Try to acquire a lock for the given key.

        Args:
            lock_key: Unique key for the lock (e.g., "otc_backfill:2024-01-01")
            execution_id: Execution ID trying to acquire the lock
            timeout_seconds: Lock expires after this many seconds

        Returns:
            True if lock acquired, False if already locked
        """
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Try to insert lock, handle conflict
                try:
                    cur.execute(
                        """
                        INSERT INTO concurrency_locks (lock_key, execution_id, acquired_at, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (lock_key) DO UPDATE
                        SET execution_id = EXCLUDED.execution_id,
                            acquired_at = EXCLUDED.acquired_at,
                            expires_at = EXCLUDED.expires_at
                        WHERE concurrency_locks.expires_at < NOW()
                        RETURNING lock_key
                        """,
                        (
                            lock_key,
                            execution_id,
                            datetime.utcnow(),
                            datetime.utcnow().replace(
                                second=datetime.utcnow().second + timeout_seconds
                            ),
                        ),
                    )
                    result = cur.fetchone()
                    conn.commit()

                    if result:
                        logger.info(
                            "lock_acquired",
                            lock_key=lock_key,
                            execution_id=execution_id,
                        )
                        return True

                    # Check if we already hold the lock
                    cur.execute(
                        "SELECT execution_id FROM concurrency_locks WHERE lock_key = %s",
                        (lock_key,),
                    )
                    existing = cur.fetchone()
                    if existing and existing["execution_id"] == execution_id:
                        return True

                    logger.warning(
                        "lock_already_held",
                        lock_key=lock_key,
                        execution_id=execution_id,
                    )
                    return False

                except Exception as e:
                    logger.error(
                        "lock_acquisition_failed",
                        lock_key=lock_key,
                        error=str(e),
                    )
                    return False

    def release(self, lock_key: str, execution_id: str) -> bool:
        """
        Release a lock.

        Args:
            lock_key: The lock key to release
            execution_id: Must match the execution that acquired the lock

        Returns:
            True if lock was released, False otherwise
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM concurrency_locks
                    WHERE lock_key = %s AND execution_id = %s
                    """,
                    (lock_key, execution_id),
                )
                conn.commit()
                released = cur.rowcount > 0

                if released:
                    logger.info(
                        "lock_released",
                        lock_key=lock_key,
                        execution_id=execution_id,
                    )
                return released

    def is_locked(self, lock_key: str) -> bool:
        """Check if a lock key is currently locked."""
        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT execution_id FROM concurrency_locks
                    WHERE lock_key = %s AND expires_at > NOW()
                    """,
                    (lock_key,),
                )
                return cur.fetchone() is not None

    def cleanup_expired(self) -> int:
        """Clean up expired locks. Returns count of cleaned locks."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM concurrency_locks
                    WHERE expires_at < NOW()
                    """
                )
                conn.commit()
                return cur.rowcount
