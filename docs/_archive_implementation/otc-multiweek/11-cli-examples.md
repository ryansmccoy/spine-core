# 11: CLI Examples

> **Purpose**: Complete CLI command examples for running the multi-week OTC workflow.

---

## Quick Start

```powershell
# 1. Initialize database with all migrations
spine db init

# 2. Run 6-week backfill with fixture data
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc

# 3. Verify results
sqlite3 spine.db "SELECT week_ending, stage, row_count_inserted FROM otc_week_manifest ORDER BY week_ending"
```

---

## Pipeline Commands

### `otc.ingest_week`

Ingest a single week's OTC data from a file.

```powershell
# Basic usage
spine run otc.ingest_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p file_path=data/fixtures/otc/week_2025-12-26.psv

# Force re-ingest (overwrite existing)
spine run otc.ingest_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p file_path=data/fixtures/otc/week_2025-12-26.psv `
  -p force=true
```

**Expected Output:**
```
Pipeline: otc.ingest_week
Status: COMPLETED
Duration: 0.15s
Metrics:
  week_ending: 2025-12-26
  tier: NMS_TIER_1
  records_parsed: 12
  records_inserted: 12
  records_rejected: 0
  records_skipped: 0
  source_sha256: 8f7d9e2a...
```

---

### `otc.normalize_week`

Normalize raw records for a single week.

```powershell
# Basic usage (after ingest)
spine run otc.normalize_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26

# Reject zero-volume records
spine run otc.normalize_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p reject_zero_volume=true
```

**Expected Output:**
```
Pipeline: otc.normalize_week
Status: COMPLETED
Duration: 0.08s
Metrics:
  week_ending: 2025-12-26
  tier: NMS_TIER_1
  records_read: 12
  records_accepted: 12
  records_rejected: 0
```

---

### `otc.aggregate_week`

Compute symbol summaries and venue shares for a week.

```powershell
# Basic usage (after normalize)
spine run otc.aggregate_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26
```

**Expected Output:**
```
Pipeline: otc.aggregate_week
Status: COMPLETED
Duration: 0.05s
Metrics:
  week_ending: 2025-12-26
  tier: NMS_TIER_1
  symbols_aggregated: 5
  venues_aggregated: 4
  calculation_version: v1.0.0
  quality_checks_passed: 5
  quality_checks_warned: 0
  quality_checks_failed: 0
```

---

### `otc.compute_rolling_6w`

Compute 6-week rolling metrics.

```powershell
# For latest aggregated week
spine run otc.compute_rolling_6w -p tier=NMS_TIER_1

# For specific week
spine run otc.compute_rolling_6w `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26
```

**Expected Output:**
```
Pipeline: otc.compute_rolling_6w
Status: COMPLETED
Duration: 0.12s
Metrics:
  week_ending: 2025-12-26
  tier: NMS_TIER_1
  symbols_computed: 5
  symbols_complete_window: 5
  symbols_incomplete_window: 0
  rolling_version: v1.0.0
```

---

### `otc.research_snapshot_week`

Build denormalized research snapshot.

```powershell
# Build snapshot for a week
spine run otc.research_snapshot_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26
```

**Expected Output:**
```
Pipeline: otc.research_snapshot_week
Status: COMPLETED
Duration: 0.06s
Metrics:
  week_ending: 2025-12-26
  tier: NMS_TIER_1
  symbols_snapshotted: 5
  symbols_with_rolling: 5
  snapshot_version: v1.0.0
```

---

### `otc.backfill_range`

Orchestrate full multi-week workflow.

```powershell
# 6 weeks back from today
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc

# Explicit date range
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p start_week=2025-11-21 `
  -p end_week=2025-12-26 `
  -p source_dir=data/fixtures/otc

# Force reprocess everything
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc `
  -p force=true

# Skip rolling and snapshot (just ETL)
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc `
  -p skip_rolling=true `
  -p skip_snapshot=true
```

**Expected Output:**
```
Pipeline: otc.backfill_range
Status: COMPLETED
Duration: 2.34s
Metrics:
  batch_id: backfill_NMS_TIER_1_2025-11-21_2025-12-26_20260102T150022
  tier: NMS_TIER_1
  weeks_requested: 6
  weeks_processed: 6
  total_ingested: 71
  total_normalized: 69
  total_rejected: 2
  rolling_computed: true
  snapshot_built: true
  errors: []
```

---

## Database Queries

### Check Manifest Status

```powershell
sqlite3 spine.db "
SELECT 
    week_ending,
    stage,
    row_count_inserted as raw,
    row_count_normalized as norm,
    row_count_rejected as rej
FROM otc_week_manifest
WHERE tier = 'NMS_TIER_1'
ORDER BY week_ending
"
```

**Output:**
```
2025-11-21|AGGREGATED|11|11|0
2025-11-28|AGGREGATED|12|12|0
2025-12-05|AGGREGATED|12|11|1
2025-12-12|AGGREGATED|12|12|0
2025-12-19|AGGREGATED|12|11|1
2025-12-26|SNAPSHOT|12|12|0
```

---

### View Rejects

```powershell
sqlite3 spine.db "
SELECT 
    week_ending,
    stage,
    reason_code,
    reason_detail
FROM otc_rejects
WHERE tier = 'NMS_TIER_1'
"
```

**Output:**
```
2025-12-05|NORMALIZE|INVALID_SYMBOL|Invalid symbol format: 'BAD$YM'
2025-12-19|NORMALIZE|NEGATIVE_VOLUME|total_shares=-50000
```

---

### View Rolling Metrics

```powershell
sqlite3 spine.db "
SELECT 
    symbol,
    avg_6w_volume,
    trend_direction,
    printf('%.1f%%', trend_pct) as trend,
    weeks_in_window,
    CASE is_complete_window WHEN 1 THEN 'YES' ELSE 'NO' END as complete
FROM otc_symbol_rolling_6w
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY avg_6w_volume DESC
"
```

**Output:**
```
AAPL|3623333|UP|10.2%|6|YES
NVDA|3275000|DOWN|-8.5%|6|YES
TSLA|1731666|UP|28.3%|6|YES
META|1408333|UP|15.7%|6|YES
MSFT|958333|FLAT|3.2%|6|YES
```

---

### View Research Snapshot

```powershell
sqlite3 spine.db "
SELECT 
    symbol,
    total_volume,
    venue_count,
    top_venue_mpid,
    rolling_trend_direction,
    quality_status
FROM otc_research_snapshot
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY total_volume DESC
"
```

**Output:**
```
AAPL|3860000|3|NITE|UP|PASS
NVDA|2950000|2|NITE|DOWN|PASS
TSLA|1930000|2|NITE|UP|PASS
META|1630000|3|NITE|UP|PASS
MSFT|1020000|2|JANE|FLAT|PASS
```

---

### View Quality Checks

```powershell
sqlite3 spine.db "
SELECT 
    week_ending,
    check_name,
    status,
    check_value
FROM otc_quality_checks
WHERE tier = 'NMS_TIER_1' AND pipeline_name = 'otc.aggregate_week'
ORDER BY week_ending, check_name
"
```

---

### Lineage Query: Find All Work from a Batch

```powershell
sqlite3 spine.db "
SELECT 
    'raw' as table_name, COUNT(*) as record_count
FROM otc_raw 
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'normalized', COUNT(*) 
FROM otc_venue_volume 
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'summary', COUNT(*) 
FROM otc_symbol_summary 
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'rolling', COUNT(*) 
FROM otc_symbol_rolling_6w 
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'snapshot', COUNT(*) 
FROM otc_research_snapshot 
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
"
```

**Output:**
```
raw|71
normalized|69
summary|30
rolling|5
snapshot|5
```

---

## Error Scenarios

### Missing Source File

```powershell
spine run otc.ingest_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p file_path=nonexistent.psv
```

**Output:**
```
Pipeline: otc.ingest_week
Status: FAILED
Error: File not found: nonexistent.psv
```

---

### Invalid Week Ending (Not Friday)

```powershell
spine run otc.ingest_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-25 `
  -p file_path=data/fixtures/otc/week_2025-12-26.psv
```

**Output:**
```
Pipeline: otc.ingest_week
Status: FAILED
Error: week_ending must be a Friday, got 2025-12-25 (Thursday). Nearest Friday: 2025-12-26
```

---

### Prerequisite Not Met

```powershell
# Try to normalize without ingesting first
spine run otc.normalize_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26
```

**Output:**
```
Pipeline: otc.normalize_week
Status: FAILED
Error: Week 2025-12-26/NMS_TIER_1 not found in manifest. Run otc.ingest_week first.
```

---

## Troubleshooting

### Check What's in the Database

```powershell
# Table row counts
sqlite3 spine.db "
SELECT 
    'otc_raw' as tbl, COUNT(*) as cnt FROM otc_raw
UNION ALL SELECT 'otc_venue_volume', COUNT(*) FROM otc_venue_volume
UNION ALL SELECT 'otc_symbol_summary', COUNT(*) FROM otc_symbol_summary
UNION ALL SELECT 'otc_rejects', COUNT(*) FROM otc_rejects
UNION ALL SELECT 'otc_quality_checks', COUNT(*) FROM otc_quality_checks
"
```

### Reset and Start Over

```powershell
# Delete database
Remove-Item spine.db -ErrorAction SilentlyContinue

# Reinitialize
spine db init

# Run backfill fresh
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=6 -p source_dir=data/fixtures/otc
```

---

## Next: Read [12-checklist.md](12-checklist.md) for reviewer verification checklist
