"""
Standardized reject handling for validation failures.

RejectSink writes rejected records to storage with lineage,
enabling audit trails and debugging. Rejects are records that
fail validation but shouldn't stop operation execution.

Manifesto:
    Financial data operations encounter invalid records:
    - Invalid symbols (BAD$YM)
    - Negative volumes
    - Missing required fields
    - Format mismatches

    These records must be:
    - **Captured:** Don't lose the data, store for investigation
    - **Classified:** Stage + reason_code for pattern analysis
    - **Traceable:** Lineage via execution_id, source_locator
    - **Debuggable:** Raw data preserved for reproduction

    Rejects are NEVER deleted - they form an audit trail of
    data quality issues for compliance and debugging.

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Reject Flow Architecture                  │
        └─────────────────────────────────────────────────────────────┘

        Capture:
        ┌───────────────────────────────────────────────────────────┐
        │ sink = RejectSink(conn, domain="otc", execution_id="abc") │
        │                                                            │
        │ sink.write(Reject(                                         │
        │     stage="NORMALIZE",                                     │
        │     reason_code="INVALID_SYMBOL",                          │
        │     reason_detail="Symbol 'BAD$YM' contains $",            │
        │     raw_data={"symbol": "BAD$YM", "volume": 1000}          │
        │ ), partition_key={"week_ending": "2025-12-26"})            │
        └───────────────────────────────────────────────────────────┘

        Storage (core_rejects):
        ┌───────────────────────────────────────────────────────────┐
        │ domain | partition_key | stage     | reason_code    | ... │
        │ otc    | {"week":...}  | NORMALIZE | INVALID_SYMBOL | ... │
        │ otc    | {"week":...}  | INGEST    | NULL_FIELD     | ... │
        └───────────────────────────────────────────────────────────┘

        Analysis (later):
        ┌───────────────────────────────────────────────────────────┐
        │ SELECT reason_code, COUNT(*) FROM core_rejects            │
        │ WHERE domain='otc' GROUP BY reason_code                   │
        │                                                            │
        │ reason_code      | count                                   │
        │ INVALID_SYMBOL   | 42                                      │
        │ NEGATIVE_VOLUME  | 7                                       │
        └───────────────────────────────────────────────────────────┘

Features:
    - **Reject dataclass:** Structured reject with stage, reason, raw data
    - **RejectSink:** Write single or batch rejects to core_rejects
    - **Lineage tracking:** execution_id, batch_id, source_locator
    - **Pattern analysis:** reason_code for aggregation
    - **Debugging:** raw_data preserved as JSON

Examples:
    Write a single reject:

    >>> sink = RejectSink(conn, domain="otc", execution_id="abc123")
    >>> sink.write(Reject(
    ...     stage="NORMALIZE",
    ...     reason_code="INVALID_SYMBOL",
    ...     reason_detail="Symbol 'BAD$YM' contains invalid characters",
    ...     raw_data={"symbol": "BAD$YM"}
    ... ), partition_key={"week_ending": "2025-12-26"})
    >>> sink.count
    1

    Write batch rejects:

    >>> rejects = [Reject(...), Reject(...), Reject(...)]
    >>> count = sink.write_batch(rejects, partition_key=key)
    >>> print(f"Wrote {count} rejects")

Performance:
    - write(): Single INSERT, O(1)
    - write_batch(): N INSERTs, O(n) - consider batching in caller

Guardrails:
    - SYNC-ONLY: All methods are synchronous
    - Rejects are NEVER deleted (audit compliance)
    - Raw data is JSON-serialized for storage
    - Count tracks total rejects written

Context:
    - Domain: Data quality, audit trail, validation
    - Used By: All Spine validation stages
    - Storage: Shared core_rejects table
    - Paired With: QualityRunner for quality gate decisions

Tags:
    reject, validation, audit-trail, data-quality, spine-core,
    debugging, lineage, sync

Doc-Types:
    - API Reference
    - Data Quality Guide
    - Validation Documentation

SCHEMA OWNERSHIP:
- Uses shared `core_rejects` table (defined in spine.core.schema)
- Domain is a partition key, not a separate table
- Domains do NOT need their own reject tables

SYNC-ONLY: All methods are synchronous.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .dialect import Dialect, SQLiteDialect
from .protocols import Connection
from .schema import CORE_TABLES


@dataclass
class Reject:
    """
    A rejected record with classification and debugging info.

    Represents a single record that failed validation. Contains
    the stage where rejection occurred, machine-readable reason code,
    human-readable detail, and original data for debugging.

    Manifesto:
        Every reject should answer:
        - **Where?** stage (INGEST, NORMALIZE, AGGREGATE)
        - **Why?** reason_code + reason_detail
        - **What?** raw_data for reproduction
        - **Source?** source_locator + line_number for tracing

        The reason_code enables aggregation ("how many INVALID_SYMBOL?")
        while reason_detail provides the specific explanation.

    Architecture:
        ::

            Reject Structure:
            ┌────────────────────────────────────────────────────────┐
            │ stage: str              # "NORMALIZE"                  │
            │ reason_code: str        # "INVALID_SYMBOL"             │
            │ reason_detail: str      # "Symbol 'BAD$YM' has $"      │
            │ raw_data: Any           # {"symbol": "BAD$YM"}         │
            │ source_locator: str     # "file://data/raw.csv"        │
            │ line_number: int        # 42                           │
            └────────────────────────────────────────────────────────┘

    Attributes:
        stage: Where rejected (INGEST, NORMALIZE, AGGREGATE).
        reason_code: Machine-readable code (INVALID_SYMBOL, NEGATIVE_VOLUME).
        reason_detail: Human-readable explanation.
        raw_data: Original data for debugging (JSON-serialized).
        source_locator: File path or URL of source data.
        line_number: Line number in source file.

    Examples:
        >>> reject = Reject(
        ...     stage="NORMALIZE",
        ...     reason_code="INVALID_SYMBOL",
        ...     reason_detail="Symbol 'BAD$YM' contains invalid characters",
        ...     raw_data={"symbol": "BAD$YM", "volume": 1000},
        ...     source_locator="file://data/raw.csv",
        ...     line_number=42
        ... )
        >>> reject.stage
        'NORMALIZE'
        >>> reject.reason_code
        'INVALID_SYMBOL'

    Tags:
        reject, validation, dataclass, data-quality, spine-core
    """

    stage: str
    reason_code: str
    reason_detail: str
    raw_data: Any = None
    source_locator: str | None = None
    line_number: int | None = None


class RejectSink:
    """
    Write rejects to core_rejects table with domain partitioning.

    Provides write() and write_batch() methods for capturing rejected
    records with full lineage. Tracks total count for metrics.

    Manifesto:
        RejectSink is the single entry point for recording validation
        failures. It ensures:
        - **Consistent schema:** All rejects in one shared table
        - **Domain partitioning:** Filter by domain for analysis
        - **Lineage tracking:** execution_id, batch_id for correlation
        - **Count tracking:** Easy access to rejection metrics

        Use one RejectSink per stage to track rejects by source.

    Architecture:
        ::

            ┌────────────────────────────────────────────────────────────┐
            │                       RejectSink                           │
            ├────────────────────────────────────────────────────────────┤
            │ Properties:                                                 │
            │   conn: Connection       # DB connection (sync)            │
            │   domain: str            # Domain name                      │
            │   table: str             # core_rejects table               │
            │   execution_id: str      # Execution correlation           │
            │   batch_id: str          # Batch correlation               │
            │   _count: int            # Running count of rejects        │
            ├────────────────────────────────────────────────────────────┤
            │ Methods:                                                    │
            │   write(reject, key)     # Write single reject             │
            │   write_batch(rejects)   # Write multiple rejects          │
            │   count → int            # Property: total written         │
            └────────────────────────────────────────────────────────────┘

            Write Flow:
            ┌────────────┐     ┌────────────┐     ┌─────────────┐
            │ Validation │────▶│ RejectSink │────▶│ core_rejects│
            │ stage      │     │ .write()   │     │ table       │
            │ catches    │     │            │     │             │
            │ bad record │     │            │     │             │
            └────────────┘     └────────────┘     └─────────────┘

    Features:
        - **Single writes:** write() for one reject at a time
        - **Batch writes:** write_batch() for efficiency
        - **Count tracking:** count property for metrics
        - **Lineage:** execution_id, batch_id correlation
        - **JSON serialization:** raw_data stored as JSON

    Examples:
        >>> sink = RejectSink(conn, domain="otc", execution_id="abc123")
        >>> sink.write(Reject(
        ...     stage="NORMALIZE",
        ...     reason_code="INVALID_SYMBOL",
        ...     reason_detail="Symbol 'BAD$YM' contains invalid characters",
        ...     raw_data=raw_record
        ... ), partition_key={"week_ending": "2025-12-26", "tier": "NMS"})
        >>> sink.count
        1

        >>> rejects = [Reject(...), Reject(...)]
        >>> sink.write_batch(rejects, partition_key=key)
        2
        >>> sink.count
        3

    Performance:
        - write(): Single INSERT, O(1)
        - write_batch(): N INSERTs (not bulk), O(n)
        - Consider batching in caller for large volumes

    Guardrails:
        - SYNC-ONLY: All methods are synchronous
        - No transactions (caller manages)
        - Raw data JSON-serialized with default=str
        - Empty batch returns 0, no DB operation

    Tags:
        reject, validation, sink, data-quality, spine-core, sync
    """

    def __init__(
        self,
        conn: Connection,
        domain: str,
        execution_id: str,
        batch_id: str = None,
        dialect: Dialect = SQLiteDialect(),
        table: str = None,
    ):
        self.conn = conn
        self.domain = domain
        self.dialect = dialect
        self.table = table or CORE_TABLES["rejects"]
        self.execution_id = execution_id
        self.batch_id = batch_id
        self._count = 0

    @property
    def count(self) -> int:
        """Number of rejects written."""
        return self._count

    def _key_json(self, key: dict[str, Any]) -> str:
        """Serialize key dict to JSON for storage."""
        return json.dumps(key, sort_keys=True, default=str)

    def write(self, reject: Reject, partition_key: dict[str, Any] = None) -> None:
        """Write single reject."""
        self._insert([reject], partition_key)
        self._count += 1

    def write_batch(self, rejects: list[Reject], partition_key: dict[str, Any] = None) -> int:
        """
        Write multiple rejects.

        Returns:
            Count of rejects written
        """
        if not rejects:
            return 0
        self._insert(rejects, partition_key)
        self._count += len(rejects)
        return len(rejects)

    def _insert(self, rejects: list[Reject], partition_key: dict[str, Any]) -> None:
        key_json = self._key_json(partition_key) if partition_key else "{}"

        columns = [
            "domain",
            "partition_key",
            "stage",
            "reason_code",
            "reason_detail",
            "raw_json",
            "source_locator",
            "line_number",
            "execution_id",
            "batch_id",
            "created_at",
        ]

        for reject in rejects:
            raw_json = json.dumps(reject.raw_data, default=str) if reject.raw_data else None
            values = (
                self.domain,
                key_json,
                reject.stage,
                reject.reason_code,
                reject.reason_detail,
                raw_json,
                reject.source_locator,
                reject.line_number,
                self.execution_id,
                self.batch_id,
                datetime.utcnow().isoformat(),
            )

            placeholders = self.dialect.placeholders(len(columns))
            self.conn.execute(f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})", values)
