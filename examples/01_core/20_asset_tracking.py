#!/usr/bin/env python3
"""Asset Tracking — Dagster-Inspired Data Artifact Management.

================================================================================
WHAT IS ASSET TRACKING?
================================================================================

**Asset tracking** is the practice of treating *data artifacts* as first-class
citizens in your data platform, rather than just side effects of operation runs.

Instead of asking "Did the operation run?" you ask:
- "Does this data exist?"
- "Is it fresh enough?"
- "What created it?"
- "What depends on it?"

This is the philosophical difference between:

    Traditional ETL: "Run ingest_filings.py at 9am"
    Asset-Centric:   "The 10-K filings asset should exist and be < 24 hours old"

Why This Matters:
    1. **Freshness SLAs** — Know when data is stale, not just when jobs failed
    2. **Impact Analysis** — Before changing a operation, see what breaks downstream
    3. **Lineage/Provenance** — Trace any number back to its source
    4. **Observability** — Check data quality without re-running operations
    5. **Selective Refresh** — Re-materialize only stale assets, not everything


================================================================================
ARCHITECTURE: ASSET GRAPH
================================================================================

Assets form a Directed Acyclic Graph (DAG) based on dependencies::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  ASSET DEPENDENCY GRAPH                                                 │
    └─────────────────────────────────────────────────────────────────────────┘

                    ┌───────────────┐      ┌───────────────┐
                    │  sec/index/   │      │  market/ref/  │
                    │    full       │      │   tickers     │
                    └───────┬───────┘      └───────┬───────┘
                            │                      │
                            ▼                      │
                    ┌───────────────┐              │
                    │ sec/filings/  │◄─────────────┘
                    │    10-K       │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ analytics/│  │ analytics/│  │ market/   │
       │ sentiment │  │ financials│  │ prices/   │
       │           │  │           │  │   daily   │
       └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                    ┌───────────────┐
                    │   analytics/  │
                    │  portfolio/   │
                    │  risk_report  │
                    └───────────────┘


    Reading the graph:
    - "risk_report" depends on sentiment, financials, and prices
    - If 10-K filings change, we may need to refresh financials & risk_report
    - We can refresh "prices" without touching SEC data


================================================================================
KEY CONCEPTS
================================================================================

AssetKey
────────
Hierarchical identifier for a data artifact.

    AssetKey("sec", "filings", "10-K")
    ↓
    namespace: "sec"         (top-level grouping)
    path:      ["sec", "filings", "10-K"]
    name:      "10-K"        (leaf name)
    string:    "sec/filings/10-K"

Keys enable namespace queries: "Find all assets under 'sec/'"


AssetDefinition
───────────────
Declaration of what an asset IS and how it SHOULD behave.

    AssetDefinition(
        key=AssetKey("sec", "filings", "10-K"),
        description="SEC 10-K annual filings from EDGAR",
        producing_operation="ingest_filings",
        freshness_policy=FreshnessPolicy(max_lag_seconds=86400),
        dependencies=[AssetKey("sec", "index", "full")],
    )

    Fields:
    - producing_operation: Which job creates this asset
    - freshness_policy: When is this asset "too old"?
    - dependencies: Assets that must exist first


AssetMaterialization
────────────────────
Record that an asset was CREATED or UPDATED.

    AssetMaterialization(
        asset_key=AssetKey("sec", "filings", "10-K"),
        partition="CIK:0001318605",     # Optional: which slice?
        status=MaterializationStatus.SUCCESS,
        metadata={"count": 42},
        execution_id="run_abc123",      # Link to operation run
        upstream_keys=[...],            # What data was consumed
    )

    Partitions: Many assets are partitioned by date, CIK, symbol, etc.
    The key identifies WHAT, the partition identifies WHICH SLICE.


AssetObservation
────────────────
Record that an asset was CHECKED without being REBUILT.

    AssetObservation(
        asset_key=AssetKey("sec", "filings", "10-K"),
        metadata={"row_count": 42, "quality_score": 0.98},
    )

    Use cases:
    - Nightly data quality checks
    - Freshness probes
    - Anomaly detection without re-ingestion


FreshnessPolicy
───────────────
SLA definition: "This asset must be refreshed every N seconds."

    policy = FreshnessPolicy(max_lag_seconds=3600)  # 1 hour
    policy.is_stale(last_materialized_at)  # → True/False

    Enables alerts: "The 10-K asset is 6 hours stale — triggering refresh"


AssetRegistry
─────────────
In-memory registry for querying assets by namespace, group, operation, etc.

    registry.by_namespace("sec")        # All sec/* assets
    registry.by_group("market_data")    # Assets tagged with group
    registry.by_operation("ingest")      # Assets produced by this operation
    registry.dependents_of(key)         # What depends on this asset?


================================================================================
DATABASE SCHEMA: STORING ASSET METADATA
================================================================================

Asset definitions and materializations are persisted for observability::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_asset_definitions                                          │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  asset_key        VARCHAR(255)  PRIMARY KEY  -- "sec/filings/10-K"     │
    │  description      TEXT                       -- Human-readable         │
    │  producing_pipe   VARCHAR(255)               -- Operation name          │
    │  group_name       VARCHAR(100)               -- Logical grouping       │
    │  freshness_secs   INTEGER                    -- Max lag before stale   │
    │  dependencies     JSON                       -- Array of keys          │
    │  tags             JSON                       -- Arbitrary metadata     │
    │  created_at       TIMESTAMP                  -- When registered        │
    │  updated_at       TIMESTAMP                  -- Last definition change │
    └─────────────────────────────────────────────────────────────────────────┘


    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_asset_materializations                                     │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  id               SERIAL        PRIMARY KEY                             │
    │  asset_key        VARCHAR(255)  NOT NULL     -- FK to definitions      │
    │  partition_key    VARCHAR(255)               -- Optional partition     │
    │  status           VARCHAR(20)   NOT NULL     -- success|partial|failed │
    │  execution_id     VARCHAR(64)                -- Link to operation run   │
    │  metadata         JSON                       -- Row counts, checksums  │
    │  upstream_keys    JSON                       -- Consumed asset keys    │
    │  materialized_at  TIMESTAMP     NOT NULL     -- When this was built    │
    │  duration_ms      INTEGER                    -- How long it took       │
    └─────────────────────────────────────────────────────────────────────────┘


    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_asset_observations                                         │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  id               SERIAL        PRIMARY KEY                             │
    │  asset_key        VARCHAR(255)  NOT NULL                                │
    │  partition_key    VARCHAR(255)                                          │
    │  metadata         JSON          NOT NULL     -- Quality metrics, etc.  │
    │  observed_at      TIMESTAMP     NOT NULL                                │
    │  execution_id     VARCHAR(64)                -- Monitor run ID         │
    └─────────────────────────────────────────────────────────────────────────┘

    Indexes:
    - idx_mat_key_time ON core_asset_materializations(asset_key, materialized_at)
    - idx_mat_exec ON core_asset_materializations(execution_id)
    - idx_obs_key  ON core_asset_observations(asset_key)


================================================================================
LINEAGE VISUALIZATION
================================================================================

Asset tracking enables automated lineage diagrams::

    Query: "What produced this number in the risk report?"

    ┌─────────────────────┐
    │  risk_report        │  ← You're debugging this
    │  2025-01-16 09:23   │
    └─────────┬───────────┘
              │ upstream_keys
              ▼
    ┌─────────────────────┐     ┌─────────────────────┐
    │  sec/financials     │     │  market/prices      │
    │  exec-456           │     │  exec-789           │
    │  2025-01-16 08:00   │     │  2025-01-16 09:00   │
    └─────────┬───────────┘     └─────────┬───────────┘
              │                           │
              ▼                           │
    ┌─────────────────────┐              │
    │  sec/filings/10-K   │◄─────────────┘
    │  exec-123           │
    │  2025-01-15 23:00   │
    └─────────────────────┘

    Each box is an AssetMaterialization.  Each arrow is an upstream_key.
    You can trace any downstream value to its source data.


================================================================================
INTEGRATION WITH ORCHESTRATORS
================================================================================

spine-core's asset tracking integrates with:

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Orchestrator │ Integration Point                                       │
    ├───────────────┼─────────────────────────────────────────────────────────┤
    │  Dagster      │ Emit AssetMaterialization from @asset op               │
    │  Prefect      │ Emit from flow completion using result metadata        │
    │  Celery       │ PostTask signal records materialization                │
    │  Airflow      │ Use on_success_callback to emit                        │
    └─────────────────────────────────────────────────────────────────────────┘

    The key insight: your orchestrator handles WHEN to run code,
    spine-core tracks WHAT data was produced.


================================================================================
BEST PRACTICES
================================================================================

1. **Name assets by WHAT they are, not HOW they're built**::

       # BAD — names the operation
       AssetKey("daily_ingest_output")

       # GOOD — names the data
       AssetKey("sec", "filings", "10-K")

2. **Use partitions for time-series or entity-scoped data**::

       AssetMaterialization(
           asset_key=AssetKey("market", "prices", "daily"),
           partition="2025-01-16",  # Date partition
       )

3. **Record upstream_keys for automatic lineage**::

       mat = AssetMaterialization(
           asset_key=AssetKey("analytics", "risk_report"),
           upstream_keys=[
               AssetKey("sec", "filings", "10-K"),
               AssetKey("market", "prices", "daily"),
           ],
       )

4. **Set freshness policies based on business SLAs**::

       # Market data: stale after 1 hour (trading hours)
       FreshnessPolicy(max_lag_seconds=3600)

       # SEC filings: stale after 24 hours (daily update)
       FreshnessPolicy(max_lag_seconds=86400)

       # Historical data: no freshness (immutable)
       FreshnessPolicy(max_lag_seconds=None)

5. **Use observations for quality checks without rebuilding**::

       # Nightly quality probe — doesn't re-ingest, just checks
       obs = AssetObservation(
           asset_key=filings_key,
           metadata={"null_rate": 0.001, "duplicate_rate": 0.0},
       )


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/20_asset_tracking.py

See Also:
    - :mod:`spine.core.assets` — Core asset models
    - :mod:`spine.execution.dispatcher` — Operation → Asset materialization
    - :mod:`spine.api.routers.assets` — REST API for querying assets
"""
from datetime import UTC, datetime, timedelta

from spine.core.assets import (
    AssetDefinition,
    AssetKey,
    AssetMaterialization,
    AssetObservation,
    AssetRegistry,
    FreshnessPolicy,
    MaterializationStatus,
    get_asset_registry,
    register_asset,
    reset_asset_registry,
)


def main():
    print("=" * 60)
    print("Asset Tracking Examples")
    print("=" * 60)

    # Clean slate for reproducibility
    reset_asset_registry()

    # =================================================================
    # 1. AssetKey — hierarchical data identifiers
    # =================================================================
    print("\n[1] AssetKey — Hierarchical Identifiers")
    print("-" * 40)

    filings_key = AssetKey("sec", "filings", "10-K")
    prices_key = AssetKey("market", "prices", "daily")

    print(f"  Key:       {filings_key}")
    print(f"  Path:      {filings_key.path}")
    print(f"  Namespace: {filings_key.namespace}")
    print(f"  Name:      {filings_key.name}")

    # Prefix matching for namespace queries
    sec_prefix = AssetKey("sec")
    print(f"  'sec' is prefix of '{filings_key}': {sec_prefix.is_prefix_of(filings_key)}")
    print(f"  'sec' is prefix of '{prices_key}': {sec_prefix.is_prefix_of(prices_key)}")

    # Parse from slash-separated string
    parsed = AssetKey.from_string("sec/filings/10-K")
    print(f"  Parsed:    {parsed} (equals original: {parsed == filings_key})")

    # =================================================================
    # 2. Register asset definitions
    # =================================================================
    print("\n[2] Asset Definitions — Declaring What Should Exist")
    print("-" * 40)

    # Using the convenience function with global registry
    filings_def = register_asset(
        "sec", "filings", "10-K",
        description="SEC 10-K annual filings from EDGAR",
        producing_operation="ingest_filings",
        freshness_policy=FreshnessPolicy(max_lag_seconds=86400),  # 24 hours
        group="sec_data",
        tags={"source": "edgar", "priority": "high"},
    )
    print(f"  Registered: {filings_def.key}")
    print(f"  Operation:   {filings_def.producing_operation}")
    print(f"  Freshness:  max {filings_def.freshness_policy.max_lag_seconds}s lag")

    register_asset(
        "sec", "filings", "10-Q",
        description="SEC 10-Q quarterly filings",
        producing_operation="ingest_filings",
        freshness_policy=FreshnessPolicy(max_lag_seconds=86400),
        group="sec_data",
    )

    register_asset(
        "market", "prices", "daily",
        description="End-of-day equity prices",
        producing_operation="fetch_prices",
        freshness_policy=FreshnessPolicy(max_lag_seconds=3600),  # 1 hour
        group="market_data",
        dependencies=(filings_key,),  # prices depend on filings for CIK mapping
    )

    register_asset(
        "analytics", "portfolio", "risk_report",
        description="Portfolio risk metrics report",
        producing_operation="compute_risk",
        group="analytics",
        dependencies=(AssetKey("market", "prices", "daily"),),
    )

    registry = get_asset_registry()
    print(f"  Total registered: {len(registry)} assets")

    # =================================================================
    # 3. Query assets by group, namespace, operation
    # =================================================================
    print("\n[3] Querying the Asset Registry")
    print("-" * 40)

    sec_assets = registry.by_namespace("sec")
    print(f"  Namespace 'sec':     {[str(a.key) for a in sec_assets]}")

    sec_group = registry.by_group("sec_data")
    print(f"  Group 'sec_data':    {[str(a.key) for a in sec_group]}")

    ingest_assets = registry.by_operation("ingest_filings")
    print(f"  Operation 'ingest':   {[str(a.key) for a in ingest_assets]}")

    dependents = registry.dependents_of(filings_key)
    print(f"  Depends on 10-K:     {[str(a.key) for a in dependents]}")

    # =================================================================
    # 4. Record materializations — data was produced
    # =================================================================
    print("\n[4] Asset Materializations — Recording Data Production")
    print("-" * 40)

    mat = AssetMaterialization(
        asset_key=filings_key,
        partition="CIK:0001318605",
        metadata={"count": 42, "latest_date": "2025-01-15", "source": "EDGAR"},
        execution_id="exec-abc-123",
        status=MaterializationStatus.SUCCESS,
        tags={"environment": "production"},
        upstream_keys=(AssetKey("sec", "index", "full"),),
    )
    print(f"  Asset:     {mat.asset_key}")
    print(f"  Partition: {mat.partition}")
    print(f"  Status:    {mat.status.value}")
    print(f"  Metadata:  {mat.metadata}")
    print(f"  Upstream:  {[str(k) for k in mat.upstream_keys]}")

    # Partial materialization — some partitions failed
    partial = AssetMaterialization(
        asset_key=AssetKey("sec", "filings", "10-Q"),
        metadata={"success_count": 100, "failure_count": 3},
        status=MaterializationStatus.PARTIAL,
    )
    print(f"\n  Partial:   {partial.asset_key} — {partial.status.value}")

    # =================================================================
    # 5. Record observations — data was checked without re-producing
    # =================================================================
    print("\n[5] Asset Observations — Checking Without Re-building")
    print("-" * 40)

    obs = AssetObservation(
        asset_key=filings_key,
        partition="CIK:0001318605",
        metadata={"row_count": 42, "freshness_lag_hours": 2.5, "quality_score": 0.98},
        execution_id="monitor-run-456",
    )
    print(f"  Observed:  {obs.asset_key} (partition={obs.partition})")
    print(f"  Metadata:  {obs.metadata}")

    # =================================================================
    # 6. Freshness policy — staleness detection
    # =================================================================
    print("\n[6] Freshness Policy — Detecting Stale Data")
    print("-" * 40)

    policy = FreshnessPolicy(max_lag_seconds=3600)  # 1 hour

    # Fresh data (materialized 30 minutes ago)
    recent = datetime.now(UTC) - timedelta(minutes=30)
    print(f"  30 min ago:  stale={policy.is_stale(recent)}")

    # Stale data (materialized 2 hours ago)
    old = datetime.now(UTC) - timedelta(hours=2)
    print(f"  2 hours ago: stale={policy.is_stale(old)}")

    # Never materialized
    print(f"  Never:       stale={policy.is_stale(None)}")

    # =================================================================
    # 7. Serialization round-trip
    # =================================================================
    print("\n[7] Serialization — JSON-Ready Dicts")
    print("-" * 40)

    mat_dict = mat.to_dict()
    print(f"  Serialized keys: {list(mat_dict.keys())}")

    restored = AssetMaterialization.from_dict(mat_dict)
    print(f"  Round-trip:  {restored.asset_key} (partition={restored.partition})")
    print(f"  Status:      {restored.status.value}")
    print(f"  Metadata:    {restored.metadata}")

    key_dict = filings_key.to_dict()
    key_back = AssetKey.from_dict(key_dict)
    print(f"  Key round:   {key_back} (equals: {key_back == filings_key})")

    # =================================================================
    # 8. Using AssetRegistry directly (non-global)
    # =================================================================
    print("\n[8] Standalone Registry (No Global State)")
    print("-" * 40)

    local_registry = AssetRegistry()
    local_registry.register(AssetDefinition(
        key=AssetKey("custom", "model", "predictions"),
        description="ML model predictions",
        group="ml",
    ))
    local_registry.register(AssetDefinition(
        key=AssetKey("custom", "model", "features"),
        description="Feature store snapshot",
        group="ml",
    ))

    print(f"  Local registry size: {len(local_registry)}")
    print(f"  Contains predictions: {AssetKey('custom', 'model', 'predictions') in local_registry}")

    ml_assets = local_registry.by_group("ml")
    print(f"  ML group: {[str(a.key) for a in ml_assets]}")

    print("\n" + "=" * 60)
    print("All asset tracking examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
