"""Distributed lock manager for scheduler.

Manifesto:
    Multiple scheduler instances must never execute the same schedule
    simultaneously.  The lock manager provides atomic acquire/release
    with TTL-based auto-expiry so crashed instances don't cause permanent
    deadlocks.  INSERT-or-fail semantics give O(1) conflict detection.

This module provides atomic lock acquire/release for schedules, enabling
safe distributed scheduler deployments.

Tags:
    spine-core, scheduling, distributed-locks, TTL, concurrency, safety

Doc-Types:
    api-reference, architecture-diagram


    Lock Manager Architecture::

        Distributed Lock Flow: Instance A acquires lock, Instance B
        gets CONFLICT and skips. Locks auto-expire via TTL.

        Lock Types:
            1. Schedule Lock - Prevents double-execution
            2. Concurrency Lock - General-purpose resource locking
        TTL: Locks auto-expire after ttl_seconds to prevent deadlocks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from spine.core.dialect import Dialect, SQLiteDialect
from spine.core.protocols import Connection

logger = logging.getLogger(__name__)


class LockManager:
    """Distributed lock manager for scheduler and concurrency control.

    Uses database-backed locks with TTL for distributed safety.

    Example:
        >>> manager = LockManager(conn, instance_id="scheduler-1")
        >>>
        >>> # Try to acquire lock
        >>> if manager.acquire_schedule_lock("schedule-123"):
        ...     try:
        ...         # Execute schedule
        ...         pass
        ...     finally:
        ...         manager.release_schedule_lock("schedule-123")
        ... else:
        ...     print("Another instance has the lock")
    """

    def __init__(
        self,
        conn: Connection,
        dialect: Dialect = SQLiteDialect(),
        instance_id: str | None = None,
    ) -> None:
        """Initialize lock manager.

        Args:
            conn: Database connection
            dialect: SQL dialect for portable queries
            instance_id: Unique identifier for this scheduler instance.
                        Auto-generated if not provided.
        """
        self.conn = conn
        self.dialect = dialect
        self.instance_id = instance_id or str(uuid4())

    def _ph(self, index: int) -> str:
        """Generate dialect-specific placeholder at 1-based position."""
        return self.dialect.placeholder(index - 1)  # Convert to 0-based

    # === Schedule Locks ===

    def acquire_schedule_lock(
        self,
        schedule_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Acquire exclusive lock for a schedule.

        Uses INSERT ... ON CONFLICT DO NOTHING pattern for atomicity.

        Args:
            schedule_id: Schedule to lock
            ttl_seconds: Lock expiry (default: 5 minutes)

        Returns:
            True if lock acquired, False if already locked
        """
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl_seconds)

        try:
            # First, try to clean up any expired lock for this schedule
            self.conn.execute(
                f"""
                DELETE FROM core_schedule_locks
                WHERE schedule_id = {self._ph(1)} AND expires_at < {self._ph(2)}
                """,
                (schedule_id, now.isoformat()),
            )

            # Try to insert lock
            insert_sql = self.dialect.insert_or_ignore(
                "core_schedule_locks",
                ["schedule_id", "locked_by", "locked_at", "expires_at"],
            )
            cursor = self.conn.execute(
                insert_sql,
                (
                    schedule_id,
                    self.instance_id,
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
            self.conn.commit()

            if cursor.rowcount > 0:
                logger.debug(f"Acquired lock for schedule {schedule_id}")
                return True

            # Check if we already hold the lock
            cursor = self.conn.execute(
                f"""
                SELECT locked_by FROM core_schedule_locks
                WHERE schedule_id = {self._ph(1)} AND locked_by = {self._ph(2)}
                """,
                (schedule_id, self.instance_id),
            )
            if cursor.fetchone():
                # Refresh lock expiry
                self.conn.execute(
                    f"""
                    UPDATE core_schedule_locks
                    SET expires_at = {self._ph(1)}
                    WHERE schedule_id = {self._ph(2)} AND locked_by = {self._ph(3)}
                    """,
                    (expires.isoformat(), schedule_id, self.instance_id),
                )
                self.conn.commit()
                logger.debug(f"Refreshed lock for schedule {schedule_id}")
                return True

            logger.debug(f"Lock already held for schedule {schedule_id}")
            return False

        except Exception as e:
            logger.error(f"Lock acquire failed: {e}")
            return False

    def release_schedule_lock(self, schedule_id: str) -> bool:
        """Release schedule lock.

        Only releases lock if held by this instance.

        Args:
            schedule_id: Schedule to unlock

        Returns:
            True if released, False if not held
        """
        try:
            cursor = self.conn.execute(
                f"""
                DELETE FROM core_schedule_locks
                WHERE schedule_id = {self._ph(1)} AND locked_by = {self._ph(2)}
                """,
                (schedule_id, self.instance_id),
            )
            self.conn.commit()

            if cursor.rowcount > 0:
                logger.debug(f"Released lock for schedule {schedule_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Lock release failed: {e}")
            return False

    def is_locked(self, schedule_id: str) -> bool:
        """Check if schedule is locked (by any instance).

        Args:
            schedule_id: Schedule to check

        Returns:
            True if locked, False otherwise
        """
        now = datetime.now(UTC)
        cursor = self.conn.execute(
            f"""
            SELECT 1 FROM core_schedule_locks
            WHERE schedule_id = {self._ph(1)} AND expires_at > {self._ph(2)}
            """,
            (schedule_id, now.isoformat()),
        )
        return cursor.fetchone() is not None

    def get_lock_holder(self, schedule_id: str) -> str | None:
        """Get the instance holding the lock.

        Args:
            schedule_id: Schedule to check

        Returns:
            Instance ID if locked, None otherwise
        """
        now = datetime.now(UTC)
        cursor = self.conn.execute(
            f"""
            SELECT locked_by FROM core_schedule_locks
            WHERE schedule_id = {self._ph(1)} AND expires_at > {self._ph(2)}
            """,
            (schedule_id, now.isoformat()),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    # === General Concurrency Locks ===

    def acquire_concurrency_lock(
        self,
        resource_type: str,
        resource_name: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Acquire general-purpose concurrency lock.

        Uses a synthetic "schedule_id" based on resource type/name.

        Args:
            resource_type: Type of resource (e.g., "operation", "workflow")
            resource_name: Name of resource
            ttl_seconds: Lock expiry

        Returns:
            True if acquired, False if locked
        """
        lock_id = f"{resource_type}:{resource_name}"
        return self.acquire_schedule_lock(lock_id, ttl_seconds)

    def release_concurrency_lock(
        self,
        resource_type: str,
        resource_name: str,
    ) -> bool:
        """Release general-purpose concurrency lock.

        Args:
            resource_type: Type of resource
            resource_name: Name of resource

        Returns:
            True if released, False otherwise
        """
        lock_id = f"{resource_type}:{resource_name}"
        return self.release_schedule_lock(lock_id)

    # === Maintenance ===

    def cleanup_expired_locks(self) -> int:
        """Remove all expired locks.

        Should be called periodically to clean up stale locks from
        crashed instances.

        Returns:
            Number of locks removed
        """
        now = datetime.now(UTC)
        cursor = self.conn.execute(
            f"""
            DELETE FROM core_schedule_locks
            WHERE expires_at < {self._ph(1)}
            """,
            (now.isoformat(),),
        )
        self.conn.commit()

        count = cursor.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} expired locks")
        return count

    def list_active_locks(self) -> list[dict]:
        """List all active (non-expired) locks.

        Returns:
            List of lock dictionaries
        """
        now = datetime.now(UTC)
        cursor = self.conn.execute(
            f"""
            SELECT schedule_id, locked_by, locked_at, expires_at
            FROM core_schedule_locks
            WHERE expires_at > {self._ph(1)}
            ORDER BY locked_at
            """,
            (now.isoformat(),),
        )
        return [
            {
                "schedule_id": row[0],
                "locked_by": row[1],
                "locked_at": row[2],
                "expires_at": row[3],
            }
            for row in cursor.fetchall()
        ]

    def force_release_all(self) -> int:
        """Force release all locks (use with caution!).

        Only use for recovery or testing.

        Returns:
            Number of locks released
        """
        cursor = self.conn.execute("DELETE FROM core_schedule_locks")
        self.conn.commit()
        count = cursor.rowcount
        logger.warning(f"Force released {count} locks")
        return count
