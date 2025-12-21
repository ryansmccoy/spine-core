"""
Watermark tracking for incremental data operations.

Provides cursor-based "how far have I read?" tracking so that
incremental operations can resume from their last position after
restart, crash, or scale-out.

Manifesto:
    Financial data sources publish continuously — SEC EDGAR, Polygon,
    Bloomberg. Without watermarks, a restart forces a full re-crawl,
    wasting API credits, time, and rate-limit headroom.

    Watermarks record the last-processed position per (domain, source,
    partition) tuple. On restart the operation reads its watermark and
    resumes from there. Key principles:

    - **Forward-only advancement:** Prevents accidental backward movement
    - **Gap detection:** ``list_gaps()`` flags missing partitions for audit
    - **Persistence-agnostic:** Database or in-memory (tests)
    - **Partition-aware:** Per-source, per-partition tracking

Architecture:
    ::

        ┌──────────────────────────────────────────────────────────┐
        │                  WatermarkStore                           │
        └──────────────────────────────────────────────────────────┘

        advance("equity", "polygon", "AAPL", cursor)
              │
              ▼
        ┌──────────────────────────────────────────────────────────┐
        │ core_watermarks table (or in-memory dict)                │
        │ domain | source  | partition_key | high_water | updated  │
        │ equity | polygon | AAPL          | 2026-02-15 | ...      │
        └──────────────────────────────────────────────────────────┘

        list_gaps(expected=["AAPL","MSFT","GOOG"])
              │
              ▼
        WatermarkGap("MSFT") → BackfillPlan

Features:
    - **Watermark dataclass:** Frozen high-water mark per (domain, source, key)
    - **WatermarkStore:** advance(), get(), list_gaps() with DB or memory backend
    - **Forward-only:** Monotonic advancement prevents duplicate processing
    - **Gap detection:** Compare expected vs actual partitions
    - **WatermarkGap:** Feeds into BackfillPlan for structured recovery

Examples:
    >>> from spine.core.watermarks import Watermark, WatermarkStore
    >>> store = WatermarkStore()
    >>> store.advance("equity", "polygon", "AAPL", "2026-02-15T00:00:00Z")
    >>> wm = store.get("equity", "polygon", "AAPL")
    >>> wm.high_water
    '2026-02-15T00:00:00Z'

Performance:
    - advance(): Single UPSERT, O(1)
    - get(): Single SELECT by (domain, source, partition_key), O(1)
    - list_gaps(): O(expected) comparison against stored watermarks

Guardrails:
    ❌ DON'T: Move watermark backward (causes duplicate processing)
    ✅ DO: Use advance() which enforces forward-only semantics

    ❌ DON'T: Skip gap detection after backfills
    ✅ DO: Run list_gaps() periodically for completeness audits

    ❌ DON'T: Store mutable state in watermark metadata
    ✅ DO: Use metadata for context only (source URL, batch_id)

Context:
    Problem: Incremental operations need crash-safe resume and completeness
        auditing across partitioned data sources.
    Solution: Per-partition watermark tracking with forward-only advancement,
        gap detection, and persistence-agnostic backend.
    Alternatives Considered: Kafka offsets (Kafka-only), custom checkpoint
        files (no gap detection), database sequences (no partition awareness).

Tags:
    watermark, incremental, cursor, resume, operation, spine-core,
    checkpoint, gap-detection, idempotent

Doc-Types:
    - API Reference
    - Operation Patterns Guide
    - Data Engineering Best Practices

STDLIB ONLY — no Pydantic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Watermark:
    """High-water mark for a single (domain, source, partition_key) cursor.

    Attributes:
        domain: Logical domain that owns this cursor (e.g. ``"equity"``).
        source: Data source identifier (e.g. ``"polygon"``, ``"sec_edgar"``).
        partition_key: Further subdivision (e.g. ticker, filing type).
        high_water: Opaque string representing the furthest position
            consumed — typically an ISO-8601 timestamp or sequence number.
        low_water: Optional lower bound (e.g. earliest offset still
            retained).  ``None`` means unbounded.
        metadata: Free-form JSON-serialisable extras.
        updated_at: When this watermark was last advanced.
    """

    domain: str
    source: str
    partition_key: str
    high_water: str
    low_water: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Gap descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WatermarkGap:
    """Describes a detected gap between two consecutive watermarks.

    Attributes:
        domain: Domain of the surrounding watermarks.
        source: Source name.
        partition_key: Partition with the gap.
        gap_start: End of the preceding watermark (exclusive).
        gap_end: Start of the following watermark (exclusive).
    """

    domain: str
    source: str
    partition_key: str
    gap_start: str
    gap_end: str


# ---------------------------------------------------------------------------
# WatermarkStore
# ---------------------------------------------------------------------------


class WatermarkStore:
    """Persistence-agnostic watermark store.

    If *conn* is supplied (any object exposing ``.execute()`` and
    ``.commit()``), watermarks are persisted to the ``core_watermarks``
    table.  Otherwise an in-memory dict is used.

    Args:
        conn: Optional database connection.

    Examples:
        In-memory usage (tests):

        >>> store = WatermarkStore()
        >>> store.advance("d", "s", "pk", "100")
        >>> store.get("d", "s", "pk").high_water
        '100'

        With a database connection:

        >>> store = WatermarkStore(conn=sqlite_conn)
        >>> store.advance("equity", "polygon", "AAPL", "2026-02-15T00:00Z")
    """

    def __init__(self, conn: Any | None = None) -> None:
        self._conn = conn
        self._mem: dict[tuple[str, str, str], Watermark] = {}

    # -- core operations -----------------------------------------------------

    def advance(
        self,
        domain: str,
        source: str,
        partition_key: str,
        high_water: str,
        *,
        low_water: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Watermark:
        """Move the watermark forward (forward-only).

        If the supplied *high_water* is lexicographically ≤ the current
        high-water, the call is a no-op and the existing watermark is
        returned unchanged.  This guarantees monotonic advancement.

        Args:
            domain: Logical domain.
            source: Data source identifier.
            partition_key: Partition subdivision.
            high_water: New high-water value.
            low_water: Optional new low-water.
            metadata: Optional metadata dict (merged with existing).

        Returns:
            The resulting :class:`Watermark` (new or unchanged).
        """
        key = (domain, source, partition_key)
        now = datetime.now(UTC)

        existing = self._get_from_store(key)
        if existing is not None and high_water <= existing.high_water:
            return existing

        merged_meta = {**(existing.metadata if existing else {}), **(metadata or {})}
        wm = Watermark(
            domain=domain,
            source=source,
            partition_key=partition_key,
            high_water=high_water,
            low_water=low_water or (existing.low_water if existing else None),
            metadata=merged_meta,
            updated_at=now,
        )

        self._put_to_store(key, wm)
        return wm

    def get(
        self,
        domain: str,
        source: str,
        partition_key: str,
    ) -> Watermark | None:
        """Retrieve the current watermark, or ``None`` if not tracked.

        Args:
            domain: Logical domain.
            source: Data source identifier.
            partition_key: Partition subdivision.

        Returns:
            The :class:`Watermark` if found, else ``None``.
        """
        return self._get_from_store((domain, source, partition_key))

    def list_all(self, domain: str | None = None) -> list[Watermark]:
        """Return all tracked watermarks, optionally filtered by domain.

        Args:
            domain: If given, only watermarks matching this domain are returned.

        Returns:
            List of :class:`Watermark` instances.
        """
        if self._conn is not None:
            return self._list_db(domain)
        marks = list(self._mem.values())
        if domain is not None:
            marks = [w for w in marks if w.domain == domain]
        return marks

    def list_gaps(
        self,
        domain: str,
        source: str,
        expected_keys: list[str],
    ) -> list[WatermarkGap]:
        """Detect partitions in *expected_keys* that have no watermark.

        Returns a :class:`WatermarkGap` for each missing partition_key.
        This is a simple "missing partition" detector — for range-gap
        detection within a single partition, use the BackfillPlan.

        Args:
            domain: Logical domain.
            source: Data source identifier.
            expected_keys: All partition keys that should have watermarks.

        Returns:
            List of :class:`WatermarkGap` for missing partitions.
        """
        gaps: list[WatermarkGap] = []
        for pk in expected_keys:
            wm = self.get(domain, source, pk)
            if wm is None:
                gaps.append(
                    WatermarkGap(
                        domain=domain,
                        source=source,
                        partition_key=pk,
                        gap_start="<no watermark>",
                        gap_end="<no watermark>",
                    )
                )
        return gaps

    def delete(self, domain: str, source: str, partition_key: str) -> bool:
        """Remove a watermark.  Returns True if it existed.

        Args:
            domain: Logical domain.
            source: Data source identifier.
            partition_key: Partition subdivision.

        Returns:
            ``True`` if a watermark was deleted, ``False`` if not found.
        """
        key = (domain, source, partition_key)
        if self._conn is not None:
            return self._delete_db(key)
        return self._mem.pop(key, None) is not None

    # -- internal: memory backend -------------------------------------------

    def _get_from_store(self, key: tuple[str, str, str]) -> Watermark | None:
        if self._conn is not None:
            return self._get_db(key)
        return self._mem.get(key)

    def _put_to_store(self, key: tuple[str, str, str], wm: Watermark) -> None:
        if self._conn is not None:
            self._upsert_db(wm)
        else:
            self._mem[key] = wm

    # -- internal: database backend ------------------------------------------

    def _get_db(self, key: tuple[str, str, str]) -> Watermark | None:
        assert self._conn is not None
        domain, source, pk = key
        row = self._conn.execute(
            "SELECT high_water, low_water, metadata_json, updated_at "
            "FROM core_watermarks "
            "WHERE domain = ? AND source = ? AND partition_key = ?",
            (domain, source, pk),
        ).fetchone()
        if row is None:
            return None
        return Watermark(
            domain=domain,
            source=source,
            partition_key=pk,
            high_water=row[0],
            low_water=row[1],
            metadata=json.loads(row[2]) if row[2] else {},
            updated_at=datetime.fromisoformat(row[3]) if row[3] else None,
        )

    def _upsert_db(self, wm: Watermark) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO core_watermarks "
            "  (domain, source, partition_key, high_water, low_water, metadata_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(domain, source, partition_key) DO UPDATE SET "
            "  high_water = excluded.high_water, "
            "  low_water = excluded.low_water, "
            "  metadata_json = excluded.metadata_json, "
            "  updated_at = excluded.updated_at",
            (
                wm.domain,
                wm.source,
                wm.partition_key,
                wm.high_water,
                wm.low_water,
                json.dumps(wm.metadata) if wm.metadata else None,
                wm.updated_at.isoformat() if wm.updated_at else None,
            ),
        )
        self._conn.commit()

    def _list_db(self, domain: str | None) -> list[Watermark]:
        assert self._conn is not None
        if domain is not None:
            rows = self._conn.execute(
                "SELECT domain, source, partition_key, high_water, low_water, "
                "metadata_json, updated_at FROM core_watermarks WHERE domain = ?",
                (domain,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT domain, source, partition_key, high_water, low_water, "
                "metadata_json, updated_at FROM core_watermarks",
            ).fetchall()
        return [
            Watermark(
                domain=r[0],
                source=r[1],
                partition_key=r[2],
                high_water=r[3],
                low_water=r[4],
                metadata=json.loads(r[5]) if r[5] else {},
                updated_at=datetime.fromisoformat(r[6]) if r[6] else None,
            )
            for r in rows
        ]

    def _delete_db(self, key: tuple[str, str, str]) -> bool:
        assert self._conn is not None
        domain, source, pk = key
        cur = self._conn.execute(
            "DELETE FROM core_watermarks "
            "WHERE domain = ? AND source = ? AND partition_key = ?",
            (domain, source, pk),
        )
        self._conn.commit()
        return cur.rowcount > 0
