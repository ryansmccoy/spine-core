"""Asset-centric tracking for data artifacts.

Inspired by Dagster's software-defined assets, this module provides primitives
for tracking *what data exists* (not just *what code ran*).  While spine-core's
execution subsystem tracks pipeline runs and their status, assets track the
**data artifacts** those pipelines produce.

Why This Matters:
    spine-core processes SEC filings, financial data, and portfolio metrics.
    Without asset tracking, you can answer "did the pipeline run?" but not
    "is the 10-K data for AAPL fresh?" or "what produced this filing record?"
    Asset tracking makes data a first-class citizen alongside executions.

Architecture Decisions:
    - **stdlib-only**: No external dependencies.  Frozen dataclasses with
      ``__slots__`` for immutability and memory efficiency.
    - **Composable keys**: ``AssetKey`` uses a tuple of strings for
      hierarchical naming (``("sec", "filings", "10-K")``), enabling
      namespace-based queries.
    - **Separation of concerns**: ``AssetMaterialization`` records *production*
      of data, ``AssetObservation`` records *observation* without production.
      This mirrors Dagster's distinction and supports freshness monitoring.
    - **Partition-aware**: Assets can be partitioned (by CIK, date, sector).
      Partitions enable incremental materialization and staleness checks.

Related Modules:
    - :mod:`spine.core.temporal_envelope` — Wraps data with temporal semantics
      (event_time, ingest_time).  Assets track *existence*; envelopes track
      *time context*.
    - :mod:`spine.core.watermarks` — Watermarks track *progress cursors*;
      assets track *data artifacts*.  A pipeline advances a watermark AND
      records an asset materialization.
    - :mod:`spine.execution.models` — ``Execution`` tracks pipeline runs.
      ``AssetMaterialization.execution_id`` links data to the run that
      produced it.
    - :mod:`spine.core.quality` — Quality checks validate data;
      ``AssetObservation`` records the result of those checks.

Best Practices:
    1. Use hierarchical keys: ``AssetKey("sec", "filings", form_type)``
       not ``AssetKey("sec_filings_10k")``.
    2. Always set ``partition`` for partitioned data (CIK, date, etc.).
    3. Record materializations *after* successful writes, not before.
    4. Use observations for freshness monitoring without re-materializing.
    5. Store ``execution_id`` to link assets to their producing pipeline.

Tags:
    domain: core, data-tracking, lineage
    layer: domain-primitives
    pattern: value-object, event-sourcing
    stdlib-only: true

Example:
    >>> key = AssetKey("sec", "filings", "10-K")
    >>> mat = AssetMaterialization(
    ...     asset_key=key,
    ...     partition="CIK:0001318605",
    ...     metadata={"count": 42, "latest_date": "2025-01-15"},
    ... )
    >>> obs = AssetObservation(
    ...     asset_key=key,
    ...     partition="CIK:0001318605",
    ...     metadata={"row_count": 42, "freshness_lag_hours": 2.5},
    ... )
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# AssetKey — hierarchical data identifier
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssetKey:
    """Hierarchical identifier for a data asset.

    An asset key is an immutable tuple of strings that uniquely identifies
    a type of data artifact.  The hierarchy enables namespace-based queries
    (e.g., all assets under ``"sec"``).

    Architecture Decision:
        Keys use a tuple (not a dot-separated string) to avoid ambiguity
        with names that contain dots and to enable efficient prefix matching.

    Example:
        >>> key = AssetKey("sec", "filings", "10-K")
        >>> key.path
        ('sec', 'filings', '10-K')
        >>> str(key)
        'sec/filings/10-K'
        >>> key.is_prefix_of(AssetKey("sec", "filings", "10-K", "2025"))
        True
    """

    path: tuple[str, ...]
    """Ordered namespace components (e.g., ``("sec", "filings", "10-K")``)."""

    def __init__(self, *parts: str) -> None:
        """Create an AssetKey from one or more string parts.

        Args:
            *parts: Namespace components.  At least one required.

        Raises:
            ValueError: If no parts are provided or any part is empty.
        """
        if not parts:
            raise ValueError("AssetKey requires at least one path component")
        for p in parts:
            if not isinstance(p, str) or not p.strip():
                raise ValueError(f"AssetKey path components must be non-empty strings, got {p!r}")
        object.__setattr__(self, "path", tuple(parts))

    def __str__(self) -> str:
        """Slash-separated string representation."""
        return "/".join(self.path)

    def __repr__(self) -> str:
        parts = ", ".join(repr(p) for p in self.path)
        return f"AssetKey({parts})"

    def is_prefix_of(self, other: AssetKey) -> bool:
        """Check if this key is a prefix of *other*.

        Example:
            >>> AssetKey("sec").is_prefix_of(AssetKey("sec", "filings"))
            True
            >>> AssetKey("sec", "filings").is_prefix_of(AssetKey("sec"))
            False
        """
        return other.path[: len(self.path)] == self.path

    @property
    def namespace(self) -> str:
        """First component (top-level namespace).

        Example:
            >>> AssetKey("sec", "filings", "10-K").namespace
            'sec'
        """
        return self.path[0]

    @property
    def name(self) -> str:
        """Last component (leaf name).

        Example:
            >>> AssetKey("sec", "filings", "10-K").name
            '10-K'
        """
        return self.path[-1]

    @classmethod
    def from_string(cls, key_str: str) -> AssetKey:
        """Parse from slash-separated string.

        Example:
            >>> AssetKey.from_string("sec/filings/10-K")
            AssetKey('sec', 'filings', '10-K')
        """
        parts = key_str.strip("/").split("/")
        return cls(*parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON/storage."""
        return {"path": list(self.path)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetKey:
        """Deserialize from dict."""
        return cls(*data["path"])


# ---------------------------------------------------------------------------
# FreshnessPolicy — staleness thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Defines how fresh an asset must be.

    Used by monitoring tools to determine if an asset is stale and needs
    re-materialization.

    Example:
        >>> policy = FreshnessPolicy(max_lag_seconds=3600)  # 1 hour
        >>> policy.is_stale(last_materialized=some_old_datetime)
        True
    """

    max_lag_seconds: float
    """Maximum allowed seconds since last materialization."""

    cron_schedule: str | None = None
    """Optional cron expression for expected materialization schedule."""

    def is_stale(self, last_materialized: datetime | None) -> bool:
        """Check if the asset is stale based on last materialization time.

        Args:
            last_materialized: When the asset was last materialized (UTC).
                ``None`` means never materialized (always stale).

        Returns:
            ``True`` if the asset needs re-materialization.
        """
        if last_materialized is None:
            return True
        elapsed = (_utcnow() - last_materialized).total_seconds()
        return elapsed > self.max_lag_seconds


# ---------------------------------------------------------------------------
# AssetMaterialization — record of data production
# ---------------------------------------------------------------------------


class MaterializationStatus(str, Enum):
    """Outcome of a materialization attempt."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some partitions failed
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AssetMaterialization:
    """Immutable record that a data asset was produced.

    A materialization is created *after* a pipeline successfully writes data.
    It answers the question: "When and how was this data created?"

    Architecture Decision:
        Materializations are frozen (immutable) to prevent modification after
        recording.  They are append-only — corrections create new
        materializations with updated metadata, never modify existing ones.

    Related Modules:
        - :class:`AssetKey` — What was materialized
        - :class:`~spine.execution.models.Execution` — What pipeline run
          produced it (linked via ``execution_id``)
        - :class:`~spine.core.temporal_envelope.TemporalEnvelope` — Time
          context for the data itself

    Example:
        >>> mat = AssetMaterialization(
        ...     asset_key=AssetKey("sec", "filings", "10-K"),
        ...     partition="CIK:0001318605",
        ...     metadata={"count": 42, "source": "EDGAR"},
        ...     execution_id="exec-abc-123",
        ... )
        >>> mat.asset_key.name
        '10-K'
    """

    asset_key: AssetKey
    """Which asset was materialized."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique materialization ID."""

    partition: str | None = None
    """Partition key (e.g., ``"CIK:0001318605"``, ``"date:2025-01-15"``)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary metadata (row counts, checksums, timestamps, etc.)."""

    timestamp: datetime = field(default_factory=_utcnow)
    """When the materialization was recorded (UTC)."""

    execution_id: str | None = None
    """Execution/run ID that produced this materialization."""

    status: MaterializationStatus = MaterializationStatus.SUCCESS
    """Outcome of the materialization."""

    tags: dict[str, str] = field(default_factory=dict)
    """Indexed tags for filtering."""

    upstream_keys: tuple[AssetKey, ...] = ()
    """Asset keys this materialization consumed (lineage)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON/storage."""
        return {
            "id": self.id,
            "asset_key": str(self.asset_key),
            "partition": self.partition,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "execution_id": self.execution_id,
            "status": self.status.value,
            "tags": self.tags,
            "upstream_keys": [str(k) for k in self.upstream_keys],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetMaterialization:
        """Deserialize from dict."""
        return cls(
            asset_key=AssetKey.from_string(data["asset_key"]),
            id=data.get("id", str(uuid.uuid4())),
            partition=data.get("partition"),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else _utcnow(),
            execution_id=data.get("execution_id"),
            status=MaterializationStatus(data.get("status", "success")),
            tags=data.get("tags", {}),
            upstream_keys=tuple(AssetKey.from_string(k) for k in data.get("upstream_keys", [])),
        )


# ---------------------------------------------------------------------------
# AssetObservation — record of data check without production
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssetObservation:
    """Immutable record that a data asset was observed (checked) without
    re-materializing it.

    Observations are lighter-weight than materializations.  They record
    freshness checks, row count validations, or quality assessments without
    triggering a full re-computation.

    Example:
        >>> obs = AssetObservation(
        ...     asset_key=AssetKey("sec", "filings", "10-K"),
        ...     partition="CIK:0001318605",
        ...     metadata={"row_count": 42, "freshness_lag_hours": 2.5},
        ... )
    """

    asset_key: AssetKey
    """Which asset was observed."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique observation ID."""

    partition: str | None = None
    """Partition key if applicable."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Observation data (counts, freshness, quality scores, etc.)."""

    timestamp: datetime = field(default_factory=_utcnow)
    """When the observation was recorded (UTC)."""

    execution_id: str | None = None
    """Execution/run ID that performed the observation."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON/storage."""
        return {
            "id": self.id,
            "asset_key": str(self.asset_key),
            "partition": self.partition,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "execution_id": self.execution_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetObservation:
        """Deserialize from dict."""
        return cls(
            asset_key=AssetKey.from_string(data["asset_key"]),
            id=data.get("id", str(uuid.uuid4())),
            partition=data.get("partition"),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else _utcnow(),
            execution_id=data.get("execution_id"),
        )


# ---------------------------------------------------------------------------
# AssetRegistry — in-memory asset catalog
# ---------------------------------------------------------------------------


@dataclass
class AssetDefinition:
    """Registered asset with its metadata and policies.

    An asset definition declares that a data artifact *should* exist,
    what produces it, and how fresh it should be.  Think of it as the
    "schema" for an asset: it describes the contract, while
    materializations are the instances.

    Example:
        >>> defn = AssetDefinition(
        ...     key=AssetKey("sec", "filings", "10-K"),
        ...     description="SEC 10-K annual filings",
        ...     producing_pipeline="ingest_filings",
        ...     freshness_policy=FreshnessPolicy(max_lag_seconds=86400),
        ...     group="sec_data",
        ... )
    """

    key: AssetKey
    """Unique identifier for this asset."""

    description: str = ""
    """Human-readable description of what this asset contains."""

    producing_pipeline: str | None = None
    """Name of the pipeline/workflow that materializes this asset."""

    freshness_policy: FreshnessPolicy | None = None
    """How fresh this asset should be (``None`` = no staleness checks)."""

    group: str = "default"
    """Logical group for dashboard/UI organization."""

    tags: dict[str, str] = field(default_factory=dict)
    """Metadata tags for filtering."""

    dependencies: tuple[AssetKey, ...] = ()
    """Assets this asset depends on (upstream lineage)."""


class AssetRegistry:
    """In-memory catalog of registered asset definitions.

    The registry is the central place to declare what assets exist in the
    system, what produces them, and their freshness requirements.  It does
    NOT store materializations — those are append-only events recorded
    separately.

    Architecture Decision:
        The registry is deliberately in-memory with no DB dependency.
        Asset *definitions* are code-level declarations (like pipeline
        registrations).  Asset *materializations* are runtime events
        stored in the execution ledger or a dedicated table.

    Example:
        >>> registry = AssetRegistry()
        >>> registry.register(AssetDefinition(
        ...     key=AssetKey("sec", "filings", "10-K"),
        ...     description="SEC 10-K annual filings",
        ...     producing_pipeline="ingest_filings",
        ... ))
        >>> registry.get(AssetKey("sec", "filings", "10-K")).description
        'SEC 10-K annual filings'
        >>> list(registry.by_group("sec_data"))
        [...]
    """

    def __init__(self) -> None:
        self._assets: dict[AssetKey, AssetDefinition] = {}

    def register(self, definition: AssetDefinition) -> None:
        """Register an asset definition.

        Args:
            definition: The asset to register.

        Raises:
            ValueError: If an asset with the same key is already registered.
        """
        if definition.key in self._assets:
            raise ValueError(f"Asset already registered: {definition.key}")
        self._assets[definition.key] = definition

    def get(self, key: AssetKey) -> AssetDefinition | None:
        """Look up an asset definition by key."""
        return self._assets.get(key)

    def list_all(self) -> list[AssetDefinition]:
        """Return all registered definitions."""
        return list(self._assets.values())

    def by_group(self, group: str) -> list[AssetDefinition]:
        """Return definitions in a specific group."""
        return [d for d in self._assets.values() if d.group == group]

    def by_namespace(self, namespace: str) -> list[AssetDefinition]:
        """Return definitions under a namespace prefix.

        Example:
            >>> registry.by_namespace("sec")
            # Returns all assets whose key starts with "sec"
        """
        prefix = AssetKey(namespace)
        return [d for d in self._assets.values() if prefix.is_prefix_of(d.key)]

    def by_pipeline(self, pipeline_name: str) -> list[AssetDefinition]:
        """Return definitions produced by a specific pipeline."""
        return [d for d in self._assets.values() if d.producing_pipeline == pipeline_name]

    def dependents_of(self, key: AssetKey) -> list[AssetDefinition]:
        """Return definitions that depend on the given asset."""
        return [d for d in self._assets.values() if key in d.dependencies]

    def clear(self) -> None:
        """Remove all registrations (for testing)."""
        self._assets.clear()

    def __len__(self) -> int:
        return len(self._assets)

    def __contains__(self, key: AssetKey) -> bool:
        return key in self._assets


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_registry: AssetRegistry | None = None


def get_asset_registry() -> AssetRegistry:
    """Get the global asset registry (creates on first access)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = AssetRegistry()
    return _default_registry


def reset_asset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _default_registry
    _default_registry = None


def register_asset(
    *path: str,
    description: str = "",
    producing_pipeline: str | None = None,
    freshness_policy: FreshnessPolicy | None = None,
    group: str = "default",
    tags: dict[str, str] | None = None,
    dependencies: tuple[AssetKey, ...] = (),
) -> AssetDefinition:
    """Convenience function to register an asset in the global registry.

    Args:
        *path: AssetKey path components.
        description: Human-readable description.
        producing_pipeline: Pipeline that produces this asset.
        freshness_policy: Staleness thresholds.
        group: Logical group name.
        tags: Metadata tags.
        dependencies: Upstream asset keys.

    Returns:
        The registered AssetDefinition.

    Example:
        >>> defn = register_asset(
        ...     "sec", "filings", "10-K",
        ...     description="SEC 10-K annual filings",
        ...     producing_pipeline="ingest_filings",
        ...     freshness_policy=FreshnessPolicy(max_lag_seconds=86400),
        ... )
    """
    defn = AssetDefinition(
        key=AssetKey(*path),
        description=description,
        producing_pipeline=producing_pipeline,
        freshness_policy=freshness_policy,
        group=group,
        tags=tags or {},
        dependencies=dependencies,
    )
    get_asset_registry().register(defn)
    return defn
