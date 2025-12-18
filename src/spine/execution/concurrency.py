"""Concurrency Guard — DB-level locking to prevent duplicate runs.

WHY
───
If two workers pick up the same pipeline+params (e.g. both try to
ingest ``finra.otc:2025-01-09``), the second run wastes resources and
can corrupt data.  ConcurrencyGuard uses database-level advisory
locking with automatic expiry so that even if a process crashes, the
lock self-heals.

ARCHITECTURE
────────────
::

    ConcurrencyGuard(conn)
      ├── .acquire(key, execution_id)  ─ try-lock with timeout
      ├── .release(key)                ─ explicit unlock
      ├── .is_locked(key)              ─ check without acquiring
      ├── .cleanup_expired()           ─ reap stale locks
      └── .list_active()               ─ list all held locks

    Lock key convention: “pipeline_name:partition_key”
      e.g. "finra.otc.ingest:2025-01-09"

BEST PRACTICES
──────────────
- Always release in a ``finally`` (or use BatchExecutor which
  handles this automatically).
- Set ``lock_timeout`` to slightly longer than the longest expected run.

Related modules:
    ledger.py  — persists the lock records
    batch.py   — uses ConcurrencyGuard internally

Example::

    guard = ConcurrencyGuard(conn)
    key = "finra.otc.ingest:2025-01-09"
    if guard.acquire(key, execution_id="exec-123"):
        try:
            run_pipeline()
        finally:
            guard.release(key)
"""

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class ConcurrencyGuard:
    """Guards against concurrent execution of the same pipeline/params.

    Uses database-level locking with automatic expiry. If a process crashes,
    the lock will automatically expire after the timeout.

    Lock keys should be unique per pipeline+params combination:
    - "finra.otc.ingest:2025-01-09" for weekly data
    - "finra.otc.ingest:2025-01-09:NMS_TIER_1" for tier-specific
    """

    def __init__(self, conn):
        """Initialize with a database connection.

        Args:
            conn: Database connection (sqlite3.Connection or psycopg.Connection)
        """
        self._conn = conn

    def acquire(
        self,
        lock_key: str,
        execution_id: str,
        timeout_seconds: int = 3600,
    ) -> bool:
        """Try to acquire a lock.

        Args:
            lock_key: Unique key for the lock (e.g., "pipeline:params_hash")
            execution_id: Execution ID trying to acquire the lock
            timeout_seconds: Lock expires after this many seconds (default: 1 hour)

        Returns:
            True if lock acquired, False if already locked by another execution
        """
        now = utcnow()
        expires_at = now + timedelta(seconds=timeout_seconds)
        cursor = self._conn.cursor()

        # First, clean up expired locks
        cursor.execute(
            """
            DELETE FROM core_concurrency_locks
            WHERE lock_key = ? AND expires_at < ?
            """,
            (lock_key, now.isoformat()),
        )

        # Try to insert new lock
        try:
            cursor.execute(
                """
                INSERT INTO core_concurrency_locks (lock_key, execution_id, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    lock_key,
                    execution_id,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            self._conn.commit()
            return True
        except Exception:
            # Lock already exists - check if we own it
            self._conn.rollback()
            cursor.execute(
                """
                SELECT execution_id FROM core_concurrency_locks
                WHERE lock_key = ?
                """,
                (lock_key,),
            )
            row = cursor.fetchone()
            if row and row[0] == execution_id:
                # We already hold the lock, extend it
                cursor.execute(
                    """
                    UPDATE core_concurrency_locks
                    SET expires_at = ?
                    WHERE lock_key = ? AND execution_id = ?
                    """,
                    (expires_at.isoformat(), lock_key, execution_id),
                )
                self._conn.commit()
                return True
            return False

    def release(self, lock_key: str, execution_id: str | None = None) -> bool:
        """Release a lock.

        Args:
            lock_key: Lock key to release
            execution_id: Optional execution ID (only release if we own it)

        Returns:
            True if lock was released, False otherwise
        """
        cursor = self._conn.cursor()

        if execution_id:
            cursor.execute(
                """
                DELETE FROM core_concurrency_locks
                WHERE lock_key = ? AND execution_id = ?
                """,
                (lock_key, execution_id),
            )
        else:
            cursor.execute(
                """
                DELETE FROM core_concurrency_locks
                WHERE lock_key = ?
                """,
                (lock_key,),
            )

        self._conn.commit()
        return cursor.rowcount > 0

    def is_locked(self, lock_key: str) -> bool:
        """Check if a lock is currently held.

        Args:
            lock_key: Lock key to check

        Returns:
            True if locked (and not expired), False otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT execution_id, expires_at FROM core_concurrency_locks
            WHERE lock_key = ?
            """,
            (lock_key,),
        )
        row = cursor.fetchone()
        if row is None:
            return False

        expires_at = datetime.fromisoformat(row[1])
        if expires_at < utcnow():
            # Lock expired, clean it up
            self.release(lock_key)
            return False

        return True

    def get_lock_holder(self, lock_key: str) -> str | None:
        """Get the execution ID holding a lock.

        Args:
            lock_key: Lock key to check

        Returns:
            Execution ID or None if not locked
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT execution_id, expires_at FROM core_concurrency_locks
            WHERE lock_key = ?
            """,
            (lock_key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        expires_at = datetime.fromisoformat(row[1])
        if expires_at < utcnow():
            return None

        return row[0]

    def extend_lock(self, lock_key: str, execution_id: str, timeout_seconds: int = 3600) -> bool:
        """Extend a lock's expiration time.

        Args:
            lock_key: Lock key to extend
            execution_id: Execution ID (must own the lock)
            timeout_seconds: New timeout from now

        Returns:
            True if extended, False if lock not owned
        """
        cursor = self._conn.cursor()
        expires_at = utcnow() + timedelta(seconds=timeout_seconds)

        cursor.execute(
            """
            UPDATE core_concurrency_locks
            SET expires_at = ?
            WHERE lock_key = ? AND execution_id = ?
            """,
            (expires_at.isoformat(), lock_key, execution_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def cleanup_expired(self) -> int:
        """Clean up all expired locks.

        Returns:
            Number of locks cleaned up
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            DELETE FROM core_concurrency_locks
            WHERE expires_at < ?
            """,
            (utcnow().isoformat(),),
        )
        self._conn.commit()
        return cursor.rowcount

    def list_active_locks(self) -> list[dict]:
        """List all active (non-expired) locks.

        Returns:
            List of lock info dicts
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT lock_key, execution_id, acquired_at, expires_at
            FROM core_concurrency_locks
            WHERE expires_at > ?
            ORDER BY acquired_at DESC
            """,
            (utcnow().isoformat(),),
        )
        return [
            {
                "lock_key": row[0],
                "execution_id": row[1],
                "acquired_at": row[2],
                "expires_at": row[3],
            }
            for row in cursor.fetchall()
        ]
