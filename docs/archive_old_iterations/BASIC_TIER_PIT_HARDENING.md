# Market Spine Basic: Point-In-Time Hardening Design (3-Clock Model)

**Date:** January 2, 2026  
**Status:** Pre-Intermediate Hardening Pass  
**Goal:** Minimal changes to support point-in-time semantics using real FINRA data structure  

---

## 1. The 3-Clock Model (Critical Foundation)

### Real FINRA Data Structure

**Actual FINRA CSV columns:**
```
tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|
totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
```

**Example Row:**
```
NMS Tier 1|A|Agilent Technologies Inc|VIRTU Americas LLC|NITE|
76630|1001|2025-12-22
```

**Key Insight:** FINRA publishes weekly totals (for a week ending on Friday), but each row has a `lastUpdateDate` showing when FINRA last updated that row in their system. This is NOT the same as the week_ending.

### Three Temporal Dimensions

#### Clock 1: Business Time (week_ending)
**What it represents:** The Friday that ends the reporting week (effective time)  
**Example value:** 2025-12-20  
**Semantics:** "This data describes trading activity for the week ending 2025-12-20"

**Questions Clock 1 Answers:**
1. What was the total volume for symbol A during the week ending 2025-12-20?
2. Which week had the highest trading activity for symbol AA?
3. Show me the 6-week rolling average as of week ending 2026-01-02.
4. What were the top 5 symbols by volume for the week ending 2025-12-27?
5. How does week 2025-12-20 compare to week 2025-12-13 for symbol A?

#### Clock 2: Source System Time (source_last_update_date)
**What it represents:** When FINRA last updated this row in their system  
**Example value:** 2025-12-22  
**Semantics:** "FINRA updated this row on 2025-12-22" (may be initial publication or a correction)

**Questions Clock 2 Answers:**
1. When did FINRA last update the data for week 2025-12-20, symbol A, MPID NITE?
2. Did FINRA publish corrections after the initial release? (compare source_last_update_date to typical publication pattern)
3. Which rows in week 2025-12-20 have source_last_update_date > 2025-12-23? (late corrections)
4. Show me all FINRA updates that occurred on 2025-12-22.
5. What is the typical lag between week_ending and source_last_update_date?

#### Clock 3: Platform Capture Time (captured_at)
**What it represents:** When we fetched/ingested the FINRA file into our system (UTC timestamp)  
**Example value:** 2025-12-23T09:00:00Z  
**Semantics:** "We captured this version of FINRA's data on 2025-12-23 at 09:00 UTC"

**Questions Clock 3 Answers:**
1. What did we know about week 2025-12-20 as-of our capture on 2025-12-23 09:00?
2. Show me all captures we've performed for week 2025-12-20 (initial + corrections).
3. What changed between our capture on 2025-12-23 and our capture on 2026-01-05?
4. When did we first ingest data for week 2025-12-20?
5. Which capture should a dashboard use for "latest view"? (MAX(captured_at))

### Temporal Dimension Relationships

**Business Time → Source System Time:**
- Typically: `source_last_update_date` is 2-3 business days after `week_ending`
- Example: Week ending 2025-12-20 (Friday) → FINRA publishes Monday 2025-12-23
- Corrections: `source_last_update_date` may be weeks later (e.g., 2026-01-05 for a correction)

**Source System Time → Platform Capture Time:**
- Our capture runs AFTER FINRA publishes
- Example: FINRA updates on 2025-12-23 → we capture on 2025-12-23 09:00
- Re-captures: We may capture again on 2026-01-05 (same source_last_update_date if no correction, or new source_last_update_date if FINRA corrected)

**Capture Identity:**
- `capture_id` = unique identifier for a fetch event
- Convention: `capture_id = batch_id` (reuse existing field)
- One capture = one file fetch = one set of (captured_at, capture_id)

### What Exists Today (Before Hardening)

**Current Schema (otc_raw):**
```sql
CREATE TABLE otc_raw (
    week_ending DATE NOT NULL,           -- Clock 1: Business time ✅
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    batch_id TEXT NOT NULL,              -- Execution identifier (not capture!)
    execution_id TEXT NOT NULL,
    -- Missing: Clock 2 (source_last_update_date) ❌
    -- Missing: Clock 3 (captured_at) ❌
    UNIQUE(week_ending, tier, symbol, mpid)  -- Cannot store multiple captures! ❌
);
```

**Problem:**
- We can capture FINRA's `lastUpdateDate` but don't store it (loses correction detection)
- We can't distinguish between "initial capture on 2025-12-23" vs "corrected capture on 2026-01-05"
- UNIQUE constraint prevents storing multiple versions of the same (week, symbol, mpid)
- No way to answer: "What did we know as-of 2025-12-23?"

---

## 2. Minimal Schema Changes (3-Clock Model)

### Design Decision: Storage Strategy

**Store all 3 clocks in `otc_raw` (source of truth):**
```sql
ALTER TABLE otc_raw ADD COLUMN source_last_update_date DATE;      -- Clock 2: From FINRA
ALTER TABLE otc_raw ADD COLUMN captured_at TIMESTAMP NOT NULL;    -- Clock 3: Our capture time
ALTER TABLE otc_raw ADD COLUMN capture_id TEXT NOT NULL;          -- Capture identifier
```

**Propagate `captured_at` and `capture_id` through pipeline:**
- Downstream tables inherit capture identity from raw
- `source_last_update_date` stays in raw only (not needed in aggregates)

**Rationale:**
- Clock 1 (week_ending): Already present everywhere ✅
- Clock 2 (source_last_update_date): Source-specific, only in raw
- Clock 3 (captured_at + capture_id): Propagated to all domain tables for PIT queries

### New Natural Keys (Allow Multiple Captures)

**Before (breaks with multiple captures):**
```sql
UNIQUE(week_ending, tier, symbol, mpid)  -- Only one version allowed ❌
```

**After (supports multiple captures):**
```sql
UNIQUE(week_ending, tier, symbol, mpid, capture_id)  -- Multiple captures OK ✅
```

**Idempotency:**
- Same `capture_id` re-run → ON CONFLICT DO NOTHING (no duplicates)
- Different `capture_id` → New row (capture history preserved)

### Migration 026: Add 3-Clock Support

**File:** `migrations/026_add_three_clock_model.sql`

```sql
-- ============================================================================
-- Migration 026: Add 3-Clock Temporal Model to OTC Domain
-- ============================================================================
-- Clock 1: week_ending (business time) - ALREADY EXISTS
-- Clock 2: source_last_update_date (FINRA update time) - NEW
-- Clock 3: captured_at (our capture time) - NEW
-- Capture Identity: capture_id - NEW
-- ============================================================================

-- ============================================================================
-- PART 1: Add new columns to otc_raw (source of truth)
-- ============================================================================
ALTER TABLE otc_raw ADD COLUMN source_last_update_date DATE;
ALTER TABLE otc_raw ADD COLUMN captured_at TIMESTAMP NOT NULL DEFAULT (datetime('now'));
ALTER TABLE otc_raw ADD COLUMN capture_id TEXT NOT NULL DEFAULT 'unknown';

-- ============================================================================
-- PART 2: Add capture identity to downstream domain tables
-- ============================================================================
ALTER TABLE otc_venue_volume ADD COLUMN captured_at TIMESTAMP NOT NULL DEFAULT (datetime('now'));
ALTER TABLE otc_venue_volume ADD COLUMN capture_id TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE otc_symbol_summary ADD COLUMN captured_at TIMESTAMP NOT NULL DEFAULT (datetime('now'));
ALTER TABLE otc_symbol_summary ADD COLUMN capture_id TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE otc_venue_share ADD COLUMN captured_at TIMESTAMP NOT NULL DEFAULT (datetime('now'));
ALTER TABLE otc_venue_share ADD COLUMN capture_id TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE otc_liquidity_score ADD COLUMN captured_at TIMESTAMP NOT NULL DEFAULT (datetime('now'));
ALTER TABLE otc_liquidity_score ADD COLUMN capture_id TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE otc_symbol_rolling_6w ADD COLUMN captured_at TIMESTAMP NOT NULL DEFAULT (datetime('now'));
ALTER TABLE otc_symbol_rolling_6w ADD COLUMN capture_id TEXT NOT NULL DEFAULT 'unknown';

-- ============================================================================
-- PART 3: Update natural keys to include capture_id (allow multiple captures)
-- ============================================================================

-- otc_raw: Allow multiple captures of same (week, symbol, mpid)
DROP INDEX IF EXISTS idx_otc_raw_natural_key;
CREATE UNIQUE INDEX idx_otc_raw_natural_key 
ON otc_raw(week_ending, tier, symbol, mpid, capture_id);

-- otc_venue_volume: Normalized data versioning
DROP INDEX IF EXISTS idx_otc_venue_volume_natural_key;
CREATE UNIQUE INDEX idx_otc_venue_volume_natural_key 
ON otc_venue_volume(week_ending, tier, symbol, mpid, capture_id);

-- otc_symbol_summary: Aggregate versioning
DROP INDEX IF EXISTS idx_otc_symbol_summary_natural_key;
CREATE UNIQUE INDEX idx_otc_symbol_summary_natural_key 
ON otc_symbol_summary(week_ending, tier, symbol, capture_id);

-- otc_venue_share: Market share versioning
CREATE UNIQUE INDEX idx_otc_venue_share_natural_key 
ON otc_venue_share(week_ending, tier, symbol, mpid, capture_id);

-- otc_liquidity_score: Liquidity versioning
CREATE UNIQUE INDEX idx_otc_liquidity_natural_key 
ON otc_liquidity_score(week_ending, tier, symbol, capture_id);

-- otc_symbol_rolling_6w: Rolling metrics versioning
DROP INDEX IF EXISTS idx_otc_rolling_natural_key;
CREATE UNIQUE INDEX idx_otc_rolling_natural_key 
ON otc_symbol_rolling_6w(week_ending, tier, symbol, capture_id);

-- ============================================================================
-- PART 4: Add indexes for point-in-time queries (performance)
-- ============================================================================

-- Query: "Latest capture for week X"
CREATE INDEX idx_otc_raw_pit_latest 
ON otc_raw(week_ending, tier, captured_at DESC);

CREATE INDEX idx_otc_symbol_summary_pit_latest 
ON otc_symbol_summary(week_ending, tier, captured_at DESC);

-- Query: "All captures for week X, ordered by time"
CREATE INDEX idx_otc_raw_captures 
ON otc_raw(week_ending, tier, capture_id, captured_at);

-- Query: "What changed in FINRA source data?" (Clock 2 queries)
CREATE INDEX idx_otc_raw_source_updates 
ON otc_raw(week_ending, source_last_update_date);

-- ============================================================================
-- PART 5: Create convenience view for "latest only" queries
-- ============================================================================

CREATE VIEW otc_symbol_summary_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM otc_symbol_summary
) WHERE rn = 1;

-- ============================================================================
-- Migration complete. Schema now supports:
-- - Multiple captures of same week (capture_id in natural keys)
-- - Source system time tracking (source_last_update_date from FINRA)
-- - Platform capture time tracking (captured_at + capture_id)
-- - Point-in-time queries (as-of captured_at <= X)
-- - Correction detection (compare source_last_update_date across captures)
-- ============================================================================
```

---

## 3. Pipeline Behavior Changes

### IngestWeekPipeline: Set All 3 Clocks

**File:** `src/market_spine/domains/otc/pipelines.py`

**Before:**
```python
class IngestWeekPipeline(BasePipeline):
    def run(self) -> dict[str, Any]:
        # ... load fixture ...
        conn.execute("""
            INSERT INTO otc_raw (
                week_ending, tier, symbol, mpid,
                total_shares, total_trades,
                batch_id, execution_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
        """, (week_ending, tier, symbol, mpid, shares, trades, batch_id, exec_id))
```

**After:**
```python
from datetime import datetime, timezone

class IngestWeekPipeline(BasePipeline):
    def run(self) -> dict[str, Any]:
        week_ending = self.params["week_ending"]
        tier = self.params["tier"]
        
        # NEW: Capture identity (reuse batch_id as capture_id)
        capture_id = self.context.get("batch_id")
        captured_at = datetime.now(timezone.utc)  # Clock 3
        
        # Load fixture (real FINRA CSV format)
        fixture_path = self._resolve_fixture_path(week_ending, tier)
        raw_records = self._parse_finra_csv(fixture_path)
        
        conn = self.context.get("db_connection")
        ingested_count = 0
        
        for record in raw_records:
            # Extract FINRA lastUpdateDate (Clock 2)
            source_last_update_date = record.get("lastUpdateDate")  # From FINRA CSV
            
            result = conn.execute("""
                INSERT INTO otc_raw (
                    week_ending, tier, symbol, mpid,
                    total_shares, total_trades,
                    source_last_update_date,  -- NEW: Clock 2
                    captured_at,              -- NEW: Clock 3
                    capture_id,               -- NEW: Capture identity
                    batch_id, execution_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (week_ending, tier, symbol, mpid, capture_id) 
                DO NOTHING
            """, (
                week_ending, tier, record["symbol"], record["mpid"],
                record["total_shares"], record["total_trades"],
                source_last_update_date,  # NEW
                captured_at,              # NEW
                capture_id,               # NEW
                self.context.get("batch_id"),
                self.context.get("execution_id")
            ))
            
            if result.rowcount > 0:
                ingested_count += 1
        
        conn.commit()
        
        return {
            "ingested_count": ingested_count,
            "capture_id": capture_id,              # NEW: Return for tracking
            "captured_at": captured_at.isoformat() # NEW: Return for tracking
        }
```

**Key Changes:**
1. Set `captured_at = datetime.now(timezone.utc)` (Clock 3) at ingest time
2. Set `capture_id = batch_id` (reuse existing identifier)
3. Extract `source_last_update_date` from FINRA CSV `lastUpdateDate` column (Clock 2)
4. Update INSERT to include new columns
5. Update ON CONFLICT to include `capture_id` (allows multiple captures)

### NormalizeWeekPipeline: Propagate Capture Identity

**Before:**
```python
class NormalizeWeekPipeline(BasePipeline):
    def run(self) -> dict[str, Any]:
        # Delete existing normalized data
        conn.execute("""
            DELETE FROM otc_venue_volume 
            WHERE week_ending = ? AND tier = ?
        """, (week_ending, tier))
        
        # Fetch raw data
        raw_records = conn.execute("""
            SELECT * FROM otc_raw 
            WHERE week_ending = ? AND tier = ?
        """, (week_ending, tier)).fetchall()
```

**After:**
```python
class NormalizeWeekPipeline(BasePipeline):
    def run(self) -> dict[str, Any]:
        week_ending = self.params["week_ending"]
        tier = self.params["tier"]
        
        # NEW: Determine which capture to normalize (default = latest)
        target_capture_id = self.params.get("capture_id")  # Optional: explicit capture
        
        if target_capture_id is None:
            # Use latest capture for this week
            result = conn.execute("""
                SELECT capture_id, captured_at 
                FROM otc_raw 
                WHERE week_ending = ? AND tier = ?
                ORDER BY captured_at DESC 
                LIMIT 1
            """, (week_ending, tier)).fetchone()
            
            if not result:
                raise ValueError(f"No raw data found for week {week_ending}")
            
            target_capture_id, captured_at = result
        else:
            # Use specified capture
            result = conn.execute("""
                SELECT captured_at FROM otc_raw 
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
                LIMIT 1
            """, (week_ending, tier, target_capture_id)).fetchone()
            
            captured_at = result[0] if result else None
        
        # Idempotency: Delete existing normalized data for THIS capture only
        conn.execute("""
            DELETE FROM otc_venue_volume 
            WHERE week_ending = ? AND tier = ? AND capture_id = ?
        """, (week_ending, tier, target_capture_id))
        
        # Fetch raw data for this specific capture
        raw_records = conn.execute("""
            SELECT * FROM otc_raw 
            WHERE week_ending = ? AND tier = ? AND capture_id = ?
        """, (week_ending, tier, target_capture_id)).fetchall()
        
        # ... normalization logic ...
        
        for venue_volume in normalized_data:
            conn.execute("""
                INSERT INTO otc_venue_volume (
                    week_ending, tier, symbol, mpid, 
                    total_shares, total_trades,
                    captured_at, capture_id,  -- NEW: Propagate
                    batch_id, execution_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                week_ending, tier, venue_volume["symbol"], venue_volume["mpid"],
                venue_volume["total_shares"], venue_volume["total_trades"],
                captured_at, target_capture_id,  # NEW: Propagate from raw
                self.context.get("batch_id"),
                self.context.get("execution_id")
            ))
```

**Key Changes:**
1. Determine target `capture_id` (default = latest, or explicit from params)
2. Delete only for specific `capture_id` (idempotency within capture)
3. Fetch raw data for specific `capture_id`
4. Propagate `captured_at` and `capture_id` to normalized table

### AggregateWeekPipeline: Propagate Capture Identity

**Changes (similar pattern):**
```python
# Determine capture from normalized data
target_capture_id = params.get("capture_id") or get_latest_capture(week_ending, tier)

# Delete existing aggregates for this capture
DELETE FROM otc_symbol_summary 
WHERE week_ending = ? AND tier = ? AND capture_id = ?

# Aggregate from normalized data with same capture_id
SELECT ... FROM otc_venue_volume 
WHERE week_ending = ? AND tier = ? AND capture_id = ?

# Insert aggregates with propagated captured_at and capture_id
INSERT INTO otc_symbol_summary (..., captured_at, capture_id)
VALUES (..., ?, ?)
```

### ComputeRollingPipeline: Use Latest Per Week

**Rolling Semantics Decision:**
```
Rolling metrics are computed using the LATEST capture for each historical week.
```

**Rationale:**
- A 6-week rolling average should use the best available data for each of those 6 weeks
- "Best available" = latest capture (corrections applied)
- This is NOT "as-of a specific capture" (that's a non-goal for Basic)

**Implementation:**
```python
class ComputeRollingPipeline(BasePipeline):
    def run(self) -> dict[str, Any]:
        week_ending = self.params["week_ending"]
        tier = self.params["tier"]
        weeks_back = self.params.get("weeks_back", 6)
        
        # NEW: Get latest capture for current week (determines output capture_id)
        current_capture = conn.execute("""
            SELECT capture_id, captured_at 
            FROM otc_symbol_summary 
            WHERE week_ending = ? AND tier = ?
            ORDER BY captured_at DESC 
            LIMIT 1
        """, (week_ending, tier)).fetchone()
        
        output_capture_id, output_captured_at = current_capture
        
        # Fetch historical summaries (LATEST per week)
        historical_summaries = conn.execute("""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY week_ending, tier, symbol 
                    ORDER BY captured_at DESC
                ) as rn
                FROM otc_symbol_summary
                WHERE tier = ? 
                AND week_ending >= date(?, ?)
            ) WHERE rn = 1
        """, (tier, week_ending, f'-{weeks_back} weeks')).fetchall()
        
        # ... rolling calculation ...
        
        # Insert with current week's capture identity
        conn.execute("""
            INSERT INTO otc_symbol_rolling_6w (
                week_ending, tier, symbol, 
                avg_volume, avg_trades,
                captured_at, capture_id,  -- NEW: From current week
                batch_id, execution_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (..., output_captured_at, output_capture_id, ...))
```

**Key Decision:**
- Rolling output inherits `capture_id` from the CURRENT week (not a mix)
- Input uses latest capture per historical week
- This is "rolling as-of latest available data" (not "rolling as-of specific capture")

---

## 4. Point-In-Time Query Patterns (SQLite)

---

## 4. Point-In-Time Query Patterns (SQLite)

### Pattern A: Latest View for (week_ending, symbol, mpid)

**Use Case:** Dashboard showing current data (corrections applied)

```sql
-- Latest capture for week 2025-12-20
SELECT 
    symbol,
    mpid,
    total_shares,
    total_trades,
    captured_at,
    capture_id,
    source_last_update_date  -- When FINRA last updated this row
FROM otc_raw
WHERE week_ending = '2025-12-20' 
  AND tier = 'NMS Tier 1'
  AND capture_id = (
      SELECT capture_id 
      FROM otc_raw 
      WHERE week_ending = '2025-12-20' AND tier = 'NMS Tier 1'
      ORDER BY captured_at DESC 
      LIMIT 1
  )
ORDER BY symbol, mpid;
```

**Or using the convenience view:**
```sql
-- Simplified query for analysts
SELECT * FROM otc_symbol_summary_latest
WHERE week_ending = '2025-12-20' AND tier = 'NMS Tier 1'
ORDER BY symbol;
```

### Pattern B: As-Of captured_at <= X View

**Use Case:** "What did we know on 2025-12-23 at 09:00?" (audit/compliance)

```sql
-- As-of 2025-12-23 09:00:00
SELECT 
    week_ending,
    symbol,
    total_volume,
    total_trades,
    venue_count,
    captured_at,
    capture_id
FROM otc_symbol_summary
WHERE tier = 'NMS Tier 1'
  AND captured_at <= '2025-12-23 09:00:00'
  AND (week_ending, tier, symbol, captured_at) IN (
      -- Latest capture per week as-of that timestamp
      SELECT week_ending, tier, symbol, MAX(captured_at)
      FROM otc_symbol_summary
      WHERE tier = 'NMS Tier 1'
        AND captured_at <= '2025-12-23 09:00:00'
      GROUP BY week_ending, tier, symbol
  )
ORDER BY week_ending DESC, symbol;
```

**Simpler (using window function):**
```sql
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM otc_symbol_summary
    WHERE tier = 'NMS Tier 1'
      AND captured_at <= '2025-12-23 09:00:00'
) WHERE rn = 1
ORDER BY week_ending DESC, symbol;
```

### Pattern C: List All Captures for week_ending = X

**Use Case:** "Show me the capture history for week 2025-12-20"

```sql
-- All captures for week 2025-12-20 with FINRA source update time
SELECT 
    capture_id,
    captured_at,
    COUNT(*) as row_count,
    COUNT(DISTINCT symbol) as symbol_count,
    COUNT(DISTINCT mpid) as venue_count,
    MAX(source_last_update_date) as max_finra_update,  -- Latest FINRA update in this capture
    MIN(source_last_update_date) as min_finra_update   -- Earliest FINRA update in this capture
FROM otc_raw
WHERE week_ending = '2025-12-20' 
  AND tier = 'NMS Tier 1'
GROUP BY capture_id, captured_at
ORDER BY captured_at;
```

**Example Output:**
```
capture_id                              | captured_at         | row_count | max_finra_update | min_finra_update
backfill_NMS_TIER_1_20251223_090000     | 2025-12-23 09:00:00 | 150       | 2025-12-22       | 2025-12-22
backfill_NMS_TIER_1_20260105_143000     | 2026-01-05 14:30:00 | 150       | 2026-01-04       | 2025-12-22
```

**Interpretation:**
- First capture: All FINRA rows had `lastUpdateDate = 2025-12-22` (initial publication)
- Second capture: Some rows updated to `2026-01-04` (FINRA published corrections)

### Pattern D: Diff Two Captures for Same Week

**Use Case:** "What changed between initial capture and correction?"

```sql
-- Compare initial vs corrected capture for week 2025-12-20
WITH 
capture1 AS (
    SELECT * FROM otc_raw
    WHERE week_ending = '2025-12-20' 
      AND tier = 'NMS Tier 1'
      AND capture_id = 'backfill_NMS_TIER_1_20251223_090000'
),
capture2 AS (
    SELECT * FROM otc_raw
    WHERE week_ending = '2025-12-20' 
      AND tier = 'NMS Tier 1'
      AND capture_id = 'backfill_NMS_TIER_1_20260105_143000'
),
-- Rows only in capture2 (new venues added)
added AS (
    SELECT 'ADDED' as change_type, c2.*
    FROM capture2 c2
    LEFT JOIN capture1 c1 USING (symbol, mpid)
    WHERE c1.symbol IS NULL
),
-- Rows only in capture1 (venues removed - should be rare)
removed AS (
    SELECT 'REMOVED' as change_type, c1.*
    FROM capture1 c1
    LEFT JOIN capture2 c2 USING (symbol, mpid)
    WHERE c2.symbol IS NULL
),
-- Rows in both but values changed
changed AS (
    SELECT 
        'CHANGED' as change_type,
        c1.symbol,
        c1.mpid,
        c1.total_shares as shares_before,
        c2.total_shares as shares_after,
        c2.total_shares - c1.total_shares as shares_delta,
        c1.total_trades as trades_before,
        c2.total_trades as trades_after,
        c2.total_trades - c1.total_trades as trades_delta,
        c1.source_last_update_date as finra_date_before,
        c2.source_last_update_date as finra_date_after
    FROM capture1 c1
    JOIN capture2 c2 USING (symbol, mpid)
    WHERE c1.total_shares != c2.total_shares 
       OR c1.total_trades != c2.total_trades
       OR c1.source_last_update_date != c2.source_last_update_date
)
SELECT * FROM added
UNION ALL
SELECT * FROM removed
UNION ALL
SELECT * FROM changed
ORDER BY change_type, symbol, mpid;
```

**Example Output:**
```
change_type | symbol | mpid | shares_before | shares_after | shares_delta | finra_date_before | finra_date_after
CHANGED     | A      | NITE | 76630         | 76850        | +220         | 2025-12-22        | 2026-01-04
CHANGED     | AA     | ARCA | 65210         | 65100        | -110         | 2025-12-22        | 2026-01-04
```

**Interpretation:**
- FINRA published corrections on 2026-01-04 (`finra_date_after`)
- Symbol A, MPID NITE: volume increased by 220 shares
- Symbol AA, MPID ARCA: volume decreased by 110 shares (correction)

---

## 5. Rolling Metrics Semantics (Clear Decision)

### Chosen Semantics: "Latest Per Week"

**Definition:**
Rolling metrics (e.g., 6-week average) are computed using the **latest available capture** for each historical week in the window.

**Example: 6-week rolling average as of week 2026-01-02**

**Input Weeks:**
- 2025-11-22 (6 weeks back) → Use latest capture (might be from 2026-01-05 if corrected)
- 2025-11-29 (5 weeks back) → Use latest capture
- 2025-12-06 (4 weeks back) → Use latest capture
- 2025-12-13 (3 weeks back) → Use latest capture
- 2025-12-20 (2 weeks back) → Use latest capture
- 2025-12-27 (1 week back) → Use latest capture

**Output:**
- `otc_symbol_rolling_6w.week_ending = 2026-01-02`
- `otc_symbol_rolling_6w.capture_id = <capture_id of week 2026-01-02>`
- `otc_symbol_rolling_6w.captured_at = <captured_at of week 2026-01-02>`

**Rationale:**
- Analysts expect rolling metrics to reflect "best available data" (corrections applied)
- Historical corrections automatically update rolling metrics on next backfill
- Simple to implement (window function to get latest per week)

**SQL Implementation:**
```sql
-- Get latest capture per historical week for rolling window
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM otc_symbol_summary
    WHERE tier = 'NMS Tier 1'
      AND week_ending >= date('2026-01-02', '-6 weeks')
      AND week_ending <= '2026-01-02'
) WHERE rn = 1;
```

### Non-Goal: "Rolling As-Of Specific Capture"

**NOT implementing in Basic:**
"Show me the 6-week rolling average as-of capture X, using only data available at that capture time"

**Why not:**
- Requires complex time-travel queries across multiple weeks
- Adds significant complexity for minimal benefit in Basic tier
- Analysts can reconstruct this manually if needed using as-of queries

**Intermediate might add:**
- Capture-scoped rolling metrics (compute rolling using only data from a specific batch/capture)
- Requires storing capture lineage and more complex query patterns

---

## 6. Verification Checklist

### Pre-Migration Verification

```bash
# 1. Backup database
cp spine.db spine.db.backup_pre_026

# 2. Run current tests
pytest tests/ -v

# 3. Verify current 3-week backfill still works
spine db reset --yes
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=3

# 4. Check current row counts (baseline)
sqlite3 spine.db "SELECT COUNT(*) FROM otc_raw;"
sqlite3 spine.db "SELECT COUNT(*) FROM otc_symbol_summary;"
```

### Post-Migration Verification

#### Step 1: Schema Verification
```sql
-- Check new columns exist
PRAGMA table_info(otc_raw);
-- Should show: source_last_update_date, captured_at, capture_id

PRAGMA table_info(otc_symbol_summary);
-- Should show: captured_at, capture_id

-- Check unique indexes updated
SELECT sql FROM sqlite_master 
WHERE type='index' AND name LIKE 'idx_otc%natural_key';
-- Should include capture_id in all natural keys

-- Check convenience view created
SELECT sql FROM sqlite_master 
WHERE type='view' AND name = 'otc_symbol_summary_latest';
```

#### Step 2: Fresh Backfill (Single Capture)
```bash
# Reset and run 3-week backfill
spine db reset --yes
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=3

# Verify single capture created
sqlite3 spine.db "SELECT DISTINCT capture_id, captured_at FROM otc_raw ORDER BY captured_at;"
# Should show 1 capture_id, 1 captured_at

# Verify source_last_update_date populated
sqlite3 spine.db "SELECT DISTINCT source_last_update_date FROM otc_raw ORDER BY source_last_update_date;"
# Should show dates from FINRA CSV (e.g., 2025-12-22)

# Verify row counts
sqlite3 spine.db "SELECT COUNT(*) FROM otc_raw;"        # 150 (50 per week × 3)
sqlite3 spine.db "SELECT COUNT(*) FROM otc_symbol_summary;"  # 6 (2 symbols × 3 weeks)
```

#### Step 3: Idempotent Rerun (Same Capture)
```bash
# Re-run same backfill immediately (same capture_id should be reused if batch_id same)
# Actually, batch_id will be different, so NEW capture created
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=3

# Check capture count
sqlite3 spine.db "SELECT COUNT(DISTINCT capture_id) FROM otc_raw;"
# Should show 2 captures now (batch_id differs each run)

# Check total row count doubled
sqlite3 spine.db "SELECT COUNT(*) FROM otc_raw;"  # 300 (150 × 2 captures)
sqlite3 spine.db "SELECT COUNT(*) FROM otc_symbol_summary;"  # 12 (6 × 2 captures)

# Verify latest view still shows correct count
sqlite3 spine.db "SELECT COUNT(*) FROM otc_symbol_summary_latest;"  # 6 (latest only)
```

**IMPORTANT:** If we want true idempotency (same capture_id on rerun), we need deterministic `capture_id` generation:
```python
# Option 1: Deterministic capture_id based on input params
capture_id = f"backfill_{tier}_{week_ending}"  # Same params = same capture_id

# Option 2: Check manifest and reuse if already completed
# (More complex, probably overkill for Basic)
```

**For Basic, we accept:** Each run creates new capture (captures are cheap, storage is cheap in Basic).

#### Step 4: Correction Scenario (New Capture with Updated FINRA Data)

```bash
# Simulate FINRA correction:
# 1. Manually edit data/fixtures/otc/week_2025-12-20.psv
# 2. Change total_shares for one row (e.g., A|NITE: 76630 → 76850)
# 3. Update source_last_update_date in fixture (simulate FINRA correction)

# Re-ingest corrected week
spine run otc.ingest_week -p week_ending=2025-12-20 -p tier=NMS_TIER_1

# Verify new capture created
sqlite3 spine.db "
SELECT capture_id, captured_at, COUNT(*) as rows 
FROM otc_raw 
WHERE week_ending = '2025-12-20' 
GROUP BY capture_id, captured_at 
ORDER BY captured_at;
"
# Should show 2 captures for week 2025-12-20

# Run diff query (Pattern D above)
sqlite3 spine.db "
SELECT symbol, mpid, 
       c1.total_shares as before, 
       c2.total_shares as after,
       c2.total_shares - c1.total_shares as delta
FROM (SELECT * FROM otc_raw WHERE week_ending = '2025-12-20' AND capture_id = '<first_capture>') c1
JOIN (SELECT * FROM otc_raw WHERE week_ending = '2025-12-20' AND capture_id = '<second_capture>') c2
USING (symbol, mpid)
WHERE c1.total_shares != c2.total_shares;
"
# Should show A|NITE: before=76630, after=76850, delta=220
```

#### Step 5: Point-In-Time Query Verification

```sql
-- Latest view
SELECT * FROM otc_symbol_summary_latest 
WHERE week_ending = '2025-12-20';
-- Should show corrected data (latest capture)

-- As-of first capture
SELECT * FROM otc_symbol_summary
WHERE week_ending = '2025-12-20' 
  AND capture_id = '<first_capture_id>';
-- Should show original data

-- All captures for week
SELECT capture_id, captured_at, symbol, total_volume 
FROM otc_symbol_summary
WHERE week_ending = '2025-12-20'
ORDER BY symbol, captured_at;
-- Should show 2 versions per symbol
```

#### Step 6: Add-Calc Still Domain-Only

```bash
# Verify adding new calculation touches only domain files
# Example: Add trade concentration metric

# Files expected to change:
# - src/market_spine/domains/otc/calculations.py (new function)
# - src/market_spine/domains/otc/pipelines.py (call new function)  
# - src/market_spine/domains/otc/schema.py (new table name)
# - migrations/027_otc_trade_concentration.sql (includes captured_at, capture_id)

# Files NOT changed:
# - src/market_spine/dispatcher.py
# - src/market_spine/runner.py
# - src/market_spine/registry.py
# - src/market_spine/db.py (unless adding platform-level feature)
```

### Success Criteria

✅ **Schema updated correctly:**
- All domain tables have `captured_at` and `capture_id`
- `otc_raw` has `source_last_update_date`
- Natural keys include `capture_id`

✅ **Backfill works:**
- 3-week backfill completes successfully
- `captured_at` and `capture_id` populated
- `source_last_update_date` extracted from FINRA CSV

✅ **Multiple captures coexist:**
- Re-running backfill creates new capture
- Old captures preserved
- No natural key conflicts

✅ **Point-in-time queries work:**
- Latest view returns correct data
- As-of queries return historical snapshots
- Capture history queryable
- Diff queries show corrections

✅ **Rolling metrics correct:**
- Uses latest capture per historical week
- Output inherits capture_id from current week

✅ **Add-calc promise holds:**
- New calculations touch only domain files + migration
- New tables include `captured_at` and `capture_id` by convention

---

## 7. Code Changes Summary (File-by-File)

### migrations/026_add_three_clock_model.sql
**Status:** NEW FILE  
**Lines:** ~80 LOC  
**Purpose:** Add 3-clock model columns and indexes  

**Key Changes:**
- Add `source_last_update_date`, `captured_at`, `capture_id` to all domain tables
- Update natural keys to include `capture_id`
- Add PIT query indexes
- Create `otc_symbol_summary_latest` view

### src/market_spine/domains/otc/pipelines.py
**Status:** MODIFIED  
**Lines:** ~100 LOC changed (across 4 pipeline classes)  

**IngestWeekPipeline:**
- Set `captured_at = datetime.now(timezone.utc)`
- Set `capture_id = batch_id`
- Extract `source_last_update_date` from FINRA CSV `lastUpdateDate` column
- Update INSERT to include new columns
- Update ON CONFLICT to include `capture_id`

**NormalizeWeekPipeline:**
- Determine target `capture_id` (default latest, or from params)
- Delete only for specific `capture_id`
- Fetch raw data for specific `capture_id`
- Propagate `captured_at` and `capture_id` to normalized table

**AggregateWeekPipeline:**
- Determine target `capture_id` from normalized data
- Delete only for specific `capture_id`
- Propagate `captured_at` and `capture_id` to aggregates

**ComputeRollingPipeline:**
- Use latest capture per historical week (window function)
- Output inherits `capture_id` from current week

### src/market_spine/domains/otc/io.py
**Status:** MODIFIED (if needed)  
**Lines:** ~20 LOC  

**Changes:**
- Update `parse_simple_psv()` or create `parse_finra_csv()` to extract `lastUpdateDate` column
- Map FINRA CSV columns to our schema

**Example:**
```python
def parse_finra_csv(filepath: str) -> list[dict[str, Any]]:
    """Parse FINRA OTC Weekly CSV format."""
    records = []
    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            records.append({
                'tier': parts[0],  # tierDescription
                'symbol': parts[1],  # issueSymbolIdentifier
                'mpid': parts[4],  # MPID
                'total_shares': int(parts[5]),  # totalWeeklyShareQuantity
                'total_trades': int(parts[6]),  # totalWeeklyTradeCount
                'lastUpdateDate': parts[7]  # lastUpdateDate (YYYY-MM-DD)
            })
    return records
```

### src/market_spine/db.py
**Status:** NO CHANGES  
**Reason:** Platform code unchanged (only domain schema changed)

### src/market_spine/dispatcher.py
**Status:** NO CHANGES  
**Reason:** Capture identity handled at pipeline level

### src/market_spine/runner.py
**Status:** NO CHANGES  
**Reason:** Execution semantics unchanged

### tests/domains/otc/test_pipelines.py
**Status:** MODIFIED  
**Lines:** ~50 LOC updated  

**Changes:**
- Update test fixtures to include `lastUpdateDate` column
- Update assertions to check `captured_at`, `capture_id`, `source_last_update_date`
- Add test for multiple captures (idempotency)
- Add test for PIT queries

**Example:**
```python
def test_ingest_week_sets_three_clocks(db_connection):
    pipeline = IngestWeekPipeline(
        params={"week_ending": "2025-12-20", "tier": "NMS_TIER_1"},
        context={"db_connection": db_connection, "batch_id": "test_batch"}
    )
    
    result = pipeline.run()
    
    # Check captured_at set
    rows = db_connection.execute("""
        SELECT DISTINCT captured_at, capture_id, source_last_update_date 
        FROM otc_raw
    """).fetchall()
    
    assert len(rows) == 1
    assert rows[0][0] is not None  # captured_at
    assert rows[0][1] == "test_batch"  # capture_id
    assert rows[0][2] == "2025-12-22"  # source_last_update_date from fixture
```

---

## 8. Explicit Non-Goals (Unchanged from Original)

❌ **Full Bitemporal Event Sourcing**  
❌ **Async Execution / Message Queues**  
❌ **API Layer / Web Service**  
❌ **Streaming Ingestion**  
❌ **User-Facing Time Travel UI**  
❌ **Automated Capture Cleanup / Retention Policies**  
❌ **Cross-Domain Capture Coordination**  
❌ **Versioned Schema Migrations**

---

## 9. Ready for Intermediate? Gate Criteria

### Checklist (Must Pass All)

- [ ] **Schema Migration 026 applied successfully**
- [ ] **All domain tables have captured_at and capture_id columns**
- [ ] **otc_raw has source_last_update_date column**
- [ ] **Natural keys updated to include capture_id**
- [ ] **3-week backfill runs successfully**
- [ ] **Multiple captures can coexist (no natural key conflicts)**
- [ ] **PIT Query Pattern A (latest view) works**
- [ ] **PIT Query Pattern B (as-of timestamp) works**
- [ ] **PIT Query Pattern C (all captures listing) works**
- [ ] **PIT Query Pattern D (diff two captures) works**
- [ ] **Rolling metrics use latest-per-week semantics correctly**
- [ ] **Test suite passes (all existing + new PIT tests)**
- [ ] **Add-calc still touches only domain files + migration**

### Readiness Statement

**Market Spine Basic is production-ready when:**
1. All checklist items above are ✅
2. A domain expert can explain the 3-clock model without reading code
3. An analyst can write PIT queries using the 4 documented patterns
4. Correction workflow (re-ingest → normalize → aggregate) is tested end-to-end

**Intermediate can then add:**
- Async dispatcher with queue-based execution
- REST API exposing PIT query patterns
- Basic web UI for capture browsing
- Capture cleanup policies
- Multi-domain capture coordination

---

## 10. Summary

### What We Built: 3-Clock Temporal Model

**Clock 1: Business Time (week_ending)**
- When the trading activity occurred
- Always present, never changes

**Clock 2: Source System Time (source_last_update_date)**
- When FINRA last updated this row
- Detects corrections (later dates = corrections)
- Stored in `otc_raw` only

**Clock 3: Platform Capture Time (captured_at + capture_id)**
- When we fetched/ingested FINRA data
- Enables point-in-time queries ("what did we know as-of X?")
- Propagated through all domain tables

### Minimal Changes

**Schema:** ~80 LOC (migration SQL)  
**Code:** ~120 LOC (pipelines + IO)  
**Tests:** ~50 LOC (new PIT tests)  
**Total:** ~250 LOC

**Platform changes:** 0 LOC (all changes in OTC domain)

### Benefits

✅ **Corrections supported:** Multiple captures coexist  
✅ **Audit trail:** Full capture history preserved  
✅ **Point-in-time queries:** 4 concrete SQL patterns  
✅ **FINRA source tracking:** `source_last_update_date` enables correction detection  
✅ **Rolling metrics clear:** Uses latest-per-week semantics  
✅ **Forward-compatible:** Intermediate builds on this foundation  

### Risks Mitigated

⚠️ **Database growth:** Managed manually in Basic (each capture adds rows)  
⚠️ **Query complexity:** Mitigated by `otc_symbol_summary_latest` view  
⚠️ **Capture ID management:** Reuse `batch_id` (simple, no new ID generation)  

---

**This is the FINAL Basic hardening.** No further schema changes before Intermediate.

**Next Step:** Apply migration 026, update pipelines, run verification checklist.
