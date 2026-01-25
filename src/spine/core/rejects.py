"""
Standardized reject handling for validation failures.

RejectSink writes rejected records to storage with lineage,
enabling audit trails and debugging.

SCHEMA OWNERSHIP:
- Uses shared `core_rejects` table (defined in spine.core.schema)
- Domain is a partition key, not a separate table
- Domains do NOT need their own reject tables

SYNC-ONLY: All methods are synchronous.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .schema import CORE_TABLES


class Connection(Protocol):
    """Minimal SYNC DB connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...


@dataclass
class Reject:
    """
    A rejected record with reason.

    Attributes:
        stage: Where rejected (INGEST, NORMALIZE, AGGREGATE)
        reason_code: Machine-readable code (INVALID_SYMBOL, NEGATIVE_VOLUME)
        reason_detail: Human-readable explanation
        raw_data: Original data (for debugging)
        source_locator: File path or URL
        line_number: Line in source file
    """

    stage: str
    reason_code: str
    reason_detail: str
    raw_data: Any = None
    source_locator: str | None = None
    line_number: int | None = None


class RejectSink:
    """
    Write rejects to core_rejects table with domain partition.

    Example:
        sink = RejectSink(conn, domain="otc", execution_id="abc123")

        sink.write(Reject(
            stage="NORMALIZE",
            reason_code="INVALID_SYMBOL",
            reason_detail="Symbol 'BAD$YM' contains invalid characters",
            raw_data=raw_record
        ), partition_key={"week_ending": "2025-12-26", "tier": "NMS_TIER_1"})
    """

    def __init__(
        self,
        conn: Connection,
        domain: str,
        execution_id: str,
        batch_id: str = None,
        table: str = None,  # Deprecated: use core_rejects
    ):
        self.conn = conn
        self.domain = domain
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

            placeholders = ", ".join("?" * len(columns))
            self.conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})", values
            )
