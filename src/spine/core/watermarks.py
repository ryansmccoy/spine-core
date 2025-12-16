"""
Watermark tracking for incremental data pipelines.

Provides cursor-based "how far have I read?" tracking so that
incremental pipelines can resume from their last position after
restart, crash, or scale-out.

Why This Matters — Financial Pipelines:
    SEC EDGAR publishes tens of thousands of filings per quarter.
    Polygon streams tick-level price data continuously.  Bloomberg
    pushes earnings estimates as analysts revise them.  Without
    watermarks, a pipeline restart forces a full re-crawl — expensive
    in API credits, time, and rate-limit headroom.

    Watermarks solve the "where did I leave off?" problem by recording
    the last-processed position per (domain, source, partition) tuple.
    On restart, the pipeline reads its watermark and resumes from there.

    Gap detection (``list_gaps()``) flags partitions where no watermark
    exists — critical for audit: "have we ingested all 10-K, 10-Q, 8-K,
    *and* 20-F filings, or did we miss a filing type?"

Why This Matters — General Pipelines:
    Any system that processes an ordered stream — Kafka offsets, CDC
    sequences, paginated API cursors, or log tail positions — needs
    the same checkpoint/resume pattern.  WatermarkStore provides a
    persistence-agnostic implementation with forward-only (monotonic)
    advancement, preventing accidental backward movement that would
    cause duplicate processing.

Key Concepts:
    Watermark: A frozen dataclass capturing the high-water mark for
        a given (domain, source, partition_key) triple.

    WatermarkStore: Persistence-agnostic store with ``advance()``
        (forward-only), ``get()``, ``list_gaps()``.

    WatermarkGap: Describes a detected gap — a partition that should
        have a watermark but doesn't.  Feed this to
        :class:`~spine.core.backfill.BackfillPlan` for structured recovery.

Related Modules:
    - :mod:`spine.core.temporal_envelope` — 4-timestamp context for each record
    - :mod:`spine.core.backfill` — structured gap-fill plans driven by gap detection
    - :mod:`spine.core.finance.corrections` — what changed and why

Architecture:
    The store persists to a ``core_watermarks`` table when a database
    connection is supplied.  Without a connection it falls back to an
    in-memory dict (useful for tests).

    Database schema::

        CREATE TABLE core_watermarks (
            domain        TEXT NOT NULL,
            source        TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            high_water    TEXT NOT NULL,
            low_water     TEXT,
            metadata_json TEXT,
            updated_at    TEXT NOT NULL,
            UNIQUE (domain, source, partition_key)
        );

Example:
    >>> from spine.core.watermarks import Watermark, WatermarkStore
    >>> store = WatermarkStore()
    >>> store.advance("equity", "polygon", "AAPL", "2026-02-15T00:00:00Z")
    >>> wm = store.get("equity", "polygon", "AAPL")
    >>> wm.high_water
    '2026-02-15T00:00:00Z'

STDLIB ONLY — no Pydantic.

Tags:
    watermark, incremental, cursor, resume, pipeline, spine-core,
    checkpoint, gap-detection, idempotent
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
