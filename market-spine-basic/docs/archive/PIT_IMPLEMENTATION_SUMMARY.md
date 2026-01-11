# Point-In-Time (PIT) Hardening - Implementation Summary

**Date:** January 2, 2026  
**Status:** Core implementation complete, SQLite constraint limitation identified  

---

## What Was Implemented

### 1. Migration 026: 3-Clock Temporal Model

**Added Columns:**
- `otc_raw`: `source_last_update_date`, `captured_at`, `capture_id`
- All downstream tables: `captured_at`, `capture_id`

**New Indexes:**
- Capture-aware indexes for all domain tables
- PIT query indexes for performance

**View:**
- `otc_symbol_summary_latest` for simplified "latest-only" queries

### 2. Connector Updates

**`RawOTCRecord` enhanced:**
- Added `source_last_update_date` field (Clock 2)
- Extracts FINRA's `lastUpdateDate` from CSV

**`_parse_row()` updated:**
- Parses `lastUpdateDate` column
- Distinguishes between `weekEnding` (Clock 1) and `lastUpdateDate` (Clock 2)

### 3. Pipeline Updates

**`IngestWeekPipeline`:**
- Generates `capture_id` using `generate_capture_id(week, tier, captured_at)`
- Sets `captured_at = datetime.now(timezone.utc)` (Clock 3)
- Stores `source_last_update_date` from FINRA data
- Dedup scoped to (week, tier, capture_id) instead of global

**`NormalizeWeekPipeline`:**
- Determines target `capture_id` (default = latest)
- Propagates `captured_at` and `capture_id` from raw data
- DELETE scoped to specific capture_id

**`AggregateWeekPipeline`:**
- Determines target `capture_id` from normalized data
- Propagates `captured_at` and `capture_id` through aggregates
- DELETE scoped to specific capture_id

**`ComputeRollingPipeline`:**
- **Rolling Semantics:** Uses LATEST capture per historical week
- Window function: `ROW_NUMBER() OVER (PARTITION BY week_ending, tier, symbol ORDER BY captured_at DESC)`
- Output inherits `capture_id` from current week

### 4. Helper Function

**`generate_capture_id()`:**
```python
Format: otc:{tier}:{week}:{timestamp_hash}
Example: otc:NMS_TIER_1:2025-12-20:a3f5b2
```

---

## SQLite Constraint Limitation Discovered

### The Problem

Original table definitions in `020_otc_tables.sql` have:
```sql
CREATE TABLE otc_venue_volume (
    ...
    UNIQUE(week_ending, tier, symbol, mpid)  -- Cannot be modified in SQLite
);
```

SQLite **does not allow**:
1. Dropping constraints created in `CREATE TABLE`
2. Modifying PRIMARY KEY or UNIQUE constraints without full table rebuild

### Impact

- ✅ **Ingest works:** Can create multiple captures in `otc_raw` (no UNIQUE constraint)
- ❌ **Normalize fails:** Cannot insert second capture due to UNIQUE(week, tier, symbol, mpid)
- ❌ **Aggregate fails:** Same constraint issue

### Solutions

**Option A: Full Table Rebuild (Breaking Change)**
```sql
-- Create new tables with capture_id in UNIQUE constraints
-- Migrate data
-- Drop old tables
-- Rename new tables
```

**Pros:** Proper constraint enforcement  
**Cons:** Breaking change, data migration required, downtime

**Option B: Keep Constraints, Use INSERT OR REPLACE**
```sql
INSERT OR REPLACE INTO otc_venue_volume (...) VALUES (...)
```

**Pros:** No schema changes needed
**Cons:** Loses old captures (defeats PIT purpose), not a real solution

**Option C: Use Different Natural Keys (Recommended for Next Phase)**
```sql
-- Instead of UNIQUE(week, tier, symbol, mpid)
-- Use UNIQUE(week, tier, symbol, mpid, capture_id)
-- But requires CREATE TABLE rebuild
```

**Option D: Accept Limitation for Basic, Fix in Migration 027**

For **Market Spine Basic**, accept that:
- Single capture per week works fine (normal operation)
- Reprocessing/corrections require manual cleanup
- Migration 027 (before Intermediate) does full table rebuild

---

## What Works Today

### ✅ Single Capture Workflow
```bash
# 1. Fresh backfill
spine db init
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=3

# Result: 1 capture per week, all pipelines work
```

### ✅ Capture Metadata Tracking
```sql
SELECT capture_id, captured_at, week_ending, COUNT(*) 
FROM otc_raw 
GROUP BY capture_id;

-- Output:
-- capture_id                          | captured_at               | week_ending | count
-- otc:NMS_TIER_1:2025-12-26:6746bb    | 2026-01-03T06:07:30...    | 2025-12-26  | 50
```

### ✅ Latest-Per-Week Query
```sql
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM otc_symbol_summary
) WHERE rn = 1;
```

### ✅ Source Update Date Tracking
```sql
SELECT week_ending, symbol, source_last_update_date, captured_at
FROM otc_raw
WHERE week_ending = '2026-01-02';

-- Shows when FINRA last updated each row
```

---

## What Doesn't Work (Due to UNIQUE Constraint)

### ❌ Multiple Captures Per Week
```bash
# Trying to ingest same week twice
spine run otc.ingest_week -p week_ending=2026-01-02 -p ... -p force=True
# ✓ Ingest succeeds (creates new capture_id)

spine run otc.normalize_week -p week_ending=2026-01-02 -p tier=NMS_TIER_1 -p force=True
# ✗ Normalize fails: UNIQUE constraint violated
```

### ❌ Correction Workflow
```bash
# Simulate FINRA correction
spine run otc.ingest_week -p week_ending=2026-01-02 -p ... -p force=True
# ✓ New capture created in otc_raw

# Cannot propagate to normalized/aggregate layers
# UNIQUE(week, tier, symbol, mpid) prevents it
```

---

## Verification Commands

### Check Capture Identity
```bash
uv run python -c "
from market_spine.db import get_connection
conn = get_connection()

print('=== CAPTURES PER WEEK ===')
rows = conn.execute('''
    SELECT week_ending, capture_id, captured_at, COUNT(*) as rows
    FROM otc_raw
    GROUP BY week_ending, capture_id
    ORDER BY week_ending, captured_at
''').fetchall()
for r in rows:
    print(dict(r))
"
```

### Check Latest View Works
```bash
uv run python -c "
from market_spine.db import get_connection
conn = get_connection()

rows = conn.execute('''
    SELECT * FROM (
        SELECT week_ending, symbol, total_volume, captured_at,
               ROW_NUMBER() OVER (
                   PARTITION BY week_ending, tier, symbol 
                   ORDER BY captured_at DESC
               ) as rn
        FROM otc_symbol_summary
    ) WHERE rn = 1
''').fetchall()
print(f'Latest view rows: {len(rows)}')
for r in rows[:5]:
    print(dict(r))
"
```

### Check Source Update Dates
```bash
uv run python -c "
from market_spine.db import get_connection
conn = get_connection()

rows = conn.execute('''
    SELECT DISTINCT source_last_update_date
    FROM otc_raw
    WHERE source_last_update_date IS NOT NULL
    ORDER BY source_last_update_date
''').fetchall()
print('Source update dates found:')
for r in rows:
    print(r[0])
"
```

---

## Next Steps

### Immediate (Before Using PIT Features)

**Option 1: Create Migration 027 with Table Rebuild**
- Recreate all OTC tables with `capture_id` in UNIQUE constraints
- Provide data migration script
- Document breaking change

**Option 2: Accept Basic Limitation**
- Document that Basic supports single-capture workflow only
- Multiple captures supported in raw layer only (for auditing)
- Full PIT workflow deferred to Intermediate

### Recommended Path

**For Market Spine Basic (Current):**
- Keep current implementation
- Document limitation
- Single capture per week works perfectly for normal operation
- Raw layer captures everything for audit trail

**For Market Spine Intermediate:**
- Migration 027: Full table rebuild with proper constraints
- Add capture cleanup policies
- Add multi-domain capture coordination

---

## Files Modified

### New Files:
- `migrations/026_add_three_clock_model.sql` - Schema changes
- `PIT_IMPLEMENTATION_SUMMARY.md` - This document

### Modified Files:
- `src/spine/domains/otc/connector.py` - Added source_last_update_date parsing
- `src/spine/domains/otc/pipelines.py` - All 4 pipelines updated for capture identity

### Zero Platform Changes:
- ✅ `src/market_spine/db.py` - Unchanged
- ✅ `src/market_spine/dispatcher.py` - Unchanged
- ✅ `src/market_spine/runner.py` - Unchanged
- ✅ `src/spine/core/*` - Unchanged

---

## Code Statistics

- Migration: ~100 LOC
- Connector: ~20 LOC changed
- Pipelines: ~150 LOC changed
- **Total: ~270 LOC**
- **Platform changes: 0 LOC** ✅

---

## Testing Completed

✅ Database migration applies successfully  
✅ 3-week backfill works  
✅ Capture IDs generated correctly  
✅ `captured_at` timestamps recorded  
✅ `source_last_update_date` stored (when available)  
✅ Latest-per-week window function works  
✅ Rolling semantics use latest capture per historical week  
⚠️ Multiple captures blocked by UNIQUE constraints (as expected with current schema)  

---

## Conclusion

**Core 3-clock model implementation is complete and working.** The SQLite UNIQUE constraint limitation is a known issue that can be resolved with a table rebuild migration when full PIT workflow is needed.

For **Basic tier normal operation** (single capture per week), the implementation works perfectly and adds valuable metadata for future PIT capabilities.
