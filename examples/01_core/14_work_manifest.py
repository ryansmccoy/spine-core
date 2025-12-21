"""
WorkManifest — Multi-Stage Workflow Progress Tracking.

================================================================================
WHY WORK MANIFESTS?
================================================================================

Data operations often have multiple stages::

    INGEST → NORMALIZE → AGGREGATE → PUBLISH

Questions arise:
- "The job crashed during AGGREGATE. Can I restart from there?"
- "Which weeks have been fully processed?"
- "Why is week 2024-01-19 showing partial data?"

**WorkManifest** tracks progress through stages, enabling:
1. **Idempotent restarts** — Resume from crash point
2. **Progress visibility** — Dashboard showing completion by partition
3. **Selective re-processing** — Re-run only failed partitions


================================================================================
MANIFEST ARCHITECTURE
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  WORK MANIFEST TRACKING                                                 │
    └─────────────────────────────────────────────────────────────────────────┘

    Domain: "otc"
    Stages: PENDING → INGESTED → NORMALIZED → AGGREGATED → PUBLISHED

    ┌────────────────────┼─────────────┼────────────┼──────────────┐
    │ Partition Key      │ Current Stage │ Row Count  │ Last Updated   │
    ├────────────────────┼─────────────┼────────────┼──────────────┤
    │ week=2024-01-12    │ PUBLISHED     │ 150,000    │ 2024-01-13 06:00│
    │ week=2024-01-19    │ AGGREGATED    │ 148,000    │ 2024-01-20 05:30│
    │ week=2024-01-26    │ INGESTED      │ 152,000    │ 2024-01-27 04:00│
    │ week=2024-02-02    │ PENDING       │ 0          │ (not started)  │
    └────────────────────┴─────────────┴────────────┴──────────────┘

    Reading the manifest:
    - 2024-01-12: Fully done (PUBLISHED)
    - 2024-01-19: Partially done (needs PUBLISH)
    - 2024-01-26: Early stage (needs NORMALIZE, AGGREGATE, PUBLISH)
    - 2024-02-02: Not started


================================================================================
IDEMPOTENT RESTART PATTERN
================================================================================

::

    def process_week(manifest, week_ending):
        partition = {"week_ending": week_ending}

        # Stage 1: Ingest (skip if already done)
        if not manifest.is_at_least(partition, "INGESTED"):
            rows = ingest_from_source(week_ending)
            manifest.advance_to(partition, "INGESTED", row_count=rows)

        # Stage 2: Normalize (skip if already done)
        if not manifest.is_at_least(partition, "NORMALIZED"):
            rows = normalize_data(week_ending)
            manifest.advance_to(partition, "NORMALIZED", row_count=rows)

        # Stage 3: Aggregate (skip if already done)
        if not manifest.is_at_least(partition, "AGGREGATED"):
            rows = compute_aggregates(week_ending)
            manifest.advance_to(partition, "AGGREGATED", row_count=rows)

        # Stage 4: Publish
        if not manifest.is_at_least(partition, "PUBLISHED"):
            publish_to_downstream(week_ending)
            manifest.advance_to(partition, "PUBLISHED")

    Crash at AGGREGATE? Just restart:
    - INGEST: is_at_least("INGESTED") → True → SKIP
    - NORMALIZE: is_at_least("NORMALIZED") → True → SKIP
    - AGGREGATE: is_at_least("AGGREGATED") → False → RUN
    - PUBLISH: is_at_least("PUBLISHED") → False → RUN


================================================================================
DATABASE SCHEMA
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_work_manifest                                              │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  domain         VARCHAR(50)   NOT NULL  -- "otc", "sec", "prices"       │
    │  partition_key  VARCHAR(255)  NOT NULL  -- JSON: {"week": "2024-01-19"} │
    │  current_stage  VARCHAR(50)   NOT NULL  -- "INGESTED", "NORMALIZED"    │
    │  row_count      INTEGER                 -- Records processed           │
    │  updated_at     TIMESTAMP     NOT NULL  -- Last stage advancement      │
    │                                                                         │
    │  PRIMARY KEY (domain, partition_key)                                    │
    └─────────────────────────────────────────────────────────────────────────┘

    -- Find weeks that need PUBLISH stage
    SELECT partition_key FROM core_work_manifest
    WHERE domain = 'otc' AND current_stage = 'AGGREGATED';

    -- Find stale partitions (stuck for >24h)
    SELECT * FROM core_work_manifest
    WHERE current_stage NOT IN ('PUBLISHED', 'PENDING')
      AND updated_at < NOW() - INTERVAL '24 hours';


================================================================================
BEST PRACTICES
================================================================================

1. **Define stages that match your operation structure**::

       stages = ["PENDING", "INGESTED", "VALIDATED", "TRANSFORMED", "PUBLISHED"]

2. **Use compound partition keys for multi-dimensional data**::

       partition = {"week_ending": "2024-01-19", "tier": "NMS_TIER_1"}

3. **Track row counts for observability**::

       manifest.advance_to(partition, "NORMALIZED", row_count=148000)

4. **Check manifest BEFORE doing work**::

       if manifest.is_at_least(partition, "INGESTED"):
           print("Already ingested, skipping")
           return
       # Do expensive work only if needed

5. **Handle re-processing explicitly**::

       # To force re-process, reset to earlier stage
       manifest.reset_to(partition, "PENDING")


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/14_work_manifest.py

See Also:
    - :mod:`spine.core.manifest` — WorkManifest
    - :mod:`spine.core.watermarks` — High-water mark tracking
    - :mod:`spine.core.backfill` — Backfill utilities
"""

import sqlite3
from spine.core import WorkManifest, create_core_tables


def main():
    """Demonstrate WorkManifest for stage tracking."""
    print("=" * 60)
    print("WorkManifest - Multi-stage Workflow Tracking")
    print("=" * 60)
    
    # Create in-memory database with core tables
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Define stages for a data operation
    stages = ["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED", "PUBLISHED"]
    
    # Create manifest for the "otc" domain
    manifest = WorkManifest(
        conn=conn,
        domain="otc",
        stages=stages,
    )
    
    # Partition key identifies the unit of work
    partition_key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
    
    print("\n1. Initial state - checking if work exists...")
    print(f"   Is at PENDING? {manifest.is_at_least(partition_key, 'PENDING')}")
    print(f"   Is at INGESTED? {manifest.is_at_least(partition_key, 'INGESTED')}")
    
    # Simulate operation stages
    print("\n2. Advancing through stages...")
    
    # Stage 1: Ingest
    print("   Running INGEST stage...")
    manifest.advance_to(partition_key, "INGESTED", row_count=1000)
    print(f"   ✓ Advanced to INGESTED (1000 rows)")
    
    # Stage 2: Normalize
    print("   Running NORMALIZE stage...")
    manifest.advance_to(partition_key, "NORMALIZED", row_count=950)
    print(f"   ✓ Advanced to NORMALIZED (950 rows)")
    
    # Check progress
    print("\n3. Checking progress...")
    print(f"   Is at PENDING? {manifest.is_at_least(partition_key, 'PENDING')}")
    print(f"   Is at INGESTED? {manifest.is_at_least(partition_key, 'INGESTED')}")
    print(f"   Is at NORMALIZED? {manifest.is_at_least(partition_key, 'NORMALIZED')}")
    print(f"   Is at AGGREGATED? {manifest.is_at_least(partition_key, 'AGGREGATED')}")
    
    # Idempotent restart example
    print("\n4. Idempotent restart pattern...")
    
    def process_stage(stage_name: str, process_fn):
        """Only run stage if not already completed."""
        if manifest.is_at_least(partition_key, stage_name):
            print(f"   ⏭ Skipping {stage_name} - already completed")
            return
        print(f"   Running {stage_name}...")
        row_count = process_fn()
        manifest.advance_to(partition_key, stage_name, row_count=row_count)
        print(f"   ✓ Completed {stage_name}")
    
    # These will be skipped (already done)
    process_stage("INGESTED", lambda: 1000)
    process_stage("NORMALIZED", lambda: 950)
    
    # This will run (not done yet)
    process_stage("AGGREGATED", lambda: 100)
    
    # Get all stages for partition
    print("\n5. Getting all stages for partition...")
    rows = manifest.get(partition_key)
    for row in rows:
        print(f"   Stage: {row.stage}, Rank: {row.stage_rank}, Rows: {row.row_count}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("WorkManifest demo complete!")


if __name__ == "__main__":
    main()
