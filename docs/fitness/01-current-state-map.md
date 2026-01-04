# 01 — Current State Map

> **Factual inventory of where calculations, tables, and constraints live today.**

---

## Calculations: Location & Invocation

### Where Calcs Are Implemented

| Calc | File | Function/Class |
|------|------|----------------|
| Symbol Summary | `packages/spine-domains/src/spine/domains/finra/otc_transparency/calculations.py` | `aggregate_to_symbol_level()` |
| Rolling Stats | `packages/spine-domains/src/spine/domains/finra/otc_transparency/calculations.py` | `compute_rolling_stats()`, `compute_rolling_for_week()` |
| Venue Dedup | `packages/spine-domains/src/spine/domains/finra/otc_transparency/calculations.py` | `dedupe_venue_rows()` |
| Symbol Summaries (compat) | `packages/spine-domains/src/spine/domains/finra/otc_transparency/calculations.py` | `compute_symbol_summaries()` |

### How Calcs Are Invoked

Pipelines in `packages/spine-domains/src/spine/domains/finra/otc_transparency/pipelines.py`:

| Pipeline | Registered Name | Invokes |
|----------|-----------------|---------|
| `IngestWeekPipeline` | `finra.otc_transparency.ingest_week` | File/API source → raw table |
| `NormalizeWeekPipeline` | `finra.otc_transparency.normalize_week` | raw → venue_volume |
| `AggregateWeekPipeline` | `finra.otc_transparency.aggregate_week` | `aggregate_to_symbol_level()` → symbol_summary |
| `ComputeRollingPipeline` | `finra.otc_transparency.compute_rolling` | rolling logic → symbol_rolling_6w |
| `BackfillPipeline` | `finra.otc_transparency.backfill_range` | Orchestrates ingest→normalize→aggregate |

**Invocation path:**
```
CLI: spine run finra.otc_transparency.aggregate_week -p week_ending=... -p tier=...
  → Dispatcher.submit()
  → Runner.run(pipeline)
  → Pipeline.run()  # calls pure calc functions
```

---

## Tables: Current Schema

### Location
- Schema DDL: `market-spine-basic/migrations/schema.sql`
- Table constants: `packages/spine-domains/src/spine/domains/finra/otc_transparency/schema.py`

### Table Inventory

| Logical Name | Physical Table | Purpose |
|--------------|----------------|---------|
| `raw` | `finra_otc_transparency_raw` | Raw ingested data from FINRA files/API |
| `venue_volume` | `finra_otc_transparency_venue_volume` | Normalized venue-level data |
| `symbol_summary` | `finra_otc_transparency_symbol_summary` | Aggregated symbol-level stats |
| `venue_share` | `finra_otc_transparency_venue_share` | Venue market share (defined in schema, not yet populated) |
| `rolling` | `finra_otc_transparency_symbol_rolling_6w` | Rolling 6-week statistics |
| `liquidity` | `finra_otc_transparency_liquidity_score` | Liquidity scores (defined, not populated) |
| `snapshot` | `finra_otc_transparency_research_snapshot` | Wide denormalized research view |

### Core Infrastructure Tables

| Table | Purpose |
|-------|---------|
| `core_manifest` | Tracks pipeline stage completion per (domain, partition_key, stage) |
| `core_rejects` | Stores rejected records with reason codes |
| `core_quality` | Stores quality check results (PASS/WARN/FAIL) |
| `core_executions` | Execution records (placeholder, not used in Basic tier) |
| `_migrations` | Tracks applied migrations |

---

## Uniqueness Constraints

### Current Enforcement

| Table | Unique Constraint |
|-------|-------------------|
| `finra_otc_transparency_raw` | `(week_ending, tier, symbol, mpid, capture_id)` |
| `finra_otc_transparency_venue_volume` | `(week_ending, tier, symbol, mpid, capture_id)` |
| `finra_otc_transparency_symbol_summary` | `(week_ending, tier, symbol, capture_id)` |
| `finra_otc_transparency_venue_share` | `(week_ending, tier, mpid, capture_id)` |
| `finra_otc_transparency_symbol_rolling_6w` | `(week_ending, tier, symbol, capture_id)` |
| `finra_otc_transparency_liquidity_score` | `(week_ending, tier, symbol, capture_id)` |
| `finra_otc_transparency_research_snapshot` | `(week_ending, tier, symbol, capture_id)` |
| `core_manifest` | `(domain, partition_key, stage)` |

**Pattern**: All domain tables include `capture_id` in uniqueness to allow multiple point-in-time captures of the same business data.

---

## Idempotency: Current Mechanism

### Strategy: DELETE + INSERT per capture

All pipelines follow this pattern:

```python
# 1. Resolve target capture_id (use latest if not specified)
target_capture_id = self.params.get("capture_id") or get_latest_capture()

# 2. Delete existing data for THIS capture only
conn.execute("""
    DELETE FROM table WHERE week_ending = ? AND tier = ? AND capture_id = ?
""", (week, tier, target_capture_id))

# 3. Recompute and insert
for row in computed_rows:
    conn.execute("INSERT INTO table ...")

# 4. Update manifest
manifest.advance_to(key, stage, ...)
```

### Manifest-Based Skip Logic

Before recomputation, pipelines check:
```python
if not force and manifest.is_at_least(key, "AGGREGATED"):
    return PipelineResult(status=COMPLETED, metrics={"skipped": True})
```

---

## Temporal Model: Three Clocks

### Clock Fields

| Clock | Field(s) | Meaning |
|-------|----------|---------|
| Clock 1 | `week_ending` | Business time (when trading occurred) |
| Clock 2 | `source_last_update_date` | Source system time (FINRA's update timestamp) |
| Clock 3 | `captured_at`, `capture_id` | Platform time (when we ingested) |

### Current Representation

**Raw table:**
```sql
week_ending TEXT NOT NULL,              -- Clock 1
source_last_update_date TEXT,           -- Clock 2
captured_at TEXT NOT NULL,              -- Clock 3
capture_id TEXT NOT NULL,               -- Clock 3 (deterministic ID)
```

**Derived tables propagate Clock 3:**
```sql
captured_at TEXT NOT NULL,              -- Propagated from upstream
capture_id TEXT NOT NULL,               -- Propagated from upstream
```

### capture_id Format
```
finra.otc_transparency:{tier}:{week_ending}:{timestamp_hash}
Example: finra.otc_transparency:OTC:2025-12-26:a3f5b2
```

---

## Query Patterns: Latest vs As-Of

### Latest (Default)

Views defined in `schema.sql`:
```sql
CREATE VIEW IF NOT EXISTS finra_otc_transparency_symbol_summary_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_symbol_summary
) WHERE rn = 1;
```

Similar views exist for:
- `finra_otc_transparency_venue_share_latest`
- `finra_otc_transparency_symbol_rolling_6w_latest`

### As-Of (Point-in-Time)

Query by specific `capture_id`:
```sql
SELECT * FROM finra_otc_transparency_symbol_summary
WHERE week_ending = ? AND tier = ? AND capture_id = ?
```

Or by `captured_at` timestamp:
```sql
SELECT * FROM finra_otc_transparency_symbol_summary
WHERE week_ending = ? AND tier = ? AND captured_at <= ?
ORDER BY captured_at DESC LIMIT 1
```

---

## Indexes: Current State

### Raw Table
```sql
idx_finra_otc_transparency_raw_week (week_ending)
idx_finra_otc_transparency_raw_symbol (symbol)
idx_finra_otc_transparency_raw_capture (week_ending, tier, capture_id)
idx_finra_otc_transparency_raw_pit (week_ending, tier, captured_at DESC)
```

### Venue Volume
```sql
idx_finra_otc_transparency_venue_volume_week (week_ending)
idx_finra_otc_transparency_venue_volume_symbol (symbol)
idx_finra_otc_transparency_venue_volume_capture (week_ending, tier, capture_id)
```

### Symbol Summary
```sql
idx_finra_otc_transparency_symbol_summary_capture (week_ending, tier, capture_id)
idx_finra_otc_transparency_symbol_summary_pit (week_ending, tier, captured_at DESC)
```

### Rolling / Venue Share / Liquidity
```sql
idx_finra_otc_transparency_symbol_rolling_6w_capture (week_ending, tier, capture_id)
idx_finra_otc_transparency_venue_share_capture (week_ending, tier, capture_id)
idx_finra_otc_transparency_liquidity_score_capture (week_ending, tier, capture_id)
```

---

## Gaps Identified

1. ~~**Venue share calc not implemented**~~ ✅ Implemented in `compute_venue_share_v1()`
2. **Liquidity score calc not implemented** — table exists but no pipeline populates it
3. ~~**No calc versioning**~~ ✅ Added `CALCS` registry with `get_current_version()`
4. ~~**No invariant checks**~~ ✅ Added `validate_venue_share_invariants()`
5. **No deprecation mechanism** — `is_deprecated()` helper added, enforcement pending
6. **Index on symbol missing for summary** — only has capture-based indexes
