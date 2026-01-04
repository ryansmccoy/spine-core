# DBA Guidance - Schema Evolution & Operations

## Overview

This document provides guidance for DBAs and data engineers on managing Market Spine's database schema evolution, experimental calculations, and operational best practices.

## Schema Change Philosophy

### Core Principles

1. **Minimize schema changes** - Most new analytics should reuse existing tables
2. **Batch schema migrations** - Group related changes into quarterly releases
3. **Backward compatibility** - New columns are nullable; never break existing queries
4. **Versioning at row level** - Use `calc_version` instead of schema migrations

## Schema Change Categories

### Category 1: No Schema Change Required ✅

**Use case:** New calculation using existing grain

**Example:** Add "median venue volume" calculation
- Reuses `weekly_symbol_venue_volume` table
- Only requires:
  - New entry in `CALCS` registry
  - New calculation function in `calculations.py`
  - No schema.sql changes

**When this applies:**
- Same business keys (week, tier, symbol, mpid)
- Same metrics (just different aggregation)
- Same capture_id strategy

**Pattern:**
```python
# packages/spine-domains/.../schema.py
CALCS = {
    # Existing
    "weekly_symbol_venue_volume": {...},
    
    # New (no schema change)
    "weekly_symbol_venue_volume_median": {
        "versions": ["v1"],
        "current": "v1",
        "table": "finra_otc_transparency_weekly_symbol_venue_volume",  # Same table!
        "business_keys": ["week_ending", "tier", "symbol", "mpid"],
        "description": "Median venue volume (uses same table as mean)"
    }
}
```

### Category 2: Add Columns to Existing Table ⚠️

**Use case:** Enrich existing calculation with new metrics

**Example:** Add `venue_rank` to venue volume table

**Required changes:**
```sql
-- migrations/schema_v2.sql
ALTER TABLE finra_otc_transparency_weekly_symbol_venue_volume
ADD COLUMN venue_rank INTEGER;  -- Nullable for backward compat
```

**Deployment strategy:**
1. Deploy code that handles NULL gracefully
2. Apply schema change (ALTER TABLE)
3. Backfill new column for historical data (optional)

**Rollback plan:**
- If column unused: safe to ignore (NULL values)
- If must remove: requires data migration

**When to avoid:**
- If column is frequently NULL (poor design)
- If it changes semantics of existing rows

### Category 3: New Table (New Grain) 🔴

**Use case:** Fundamentally different aggregation level

**Example:** Daily symbol volume (vs weekly)

**Required changes:**
```sql
-- New table with different grain
CREATE TABLE IF NOT EXISTS finra_otc_transparency_daily_symbol_volume (
    week_ending TEXT NOT NULL,  -- Still partitioned by week for backfill
    trade_date TEXT NOT NULL,   -- New grain: daily
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    ...
    UNIQUE(week_ending, trade_date, tier, symbol, capture_id)
);
```

**Checklist:**
- [ ] New table follows naming convention: `{domain}_{entity}_{grain}`
- [ ] Includes all 3 clocks (business, source, capture)
- [ ] Has proper indexes (see Index Design below)
- [ ] Has `*_latest` view for common queries
- [ ] Registered in `CALCS` with correct `table` name

## Batching Schema Changes

### Quarterly Release Cycle

**Timeline:**
- **Q1 Planning (Jan):** Collect feature requests, design schemas
- **Q1 Implementation (Feb):** Code + schema changes, test in staging
- **Q1 Release (Mar):** Deploy to production, monitor
- **Repeat for Q2, Q3, Q4**

**Migration script organization:**
```
migrations/
  schema.sql          # Base schema (foundation)
  2025_q1_finra.sql   # Q1: FINRA enhancements
  2025_q2_trace.sql   # Q2: TRACE domain added
  2025_q3_calcs.sql   # Q3: New calculation tables
```

**Applying migrations:**
```bash
# Base schema (first time)
sqlite3 spine.db < migrations/schema.sql

# Quarterly updates
sqlite3 spine.db < migrations/2025_q1_finra.sql
sqlite3 spine.db < migrations/2025_q2_trace.sql
```

**Migration tracking:**
```sql
-- Automatically tracked in _migrations table
SELECT * FROM _migrations ORDER BY applied_at DESC;

-- Output:
-- 2025_q3_calcs.sql      | 2025-09-15T10:00:00Z
-- 2025_q2_trace.sql      | 2025-06-10T09:30:00Z
-- 2025_q1_finra.sql      | 2025-03-05T11:15:00Z
-- schema.sql             | 2025-01-01T08:00:00Z
```

## Experimental Calculations Strategy

### Option A: Scratch Tables (Recommended for R&D)

**Use case:** Analyst testing new metric, not production-ready

**Pattern:**
```sql
-- Temporary table for experimentation
CREATE TABLE IF NOT EXISTS _scratch_analyst_hhi_variant (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    hhi_weighted REAL,
    hhi_log_normalized REAL,
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL
);
```

**Naming:** Prefix with `_scratch_` or `_exp_`

**Lifecycle:**
- Created ad-hoc by analyst
- Not in core schema.sql
- Dropped after analysis complete
- If proves useful → promote to production table in next quarterly release

**Promotion checklist:**
- [ ] Remove `_scratch_` prefix
- [ ] Add proper indexes
- [ ] Add to CALCS registry
- [ ] Write production-grade calculation function
- [ ] Add tests

### Option B: Views (Recommended for Derived Metrics)

**Use case:** New metric derived from existing tables without new storage

**Pattern:**
```sql
-- View for experimental metric (no new storage)
CREATE VIEW IF NOT EXISTS finra_otc_transparency_venue_volume_percentiles AS
SELECT 
    week_ending,
    tier,
    symbol,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_volume) AS p50_volume,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_volume) AS p95_volume,
    captured_at,
    capture_id
FROM finra_otc_transparency_weekly_symbol_venue_volume
GROUP BY week_ending, tier, symbol, capture_id;
```

**Advantages:**
- No new storage
- Automatically updates when base table changes
- Easy to drop without data loss
- Can promote to materialized table later if slow

**When to materialize:**
- View becomes too slow (> 5 seconds)
- Used in critical dashboards
- Required for API endpoints with SLA

## Index Design Patterns

### Standard Index Set for Time-Series Tables

Every time-series calculation table should have:

```sql
-- 1. Capture index (as-of queries)
CREATE INDEX IF NOT EXISTS idx_{table}_capture 
    ON {table}(week_ending, tier, capture_id);

-- 2. Symbol lookup (trading desk queries)
CREATE INDEX IF NOT EXISTS idx_{table}_symbol 
    ON {table}(symbol, week_ending, tier);

-- 3. Latest queries (most common pattern)
CREATE INDEX IF NOT EXISTS idx_{table}_latest 
    ON {table}(week_ending, tier, captured_at DESC);
```

**Example for new table:**
```sql
CREATE TABLE finra_otc_transparency_daily_symbol_volume (...);

CREATE INDEX idx_daily_vol_capture ON finra_otc_transparency_daily_symbol_volume(week_ending, trade_date, tier, capture_id);
CREATE INDEX idx_daily_vol_symbol ON finra_otc_transparency_daily_symbol_volume(symbol, trade_date);
CREATE INDEX idx_daily_vol_latest ON finra_otc_transparency_daily_symbol_volume(trade_date, tier, captured_at DESC);
```

### When to Add Custom Indexes

**Symptom:** Slow query on production endpoint

**Investigation:**
```sql
-- SQLite: check query plan
EXPLAIN QUERY PLAN
SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume
WHERE symbol = 'AAPL' AND week_ending >= '2025-01-01';

-- Output shows: SCAN TABLE (bad) vs SEARCH TABLE USING INDEX (good)
```

**Fix:** Add covering index
```sql
CREATE INDEX idx_custom_symbol_week 
    ON finra_otc_transparency_weekly_symbol_venue_volume(symbol, week_ending);
```

**Guideline:** Don't add indexes preemptively (disk space cost). Wait for real query patterns.

## Version Management Strategies

### Strategy 1: Calculation Versioning (Preferred)

**Use case:** Change calculation logic without schema change

**Pattern:**
```python
# Old calculation stays in table
WeeklySymbolVenueVolumeRow(
    calc_name="weekly_symbol_venue_volume",
    calc_version="v1",  # Old version
    ...
)

# New calculation writes to same table with v2
WeeklySymbolVenueVolumeRow(
    calc_name="weekly_symbol_venue_volume",
    calc_version="v2",  # New version with different logic
    ...
)
```

**Query patterns:**
```sql
-- Latest of v2 only
SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume
WHERE calc_version = 'v2'
  AND (week_ending, tier, symbol, mpid, captured_at) IN (
      SELECT week_ending, tier, symbol, mpid, MAX(captured_at)
      FROM finra_otc_transparency_weekly_symbol_venue_volume
      WHERE calc_version = 'v2'
      GROUP BY week_ending, tier, symbol, mpid
  );

-- Or create view
CREATE VIEW finra_otc_transparency_weekly_symbol_venue_volume_v2_latest AS
SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume
WHERE calc_version = 'v2'
  AND ... (latest logic);
```

**Advantages:**
- Both versions coexist
- A/B testing easy
- Gradual migration
- Rollback trivial (just query v1)

**Disadvantages:**
- Table grows (2x storage)
- Indexes cover both versions
- Must filter by `calc_version` in all queries

### Strategy 2: New Table for Breaking Changes

**Use case:** Schema incompatible with old version

**Pattern:**
```sql
-- Old table (deprecated but kept for historical queries)
CREATE TABLE finra_otc_transparency_weekly_symbol_venue_volume_v1 (...);

-- New table (incompatible schema)
CREATE TABLE finra_otc_transparency_weekly_symbol_venue_volume_v2 (
    -- Different columns, can't reuse v1 table
    ...
);

-- Alias to "current" for new code
CREATE VIEW finra_otc_transparency_weekly_symbol_venue_volume AS
SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume_v2;
```

**When to use:**
- Business keys changed (grain changed)
- Metrics fundamentally different (can't compare v1 vs v2)
- Old table small enough to archive

## Column Naming Standards

### Temporal Columns

```sql
-- Clock 1: Business time (when trading occurred)
week_ending TEXT NOT NULL,
trade_date TEXT,

-- Clock 2: Source system time (when FINRA updated)
source_last_update_date TEXT,

-- Clock 3: Platform time (when we captured)
captured_at TEXT NOT NULL,
capture_id TEXT NOT NULL,

-- Execution tracking
calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
```

### Metrics

```sql
-- Volumes: use _volume suffix
total_volume INTEGER,
venue_volume INTEGER,
tier_volume INTEGER,

-- Shares/percentages: use _share suffix (0.0 to 1.0)
venue_share REAL CHECK (venue_share BETWEEN 0 AND 1),
tier_volume_share REAL CHECK (tier_volume_share BETWEEN 0 AND 1),

-- Counts: use _count suffix
trade_count INTEGER,
venue_count INTEGER,

-- Indexes: use hhi, gini, entropy (not _index to avoid SQL keyword)
hhi REAL CHECK (hhi BETWEEN 0 AND 1),
```

### Identifiers

```sql
-- Business keys
symbol TEXT NOT NULL,       -- Security identifier
mpid TEXT NOT NULL,         -- Market participant ID
tier TEXT NOT NULL,         -- NMS_TIER_1, NMS_TIER_2, OTC

-- Metadata
calc_name TEXT NOT NULL,
calc_version TEXT NOT NULL,
execution_id TEXT NOT NULL,
batch_id TEXT,
```

## Data Quality Constraints

### Use CHECK Constraints for Invariants

```sql
-- Shares must sum to 1.0
venue_share REAL CHECK (venue_share BETWEEN 0 AND 1),

-- HHI bounded
hhi REAL CHECK (hhi BETWEEN 0 AND 1),

-- Volumes non-negative
total_volume INTEGER CHECK (total_volume >= 0),

-- Dates in ISO 8601
week_ending TEXT CHECK (week_ending GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
```

**Advantages:**
- Database enforces invariants
- Catches calculation bugs immediately
- Self-documenting schema

**Testing:**
```python
# This should raise an IntegrityError
conn.execute(
    "INSERT INTO ... VALUES (..., hhi = 1.5, ...)"  # Invalid: HHI > 1.0
)
# sqlite3.IntegrityError: CHECK constraint failed: hhi BETWEEN 0 AND 1
```

## Operational Best Practices

### 1. Use Transactions for Multi-Table Updates

```python
with conn:
    # Delete old calculation
    conn.execute("DELETE FROM finra_otc_transparency_weekly_symbol_venue_volume WHERE capture_id = ?", (capture_id,))
    
    # Insert new calculation
    conn.executemany(
        "INSERT INTO finra_otc_transparency_weekly_symbol_venue_volume VALUES (...)",
        rows
    )
    
    # Update manifest
    conn.execute("UPDATE core_manifest SET row_count = ? WHERE ...", (len(rows),))
    
    # All-or-nothing: if any fails, entire transaction rolls back
```

### 2. Vacuum After Large Deletes

```bash
# After deleting old captures or scratch tables
sqlite3 spine.db "VACUUM;"

# This reclaims disk space (otherwise just marked as free)
```

### 3. Analyze After Schema Changes

```sql
-- Update SQLite statistics for query optimizer
ANALYZE;

-- Or target specific tables
ANALYZE finra_otc_transparency_weekly_symbol_venue_volume;
```

### 4. Monitor Table Sizes

```sql
-- Check table sizes (requires dbstat virtual table)
SELECT 
    name,
    SUM(pgsize) / 1024 / 1024 AS size_mb
FROM dbstat
WHERE name LIKE 'finra_otc%'
GROUP BY name
ORDER BY size_mb DESC;
```

### 5. Archive Old Captures

**Strategy:** Keep last 2 years of captures, archive older

```sql
-- Find old captures (> 2 years)
SELECT DISTINCT capture_id, MIN(captured_at) as oldest
FROM finra_otc_transparency_raw
WHERE captured_at < date('now', '-2 years')
GROUP BY capture_id;

-- Archive to cold storage (S3, Glacier)
sqlite3 spine.db ".dump --where=\"capture_id='old-capture-id'\"" > archive_2023.sql

-- Delete from production
DELETE FROM finra_otc_transparency_raw 
WHERE capture_id = 'old-capture-id';

VACUUM;
```

## Troubleshooting Common Issues

### Issue 1: Slow Query on Latest Data

**Symptom:** Query takes > 5 seconds
```sql
SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume
WHERE symbol = 'AAPL'
ORDER BY captured_at DESC
LIMIT 10;
```

**Diagnosis:**
```sql
EXPLAIN QUERY PLAN [query];
-- Shows: SCAN TABLE (no index used)
```

**Fix:** Add covering index
```sql
CREATE INDEX idx_venue_vol_symbol_latest 
    ON finra_otc_transparency_weekly_symbol_venue_volume(symbol, captured_at DESC);
```

### Issue 2: Constraint Violation on Insert

**Symptom:** `CHECK constraint failed: venue_share BETWEEN 0 AND 1`

**Cause:** Calculation bug (shares don't sum to 1.0)

**Fix:**
1. Check calculation logic
2. Add validation in calculation function
3. Add test that verifies invariant

### Issue 3: Duplicate Key Error

**Symptom:** `UNIQUE constraint failed: finra_otc_transparency_weekly_symbol_venue_volume.week_ending, .tier, ...`

**Cause:** Attempting to insert same (week, tier, symbol, mpid, capture_id) twice

**Fix:** Use UPSERT pattern
```sql
INSERT INTO ... VALUES (...)
ON CONFLICT(week_ending, tier, symbol, mpid, capture_id) DO UPDATE SET
    total_volume = excluded.total_volume,
    trade_count = excluded.trade_count,
    updated_at = datetime('now');
```

## Schema Evolution Checklist

Before deploying schema changes:

- [ ] **Backward compatible:** Existing queries still work
- [ ] **Indexes added:** Performance tested in staging
- [ ] **Migration script:** Tested on copy of production data
- [ ] **Rollback plan:** Can revert if issues arise
- [ ] **Documentation updated:** schema.sql comments, this guide
- [ ] **Tests passing:** All existing + new tests green
- [ ] **Monitoring configured:** Alerts for slow queries, constraint violations
- [ ] **Stakeholders notified:** Trading desks, API consumers informed

## Summary

**Key Takeaways:**

1. **Prefer no-schema changes** - Version at row level when possible
2. **Batch changes quarterly** - Don't migrate schema every sprint
3. **Use views for experiments** - Promote to tables only if needed
4. **Index for real queries** - Don't guess, profile production
5. **Enforce invariants in schema** - CHECK constraints catch bugs early
6. **Vacuum and analyze** - Keep SQLite healthy

**When in doubt:**
- Can this be a view instead of a table? → Use view
- Can this reuse an existing table? → Reuse with `calc_version`
- Does this need an index? → Measure first, add if slow
- Should this be in core schema? → Only if production-grade
