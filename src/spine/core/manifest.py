"""
Generic work manifest for tracking multi-stage workflows.

WorkManifest provides stage tracking for any domain's unit of work,
enabling idempotent restarts and progress monitoring across pipeline stages.

Manifesto:
    Financial data pipelines have multiple stages: ingest, normalize,
    aggregate, publish. Each stage must be tracked to support:

    - **Idempotent restarts:** Know where to resume after failure
    - **Progress monitoring:** Dashboard visibility into pipeline state
    - **Metrics collection:** Row counts, timing, quality metrics per stage
    - **Audit trail:** When stages completed, by which execution

    WorkManifest is the single source of truth for "where is this
    work item in the pipeline?" It uses a current-state table design
    (one row per stage per partition) optimized for fast lookups.

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    WorkManifest Architecture                 │
        └─────────────────────────────────────────────────────────────┘

        Stage Progression:
        ┌─────────────────────────────────────────────────────────────┐
        │                                                              │
        │  PENDING → INGESTED → NORMALIZED → AGGREGATED → PUBLISHED   │
        │    [0]        [1]         [2]          [3]          [4]     │
        │                                                              │
        │  Each stage has a rank for comparison (is_at_least)          │
        └─────────────────────────────────────────────────────────────┘

        Storage (core_manifest):
        ┌────────────────────────────────────────────────────────────┐
        │ domain | partition_key           | stage      | rank | ... │
        │ otc    | {"week_ending":"12-26"} | PENDING    | 0    | ... │
        │ otc    | {"week_ending":"12-26"} | INGESTED   | 1    | ... │
        │ otc    | {"week_ending":"12-26"} | NORMALIZED | 2    | ... │
        └────────────────────────────────────────────────────────────┘

        One row PER STAGE per partition (not one row per partition).

        API:
        ┌────────────────────────────────────────────────────────────┐
        │ advance_to(key, stage)  → UPSERT row for stage             │
        │ is_at_least(key, stage) → Check if rank >= target          │
        │ get(key)                → List all stages for partition    │
        └────────────────────────────────────────────────────────────┘

Features:
    - **Stage tracking:** Advance through stages with advance_to()
    - **Progress checks:** is_at_least() for idempotent stage gates
    - **Metrics storage:** row_count, custom metrics per stage
    - **Execution lineage:** execution_id, batch_id correlation
    - **Event hooks:** Optional on_stage_change for future event emission

Examples:
    Basic stage tracking:

    >>> manifest = WorkManifest(
    ...     conn,
    ...     domain="otc",
    ...     stages=["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED"]
    ... )
    >>> key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
    >>> manifest.advance_to(key, "INGESTED", row_count=1000)
    >>> manifest.is_at_least(key, "INGESTED")
    True

    Check before re-processing:

    >>> if not manifest.is_at_least(key, "NORMALIZED"):
    ...     # Run normalization
    ...     normalize(data)
    ...     manifest.advance_to(key, "NORMALIZED", row_count=950)

Performance:
    - advance_to(): Single UPSERT, O(1)
    - is_at_least(): Single SELECT by (domain, partition_key, stage), O(1)
    - get(): Index scan on (domain, partition_key), O(stages)

Guardrails:
    - SYNC-ONLY: All methods are synchronous
    - UPSERT semantics: advance_to() creates or updates
    - Stage order defined at construction time
    - Metrics are JSON-serialized for flexibility

Context:
    - Domain: Pipeline orchestration, progress tracking
    - Used By: All Spine workflows (Entity, Feed, Market)
    - Storage: Shared core_manifest table
    - Paired With: ExecutionContext for lineage tracking

Tags:
    manifest, workflow, progress, idempotent, stage-tracking,
    spine-core, pipeline, sync

Doc-Types:
    - API Reference
    - Pipeline Orchestration Guide
    - Idempotency Documentation

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
from typing import Any

from .dialect import Dialect, SQLiteDialect
from .protocols import Connection
from .schema import CORE_TABLES

# Type alias for the optional event hook (future Option B)
StageChangeHook = Callable[[str, dict, str, int, dict], None]
# Arguments: domain, partition_key, stage, stage_rank, metrics


class ManifestRow:
    """
    A single stage record from the manifest.

    Represents one row in core_manifest, capturing the state of a
    specific stage for a partition. Includes metrics, timing, and
    execution lineage for audit and debugging.

    Manifesto:
        Each stage in a pipeline needs to track:
        - **What:** stage name and rank for ordering
        - **When:** updated_at timestamp
        - **How much:** row_count for volume tracking
        - **Metrics:** custom JSON metrics per stage
        - **Lineage:** execution_id, batch_id for tracing

        ManifestRow is an immutable snapshot of this information,
        returned by WorkManifest.get() for each stage.

    Architecture:
        ::

            ManifestRow Structure:
            ┌────────────────────────────────────────────────────────┐
            │ stage: str           # e.g., "INGESTED"                │
            │ stage_rank: int      # e.g., 1 (for ordering)          │
            │ row_count: int|None  # e.g., 1000 rows processed       │
            │ metrics: dict        # e.g., {"null_rate": 0.05}       │
            │ execution_id: str    # Correlation to execution        │
            │ batch_id: str        # Correlation to batch            │
            │ updated_at: str      # ISO timestamp                   │
            └────────────────────────────────────────────────────────┘

    Attributes:
        stage: Stage name (e.g., "INGESTED", "NORMALIZED").
        stage_rank: Integer rank for stage ordering (0-indexed).
        row_count: Number of rows processed at this stage, or None.
        metrics: Custom metrics dictionary (JSON-serialized in DB).
        execution_id: Execution ID that created/updated this row.
        batch_id: Batch ID within the execution.
        updated_at: ISO timestamp of last update.

    Examples:
        >>> row = ManifestRow(
        ...     stage="INGESTED",
        ...     stage_rank=1,
        ...     row_count=1000,
        ...     metrics={"null_rate": 0.05},
        ...     execution_id="exec-123",
        ...     batch_id="batch-456",
        ...     updated_at="2025-12-26T10:00:00Z"
        ... )
        >>> row.stage
        'INGESTED'
        >>> row.stage_rank
        1

    Tags:
        manifest, stage, progress, dataclass, spine-core
    """

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
    Track processing stages for work items in multi-stage workflows.

    Each work item is identified by domain + partition_key, and progresses
    through stages (PENDING → INGESTED → NORMALIZED → AGGREGATED, etc.).
    Uses a current-state table design with one row per (domain, partition, stage).

    Manifesto:
        Knowing "where is this work in the pipeline?" is critical for:
        - **Idempotent restarts:** Resume from the last completed stage
        - **Progress dashboards:** Show pipeline status at a glance
        - **Debugging:** Correlate issues with specific stages
        - **Metrics:** Track row counts and timing per stage

        WorkManifest is the single source of truth. It supports:
        - UPSERT semantics (advance_to creates or updates)
        - Rank-based comparison (is_at_least for stage gates)
        - Multi-stage queries (get all stages for a partition)

    Architecture:
        ::

            ┌────────────────────────────────────────────────────────────┐
            │                      WorkManifest                          │
            ├────────────────────────────────────────────────────────────┤
            │ Properties:                                                 │
            │   conn: Connection        # DB connection (sync)           │
            │   domain: str             # Domain name                     │
            │   table: str              # core_manifest table             │
            │   stages: list[str]       # Ordered stage names            │
            │   _stage_ranks: dict      # stage → rank mapping           │
            │   on_stage_change: Hook   # Optional event callback        │
            ├────────────────────────────────────────────────────────────┤
            │ Methods:                                                    │
            │   advance_to(key, stage)  # UPSERT stage row               │
            │   is_at_least(key, stage) # Check rank >= target           │
            │   get(key)                # List all stages for partition  │
            └────────────────────────────────────────────────────────────┘

            Stage Progression:
            ┌────────────────────────────────────────────────────────────┐
            │                                                             │
            │  PENDING ─▶ INGESTED ─▶ NORMALIZED ─▶ AGGREGATED           │
            │   rank=0    rank=1       rank=2        rank=3              │
            │                                                             │
            │  is_at_least("NORMALIZED") checks rank >= 2                │
            └────────────────────────────────────────────────────────────┘

            Database Storage:
            ┌─────────────────────────────────────────────────────────────┐
            │ domain | partition_key           | stage     | rank | ...  │
            │ otc    | {"week":"12-26"}        | PENDING   | 0    | ...  │
            │ otc    | {"week":"12-26"}        | INGESTED  | 1    | ...  │
            │ ...one row per stage per partition...                      │
            └─────────────────────────────────────────────────────────────┘

    Features:
        - **UPSERT semantics:** advance_to() creates or updates stage row
        - **Rank comparison:** is_at_least() uses stage ordering
        - **Metrics storage:** row_count, custom JSON metrics per stage
        - **Execution lineage:** execution_id, batch_id correlation
        - **Event hooks:** Optional on_stage_change for future use

    Examples:
        Basic stage tracking:

        >>> manifest = WorkManifest(
        ...     conn,
        ...     domain="otc",
        ...     stages=["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED"]
        ... )
        >>> key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
        >>> manifest.advance_to(key, "INGESTED", row_count=1000)
        >>> manifest.is_at_least(key, "INGESTED")
        True

        Idempotent processing:

        >>> if not manifest.is_at_least(key, "NORMALIZED"):
        ...     data = normalize(raw_data)
        ...     manifest.advance_to(key, "NORMALIZED", row_count=len(data))

        Get all stages:

        >>> stages = manifest.get(key)
        >>> for row in stages:
        ...     print(f"{row.stage}: {row.row_count} rows")

    Performance:
        - advance_to(): Single UPSERT, O(1)
        - is_at_least(): Single SELECT, O(1)
        - get(): Index scan, O(number of stages)

    Guardrails:
        - SYNC-ONLY: All methods are synchronous
        - Stage order defined at construction time
        - Unknown stages raise ValueError
        - Metrics are JSON-serialized for flexibility

    Context:
        - Domain: Pipeline orchestration, progress tracking
        - Used By: All Spine workflows
        - Storage: Shared core_manifest table
        - Paired With: ExecutionContext for lineage

    Tags:
        manifest, workflow, progress, idempotent, stage-tracking,
        spine-core, pipeline, sync
    """

    def __init__(
        self,
        conn: Connection,
        domain: str,
        stages: list[str],
        dialect: Dialect = SQLiteDialect(),
        on_stage_change: StageChangeHook | None = None,
    ):
        """
        Initialize WorkManifest.

        Args:
            conn: Database connection (sync protocol)
            domain: Domain name (e.g., "otc")
            stages: Ordered list of stage names
            dialect: SQL dialect for portable queries
            on_stage_change: Optional hook for event emission (future Option B)
        """
        self.conn = conn
        self.domain = domain
        self.dialect = dialect
        self.table = CORE_TABLES["manifest"]
        self.stages = stages
        self._stage_ranks = {stage: idx for idx, stage in enumerate(stages)}

        # Future-proofing: optional hook for event emission
        self.on_stage_change = on_stage_change

    def _ph(self, count: int) -> str:
        """Generate dialect-specific placeholders."""
        return self.dialect.placeholders(count)

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

        # Portable UPSERT via dialect
        upsert_sql = self.dialect.upsert(
            self.table,
            ["domain", "partition_key", "stage", "stage_rank", "row_count",
             "metrics_json", "execution_id", "batch_id", "updated_at"],
            ["domain", "partition_key", "stage"],
        )
        self.conn.execute(
            upsert_sql,
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
            WHERE domain = {self.dialect.placeholder(0)} AND partition_key = {self.dialect.placeholder(1)}
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
            WHERE domain = {self.dialect.placeholder(0)} AND partition_key = {self.dialect.placeholder(1)}
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
            WHERE domain = {self.dialect.placeholder(0)} AND partition_key = {self.dialect.placeholder(1)} AND stage = {self.dialect.placeholder(2)}
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
            WHERE domain = {self.dialect.placeholder(0)} AND partition_key = {self.dialect.placeholder(1)} AND stage = {self.dialect.placeholder(2)}
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
