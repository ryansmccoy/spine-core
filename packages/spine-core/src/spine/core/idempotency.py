"""
Idempotency helpers for pipeline execution.

Provides patterns for:
- Level 2 (Input-Idempotent): Hash-based deduplication
- Level 3 (State-Idempotent): Delete + insert patterns
"""

from enum import IntEnum
from typing import Any, Protocol


class Connection(Protocol):
    """Minimal DB connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...


class IdempotencyLevel(IntEnum):
    """
    Pipeline idempotency classification.

    L1_APPEND: Always inserts, external dedup
    L2_INPUT: Same input → same output (hash dedup)
    L3_STATE: Re-run → same final state (delete+insert)
    """

    L1_APPEND = 1
    L2_INPUT = 2
    L3_STATE = 3


class IdempotencyHelper:
    """
    Helper for idempotent pipeline patterns.

    Example:
        helper = IdempotencyHelper(conn)

        # Level 2: Check if hash exists
        if helper.hash_exists("otc_raw", "record_hash", hash_value):
            continue  # Skip duplicate

        # Level 3: Delete before insert
        helper.delete_for_key("otc_venue_volume", {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"})
        # ... insert new data ...
    """

    def __init__(self, conn: Connection):
        self.conn = conn

    def hash_exists(self, table: str, hash_column: str, hash_value: str) -> bool:
        """
        Check if record hash already exists (Level 2 dedup).

        Returns:
            True if hash exists, False otherwise
        """
        row = self.conn.execute(
            f"SELECT 1 FROM {table} WHERE {hash_column} = ? LIMIT 1", (hash_value,)
        ).fetchone()
        return row is not None

    def get_existing_hashes(self, table: str, hash_column: str) -> set[str]:
        """
        Get all existing hashes from a table.

        Useful for batch dedup before inserts.
        """
        rows = self.conn.execute(f"SELECT {hash_column} FROM {table}").fetchall()
        return {r[0] for r in rows}

    def delete_for_key(self, table: str, key: dict[str, Any]) -> int:
        """
        Delete all rows matching key (Level 3 pattern).

        Returns:
            Number of rows deleted
        """
        where = " AND ".join(f"{k} = ?" for k in key.keys())
        values = tuple(key.values())

        cursor = self.conn.execute(f"DELETE FROM {table} WHERE {where}", values)
        return cursor.rowcount

    def delete_and_count(self, table: str, key: dict[str, Any]) -> int:
        """Alias for delete_for_key."""
        return self.delete_for_key(table, key)


class LogicalKey:
    """
    Represents a domain's natural/logical key.

    Example:
        key = LogicalKey(week_ending="2025-12-26", tier="NMS_TIER_1")
        key.where_clause()  # "week_ending = ? AND tier = ?"
        key.values()        # ("2025-12-26", "NMS_TIER_1")
    """

    def __init__(self, **parts):
        self._parts = parts

    def where_clause(self) -> str:
        """SQL WHERE clause (without WHERE keyword)."""
        return " AND ".join(f"{k} = ?" for k in self._parts.keys())

    def values(self) -> tuple:
        """Parameter values for WHERE clause."""
        return tuple(self._parts.values())

    def as_dict(self) -> dict[str, Any]:
        """Key as dictionary."""
        return dict(self._parts)

    def __repr__(self) -> str:
        parts = ", ".join(f"{k}={v!r}" for k, v in self._parts.items())
        return f"LogicalKey({parts})"
