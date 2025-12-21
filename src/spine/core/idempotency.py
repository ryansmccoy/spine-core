"""
Idempotency helpers for operation execution.

Provides patterns for ensuring operations produce consistent results on re-run:
- Level 1 (Append): Always inserts, external deduplication
- Level 2 (Input-Idempotent): Hash-based deduplication
- Level 3 (State-Idempotent): Delete + insert patterns

Manifesto:
    Financial data operations must be re-runnable without creating duplicates.
    When a operation fails halfway through a 6-week backfill, operators need to
    re-run it safely. Without idempotency, re-runs create:
    - Duplicate records (inflate volumes)
    - Conflicting versions (which is correct?)
    - Failed constraints (unique violations)

    spine-core defines three idempotency levels:

    **L1_APPEND:** Raw capture layer. Always insert, let downstream dedup.
        Use case: Audit logs, event streams, raw API responses

    **L2_INPUT:** Hash-based dedup. Same input hash → skip insert.
        Use case: Bronze layer where source data has no natural key

    **L3_STATE:** Delete + insert. Same logical key → delete old, insert new.
        Use case: Aggregations, derived tables, any table with natural keys

Architecture:
    ::

        ┌───────────────────────────────────────────────────────────┐
        │                Idempotency Level Progression              │
        └───────────────────────────────────────────────────────────┘

        L1_APPEND (Raw)        L2_INPUT (Dedup)       L3_STATE (Derived)
        ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
        │ INSERT all  │   →    │ Hash check  │   →    │ DELETE key  │
        │ No checks   │        │ Skip if     │        │ INSERT new  │
        │             │        │ exists      │        │             │
        └─────────────┘        └─────────────┘        └─────────────┘
              ↓                      ↓                      ↓
        audit_log            bronze_otc_raw         silver_otc_volume

        L3_STATE Pattern (most common):
        ┌─────────────────────────────────────────────────────────┐
        │ BEGIN TRANSACTION                                        │
        │   DELETE FROM silver_otc WHERE week='2025-12-26'        │
        │                           AND tier='NMS_TIER_1'         │
        │   INSERT INTO silver_otc (week, tier, volume) VALUES... │
        │ COMMIT                                                   │
        └─────────────────────────────────────────────────────────┘

Context:
    Problem: Re-running financial data operations creates duplicates, conflicting
        versions, or constraint violations without systematic idempotency.
    Solution: Three-level idempotency framework (L1 Append, L2 Input Hash,
        L3 State Delete+Insert) with clear guidance on when to use each.
    Alternatives Considered: Database UPSERT only (doesn't handle all cases),
        event sourcing (too complex for batch), external dedup service
        (unnecessary dependency).

Tags:
    idempotency, operation, deduplication, delete-insert, spine-core,
    data-engineering, batch-processing

Doc-Types:
    - API Reference
    - Operation Patterns Guide
    - Data Engineering Best Practices
"""

from enum import IntEnum
from typing import Any

from .protocols import Connection


class IdempotencyLevel(IntEnum):
    """
    Operation idempotency classification for re-run safety.

    IdempotencyLevel defines the contract a operation provides for re-execution.
    Higher levels provide stronger guarantees but require more infrastructure.

    Manifesto:
        Not all operations need the same idempotency guarantees. Raw capture
        operations (L1) can append freely because downstream layers handle dedup.
        Bronze layers (L2) use hash-based dedup to avoid re-processing identical
        source data. Silver/Gold layers (L3) use delete+insert to ensure re-runs
        produce exactly the same final state.

        Explicitly declaring idempotency level:
        - Documents operation behavior for operators
        - Enables framework-level safety checks
        - Guides monitoring and alerting (L1 re-run: normal, L3 re-run: investigate)

    Architecture:
        ```
        ┌──────────────────────────────────────────────────────────┐
        │              Idempotency Level Characteristics           │
        ├──────────────────────────────────────────────────────────┤
        │ Level     │ Re-run Safety │ Infrastructure │ Use Case   │
        ├───────────┼───────────────┼────────────────┼────────────┤
        │ L1_APPEND │ None          │ None           │ Audit logs │
        │ L2_INPUT  │ Hash-based    │ Hash column    │ Bronze     │
        │ L3_STATE  │ Delete+insert │ Logical key    │ Silver/Gold│
        └──────────────────────────────────────────────────────────┘

        Progression Through Layers:
        ┌─────────┐     ┌─────────┐     ┌─────────┐
        │ L1_RAW  │ ──► │L2_BRONZE│ ──► │L3_SILVER│
        │ (append)│     │ (hash)  │     │ (d+i)   │
        └─────────┘     └─────────┘     └─────────┘
        ```

    Features:
        - L1_APPEND (1): Raw capture, always insert, external dedup
        - L2_INPUT (2): Hash-based dedup, same hash → skip
        - L3_STATE (3): Delete+insert, same key → same state
        - IntEnum for ordering and comparison

    Examples:
        Declaring operation idempotency:

        >>> class MyOperation:
        ...     idempotency_level = IdempotencyLevel.L3_STATE

        Checking level:

        >>> IdempotencyLevel.L3_STATE > IdempotencyLevel.L1_APPEND
        True
        >>> IdempotencyLevel.L2_INPUT.name
        'L2_INPUT'

    Guardrails:
        ❌ DON'T: Use L1 for derived tables (duplicates on re-run)
        ✅ DO: Use L3 for any table with natural/logical keys

        ❌ DON'T: Assume L2 prevents all duplicates (hash collisions)
        ✅ DO: Use cryptographic hashes (SHA-256) for L2

    Tags:
        idempotency, operation-level, batch-processing, data-engineering,
        spine-core

    Doc-Types:
        - API Reference
        - Operation Patterns Guide
    """

    L1_APPEND = 1  # Always inserts, external dedup (audit logs)
    L2_INPUT = 2  # Same input → same output (hash-based dedup)
    L3_STATE = 3  # Re-run → same final state (delete+insert)


class IdempotencyHelper:
    """
    Database operations for idempotent operation patterns.

    IdempotencyHelper provides the low-level operations needed to implement
    L2 (hash-based dedup) and L3 (delete+insert) idempotency patterns.

    Manifesto:
        The delete+insert pattern is deceptively simple but easy to get wrong:
        - Delete must use exact logical key (not partial matches)
        - Delete and insert must be in same transaction
        - Key columns must match between delete and insert

        IdempotencyHelper encapsulates these patterns with a clean API:
        - hash_exists(): L2 pattern - check before insert
        - delete_for_key(): L3 pattern - delete by logical key
        - get_existing_hashes(): Batch L2 - preload for bulk checks

    Architecture:
        ```
        ┌──────────────────────────────────────────────────────────┐
        │                   IdempotencyHelper API                   │
        └──────────────────────────────────────────────────────────┘

        L2 Pattern (hash-based):
        ┌────────────────────────────────────────────────────────┐
        │ if helper.hash_exists("bronze_raw", "hash", h):       │
        │     continue  # Skip duplicate                         │
        │ conn.execute("INSERT INTO bronze_raw ...")            │
        └────────────────────────────────────────────────────────┘

        L3 Pattern (delete+insert):
        ┌────────────────────────────────────────────────────────┐
        │ key = {"week_ending": "2025-12-26", "tier": "NMS_T1"} │
        │ helper.delete_for_key("silver_volume", key)           │
        │ # ... insert new data ...                              │
        └────────────────────────────────────────────────────────┘

        Batch L2 Pattern:
        ┌────────────────────────────────────────────────────────┐
        │ existing = helper.get_existing_hashes("bronze", "h")  │
        │ for record in batch:                                   │
        │     if record.hash not in existing:                   │
        │         to_insert.append(record)                      │
        └────────────────────────────────────────────────────────┘
        ```

    Features:
        - hash_exists(): Single hash lookup for L2 dedup
        - get_existing_hashes(): Batch hash preload
        - delete_for_key(): L3 delete by logical key
        - Works with any Connection protocol (SQLite, PostgreSQL, etc.)

    Examples:
        L2 pattern - hash-based dedup:

        >>> helper = IdempotencyHelper(conn)
        >>> if helper.hash_exists("otc_raw", "record_hash", hash_value):
        ...     print("Duplicate, skipping")
        ... else:
        ...     conn.execute("INSERT INTO otc_raw ...")

        L3 pattern - delete+insert:

        >>> helper = IdempotencyHelper(conn)
        >>> key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
        >>> deleted = helper.delete_for_key("otc_venue_volume", key)
        >>> print(f"Deleted {deleted} existing rows")
        >>> # ... insert new data ...

    Performance:
        - hash_exists(): O(1) with index on hash column
        - get_existing_hashes(): O(n) where n = table rows
        - delete_for_key(): O(m) where m = matching rows

    Guardrails:
        ❌ DON'T: Delete without transaction (partial state on failure)
        ✅ DO: Wrap delete+insert in transaction

        ❌ DON'T: Use partial key for delete (deletes too much)
        ✅ DO: Use complete logical key for delete

    Tags:
        idempotency, helper, database, dedup, delete-insert, spine-core

    Doc-Types:
        - API Reference
        - Operation Patterns Guide
    """

    def __init__(self, conn: Connection):
        self.conn = conn

    def hash_exists(self, table: str, hash_column: str, hash_value: str) -> bool:
        """
        Check if record hash already exists (Level 2 dedup).

        Returns:
            True if hash exists, False otherwise
        """
        row = self.conn.execute(f"SELECT 1 FROM {table} WHERE {hash_column} = ? LIMIT 1", (hash_value,)).fetchone()
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
    Natural key abstraction for domain-driven data access.

    LogicalKey represents a domain's natural/business key (as opposed to
    surrogate keys like auto-increment IDs). It encapsulates the key parts
    and provides SQL generation utilities.

    Manifesto:
        Financial data has natural keys: (week_ending, tier), (accession_number),
        (cik, form_type, filed_date). These keys are meaningful to the business
        and stable across systems. LogicalKey:
        - Makes natural keys first-class citizens
        - Provides WHERE clause generation
        - Enables key-based operations (delete, lookup)
        - Documents what makes a record unique

    Architecture:
        ```
        ┌──────────────────────────────────────────────────────────┐
        │                    LogicalKey Usage                       │
        └──────────────────────────────────────────────────────────┘

        Construction:
        ┌────────────────────────────────────────────────────────┐
        │ key = LogicalKey(week_ending="2025-12-26",            │
        │                  tier="NMS_TIER_1")                    │
        └────────────────────────────────────────────────────────┘

        SQL Generation:
        ┌────────────────────────────────────────────────────────┐
        │ key.where_clause()  → "week_ending = ? AND tier = ?"  │
        │ key.values()        → ("2025-12-26", "NMS_TIER_1")    │
        └────────────────────────────────────────────────────────┘

        With IdempotencyHelper:
        ┌────────────────────────────────────────────────────────┐
        │ helper.delete_for_key("table", key.as_dict())         │
        └────────────────────────────────────────────────────────┘
        ```

    Features:
        - Keyword argument construction for clarity
        - where_clause(): SQL WHERE without keyword
        - values(): Parameter tuple for prepared statements
        - as_dict(): Dictionary form for other APIs
        - Readable __repr__ for debugging

    Examples:
        Creating a logical key:

        >>> key = LogicalKey(week_ending="2025-12-26", tier="NMS_TIER_1")
        >>> key
        LogicalKey(week_ending='2025-12-26', tier='NMS_TIER_1')

        SQL generation:

        >>> key.where_clause()
        'week_ending = ? AND tier = ?'
        >>> key.values()
        ('2025-12-26', 'NMS_TIER_1')

        Using with raw SQL:

        >>> sql = f"SELECT * FROM volume WHERE {key.where_clause()}"
        >>> conn.execute(sql, key.values())

        Using with IdempotencyHelper:

        >>> helper.delete_for_key("volume", key.as_dict())

    Performance:
        - Construction: O(n) where n = key parts
        - where_clause(): O(n) string join
        - values(): O(1) tuple creation

    Guardrails:
        ❌ DON'T: Use surrogate keys for business operations
        ✅ DO: Use LogicalKey with natural domain keys

        ❌ DON'T: Build WHERE clauses manually
        ✅ DO: Use LogicalKey.where_clause() for consistency

    Tags:
        logical-key, natural-key, domain-driven, sql-generation, spine-core

    Doc-Types:
        - API Reference
        - Data Modeling Guide
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
