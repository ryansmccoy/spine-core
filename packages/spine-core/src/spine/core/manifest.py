"""
Generic work manifest for tracking multi-stage workflows.

WorkManifest provides stage tracking for any domain's unit of work.

SCHEMA:
- Uses shared `core_manifest` table (defined in spine.core.schema)
- Columns: domain, partition_key, stage, stage_rank, row_count, metrics_json,
           execution_id, batch_id, updated_at
- UNIQUE constraint on (domain, partition_key, stage)
- One row PER STAGE per partition (not one row per partition)

BEHAVIOR:
- advance_to() UPSERTS: creates or updates row for that stage
- is_at_least() compares stage_rank (or configured stage ordering)
- get() returns all stages for a partition in stage order

SYNC-ONLY: All methods are synchronous.

FUTURE-PROOFING (Option B):
- Code is structured so adding EventEmitter is additive
- Optional hook `on_stage_change` can be set to emit events
- core_manifest_events table can be added later without changing this API
"""

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from .schema import CORE_TABLES


class Connection(Protocol):
    """Minimal SYNC DB connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...
    def commit(self) -> None: ...


# Type alias for the optional event hook (future Option B)
StageChangeHook = Callable[[str, dict, str, int, dict], None]
# Arguments: domain, partition_key, stage, stage_rank, metrics


class ManifestRow:
    """A single stage record from the manifest."""

    def __init__(
        self,
        stage: str,
        stage_rank: int,
        row_count: int | None,
        metrics: dict[str, Any],
        execution_id: str | None,
        batch_id: str | None,
        updated_at: str,
    ):
        self.stage = stage
        self.stage_rank = stage_rank
        self.row_count = row_count
        self.metrics = metrics
        self.execution_id = execution_id
        self.batch_id = batch_id
        self.updated_at = updated_at

    def __repr__(self) -> str:
        return f"ManifestRow(stage={self.stage!r}, rank={self.stage_rank})"


class WorkManifest:
    """
    Track processing stages for work items (Option A: current-state table).

    Each work item is identified by:
    - domain: The domain name (e.g., "otc", "equity")
    - partition_key: Dict of key columns (e.g., {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"})

    Stages are stored as separate rows. Each stage has a rank for ordering.

    Example:
        manifest = WorkManifest(
            conn,
            domain="otc",
            stages=["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED"]
        )

        key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}

        # Advance to a stage (upserts)
        manifest.advance_to(key, "INGESTED", row_count=1000)

        # Check if at least at a stage
        if manifest.is_at_least(key, "INGESTED"):
            print("Already ingested")

        # Get all stages for a partition
        stages = manifest.get(key)  # List of ManifestRow in stage order
    """

    def __init__(
        self,
        conn: Connection,
        domain: str,
        stages: list[str],
        on_stage_change: StageChangeHook | None = None,
    ):
        """
        Initialize WorkManifest.

        Args:
            conn: Database connection (sync protocol)
            domain: Domain name (e.g., "otc")
            stages: Ordered list of stage names
            on_stage_change: Optional hook for event emission (future Option B)
        """
        self.conn = conn
        self.domain = domain
        self.table = CORE_TABLES["manifest"]
        self.stages = stages
        self._stage_ranks = {stage: idx for idx, stage in enumerate(stages)}

        # Future-proofing: optional hook for event emission
        self.on_stage_change = on_stage_change

    def _key_json(self, key: dict[str, Any]) -> str:
        """Serialize key dict to JSON for storage."""
        return json.dumps(key, sort_keys=True, default=str)

    def _get_rank(self, stage: str) -> int:
        """Get rank for a stage (0-based index in stages list)."""
        if stage not in self._stage_ranks:
            raise ValueError(f"Unknown stage '{stage}'. Valid stages: {self.stages}")
        return self._stage_ranks[stage]

    def advance_to(
        self,
        key: dict[str, Any],
        stage: str,
        *,
        row_count: int | None = None,
        execution_id: str | None = None,
        batch_id: str | None = None,
        **metrics,
    ) -> None:
        """
        Upsert stage record for a partition.

        Creates or updates the row for (domain, partition_key, stage).
        This is NOT append-only; it updates existing stage rows.

        Args:
            key: Partition key dict
            stage: Stage name (must be in configured stages list)
            row_count: Optional row count metric
            execution_id: Optional execution ID for lineage
            batch_id: Optional batch ID for lineage
            **metrics: Additional metrics stored in metrics_json
        """
        key_json = self._key_json(key)
        stage_rank = self._get_rank(stage)
        updated_at = datetime.utcnow().isoformat()
        metrics_json = json.dumps(metrics) if metrics else None

        # SQLite UPSERT syntax (INSERT OR REPLACE respects UNIQUE constraint)
        self.conn.execute(
            f"""
            INSERT INTO {self.table} 
                (domain, partition_key, stage, stage_rank, row_count, 
                 metrics_json, execution_id, batch_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain, partition_key, stage) DO UPDATE SET
                stage_rank = excluded.stage_rank,
                row_count = excluded.row_count,
                metrics_json = excluded.metrics_json,
                execution_id = excluded.execution_id,
                batch_id = excluded.batch_id,
                updated_at = excluded.updated_at
            """,
            (
                self.domain,
                key_json,
                stage,
                stage_rank,
                row_count,
                metrics_json,
                execution_id,
                batch_id,
                updated_at,
            ),
        )

        # Future-proofing: call event hook if provided
        if self.on_stage_change:
            self.on_stage_change(self.domain, key, stage, stage_rank, metrics)

    def get(self, key: dict[str, Any]) -> list[ManifestRow]:
        """
        Get all stage records for a partition, ordered by stage_rank.

        Returns:
            List of ManifestRow objects in stage order (earliest first)
        """
        key_json = self._key_json(key)

        cursor = self.conn.execute(
            f"""
            SELECT stage, stage_rank, row_count, metrics_json,
                   execution_id, batch_id, updated_at
            FROM {self.table}
            WHERE domain = ? AND partition_key = ?
            ORDER BY stage_rank ASC
            """,
            (self.domain, key_json),
        )

        rows = []
        for row in cursor.fetchall():
            metrics = json.loads(row[3]) if row[3] else {}
            rows.append(
                ManifestRow(
                    stage=row[0],
                    stage_rank=row[1],
                    row_count=row[2],
                    metrics=metrics,
                    execution_id=row[4],
                    batch_id=row[5],
                    updated_at=row[6],
                )
            )
        return rows

    def get_latest_stage(self, key: dict[str, Any]) -> str | None:
        """
        Get the highest-ranked stage that has been recorded.

        Returns:
            Stage name, or None if no stages recorded
        """
        key_json = self._key_json(key)

        row = self.conn.execute(
            f"""
            SELECT stage FROM {self.table}
            WHERE domain = ? AND partition_key = ?
            ORDER BY stage_rank DESC
            LIMIT 1
            """,
            (self.domain, key_json),
        ).fetchone()

        return row[0] if row else None

    def is_at_least(self, key: dict[str, Any], min_stage: str) -> bool:
        """
        Check if partition has reached at least the given stage.

        This checks if any recorded stage has rank >= min_stage's rank.

        Args:
            key: Partition key dict
            min_stage: Minimum stage to check for

        Returns:
            True if at or past min_stage, False otherwise
        """
        min_rank = self._get_rank(min_stage)
        latest = self.get_latest_stage(key)

        if latest is None:
            return False

        return self._get_rank(latest) >= min_rank

    def is_before(self, key: dict[str, Any], stage: str) -> bool:
        """
        Check if partition is before the given stage (or has no records).

        Args:
            key: Partition key dict
            stage: Stage to compare against

        Returns:
            True if before stage or no records, False otherwise
        """
        stage_rank = self._get_rank(stage)
        latest = self.get_latest_stage(key)

        if latest is None:
            return True

        return self._get_rank(latest) < stage_rank

    def has_stage(self, key: dict[str, Any], stage: str) -> bool:
        """
        Check if a specific stage has been recorded.

        Args:
            key: Partition key dict
            stage: Stage to check

        Returns:
            True if stage exists, False otherwise
        """
        key_json = self._key_json(key)

        row = self.conn.execute(
            f"""
            SELECT 1 FROM {self.table}
            WHERE domain = ? AND partition_key = ? AND stage = ?
            """,
            (self.domain, key_json, stage),
        ).fetchone()

        return row is not None

    def get_stage_metrics(self, key: dict[str, Any], stage: str) -> ManifestRow | None:
        """
        Get metrics for a specific stage.

        Args:
            key: Partition key dict
            stage: Stage to get metrics for

        Returns:
            ManifestRow if stage exists, None otherwise
        """
        key_json = self._key_json(key)

        row = self.conn.execute(
            f"""
            SELECT stage, stage_rank, row_count, metrics_json,
                   execution_id, batch_id, updated_at
            FROM {self.table}
            WHERE domain = ? AND partition_key = ? AND stage = ?
            """,
            (self.domain, key_json, stage),
        ).fetchone()

        if row is None:
            return None

        metrics = json.loads(row[3]) if row[3] else {}
        return ManifestRow(
            stage=row[0],
            stage_rank=row[1],
            row_count=row[2],
            metrics=metrics,
            execution_id=row[4],
            batch_id=row[5],
            updated_at=row[6],
        )
