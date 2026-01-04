# 01: Schema Migration

> **Purpose**: Define all SQLite schema changes for the multi-week OTC workflow. This single migration file creates all required tables and indexes.

---

## Design Choices

### Why One Migration File?
- Basic tier uses sequential migrations numbered `001_`, `002_`, etc.
- This is `021_otc_multiweek_real_example.sql` (after existing migrations)
- Single file = atomic upgrade, easier rollback testing

### SQLite Limitations Handled
1. **No `ALTER TABLE DROP COLUMN`** → We use new tables, not modify existing columns
2. **No `ALTER TABLE ADD CONSTRAINT`** → We use `CREATE UNIQUE INDEX` instead
3. **No concurrent DDL** → Fine for Basic tier (single process)

### Idempotency
- All `CREATE TABLE` uses `IF NOT EXISTS`
- All `CREATE INDEX` uses `IF NOT EXISTS`
- Safe to run multiple times

---

## Migration File: `021_otc_multiweek_real_example.sql`

```sql
-- ============================================================================
-- Migration: 021_otc_multiweek_real_example.sql
-- Purpose: Add multi-week workflow support for OTC domain
-- Basic Tier: Synchronous, SQLite, single-process
-- ============================================================================

-- ============================================================================
-- TABLE: otc_week_manifest
-- Purpose: Track ingestion/processing status for each (week_ending, tier)
-- Updated by: ingest_week, normalize_week, aggregate_week, compute_rolling, snapshot
-- ============================================================================
CREATE TABLE IF NOT EXISTS otc_week_manifest (
    -- Natural key
    week_ending TEXT NOT NULL,              -- ISO Friday date (e.g., "2025-12-26")
    tier TEXT NOT NULL,                     -- NMS_TIER_1 | NMS_TIER_2 | OTC
    
    -- Source metadata (populated by ingest_week)
    source_type TEXT,                       -- "file" | "url"
    source_locator TEXT,                    -- File path or URL
    source_sha256 TEXT,                     -- SHA256 of source file
    source_bytes INTEGER,                   -- Size of source file
    
    -- Row counts (accumulated across stages)
    row_count_raw INTEGER DEFAULT 0,        -- Lines in source file
    row_count_parsed INTEGER DEFAULT 0,     -- Successfully parsed records
    row_count_inserted INTEGER DEFAULT 0,   -- Inserted into otc_raw
    row_count_normalized INTEGER DEFAULT 0, -- Inserted into otc_venue_volume
    row_count_rejected INTEGER DEFAULT 0,   -- Written to otc_rejects
    
    -- Stage tracking (updated as pipeline completes)
    stage TEXT DEFAULT 'PENDING',           -- PENDING|INGESTED|NORMALIZED|AGGREGATED|ROLLING|SNAPSHOT
    
    -- Lineage
    execution_id TEXT,                      -- Last execution that updated this
    batch_id TEXT,                          -- Batch this belongs to
    
    -- Timestamps
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    
    -- Constraints
    PRIMARY KEY (week_ending, tier)
);

CREATE INDEX IF NOT EXISTS idx_manifest_stage ON otc_week_manifest(stage);
CREATE INDEX IF NOT EXISTS idx_manifest_batch ON otc_week_manifest(batch_id);


-- ============================================================================
-- TABLE: otc_raw (modify existing - add lineage columns)
-- Note: If table exists without these columns, we add them
-- ============================================================================
-- Add columns if they don't exist (SQLite-safe pattern)
-- We check via pragma, but simpler: just add with ALTER and ignore error
-- In practice, wrap in try/except in Python migration runner

-- These ALTER statements may fail if columns exist - that's OK
-- The migration runner should handle "duplicate column name" gracefully
ALTER TABLE otc_raw ADD COLUMN execution_id TEXT;
ALTER TABLE otc_raw ADD COLUMN batch_id TEXT;
ALTER TABLE otc_raw ADD COLUMN record_hash TEXT;
ALTER TABLE otc_raw ADD COLUMN ingested_at TEXT DEFAULT (datetime('now'));

CREATE INDEX IF NOT EXISTS idx_otc_raw_execution ON otc_raw(execution_id);
CREATE INDEX IF NOT EXISTS idx_otc_raw_batch ON otc_raw(batch_id);
CREATE INDEX IF NOT EXISTS idx_otc_raw_hash ON otc_raw(record_hash);
CREATE INDEX IF NOT EXISTS idx_otc_raw_week_tier ON otc_raw(week_ending, tier);


-- ============================================================================
-- TABLE: otc_normalization_map
-- Purpose: Track raw → normalized mapping with accept/reject status
-- Written by: normalize_week
-- ============================================================================
CREATE TABLE IF NOT EXISTS otc_normalization_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Link to raw record
    raw_record_hash TEXT NOT NULL,          -- Hash of source record
    
    -- Normalized natural key (if accepted)
    week_ending TEXT,
    tier TEXT,
    symbol TEXT,
    mpid TEXT,
    
    -- Status
    status TEXT NOT NULL,                   -- ACCEPTED | REJECTED
    reject_reason TEXT,                     -- Null if accepted, reason code if rejected
    reject_detail TEXT,                     -- Human-readable detail
    
    -- Lineage
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    
    -- Index for lookups
    UNIQUE(raw_record_hash, execution_id)
);

CREATE INDEX IF NOT EXISTS idx_normmap_status ON otc_normalization_map(status);
CREATE INDEX IF NOT EXISTS idx_normmap_week ON otc_normalization_map(week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_normmap_rejected ON otc_normalization_map(status, reject_reason) 
    WHERE status = 'REJECTED';


-- ============================================================================
-- TABLE: otc_rejects
-- Purpose: Store rejected records with reason codes for audit/debugging
-- Written by: ingest_week, normalize_week
-- ============================================================================
CREATE TABLE IF NOT EXISTS otc_rejects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Source identification
    week_ending TEXT,                       -- May be null if unparseable
    tier TEXT,
    source_locator TEXT,                    -- File path or URL
    line_number INTEGER,                    -- Line in source file (1-based)
    
    -- Original data
    raw_line TEXT,                          -- Original line from file
    raw_record_hash TEXT,                   -- Hash if parseable
    
    -- Rejection details
    stage TEXT NOT NULL,                    -- INGEST | NORMALIZE | AGGREGATE
    reason_code TEXT NOT NULL,              -- Machine-readable code
    reason_detail TEXT,                     -- Human-readable explanation
    
    -- Lineage
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rejects_week ON otc_rejects(week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_rejects_reason ON otc_rejects(reason_code);
CREATE INDEX IF NOT EXISTS idx_rejects_stage ON otc_rejects(stage);
CREATE INDEX IF NOT EXISTS idx_rejects_execution ON otc_rejects(execution_id);


-- ============================================================================
-- TABLE: otc_venue_volume (modify existing - add lineage)
-- ============================================================================
ALTER TABLE otc_venue_volume ADD COLUMN execution_id TEXT;
ALTER TABLE otc_venue_volume ADD COLUMN batch_id TEXT;
ALTER TABLE otc_venue_volume ADD COLUMN normalized_at TEXT DEFAULT (datetime('now'));

CREATE INDEX IF NOT EXISTS idx_venue_vol_execution ON otc_venue_volume(execution_id);
CREATE INDEX IF NOT EXISTS idx_venue_vol_batch ON otc_venue_volume(batch_id);


-- ============================================================================
-- TABLE: otc_symbol_summary (modify existing - add lineage + versioning)
-- ============================================================================
ALTER TABLE otc_symbol_summary ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
ALTER TABLE otc_symbol_summary ADD COLUMN execution_id TEXT;
ALTER TABLE otc_symbol_summary ADD COLUMN batch_id TEXT;
ALTER TABLE otc_symbol_summary ADD COLUMN calculated_at TEXT DEFAULT (datetime('now'));

CREATE INDEX IF NOT EXISTS idx_symbol_sum_execution ON otc_symbol_summary(execution_id);
CREATE INDEX IF NOT EXISTS idx_symbol_sum_batch ON otc_symbol_summary(batch_id);


-- ============================================================================
-- TABLE: otc_venue_share (modify existing - add lineage + versioning)
-- ============================================================================
ALTER TABLE otc_venue_share ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
ALTER TABLE otc_venue_share ADD COLUMN execution_id TEXT;
ALTER TABLE otc_venue_share ADD COLUMN batch_id TEXT;
ALTER TABLE otc_venue_share ADD COLUMN calculated_at TEXT DEFAULT (datetime('now'));

CREATE INDEX IF NOT EXISTS idx_venue_share_execution ON otc_venue_share(execution_id);
CREATE INDEX IF NOT EXISTS idx_venue_share_batch ON otc_venue_share(batch_id);


-- ============================================================================
-- TABLE: otc_symbol_rolling_6w
-- Purpose: Store 6-week rolling metrics with completeness flags
-- Written by: compute_rolling_6w
-- ============================================================================
CREATE TABLE IF NOT EXISTS otc_symbol_rolling_6w (
    -- Natural key
    week_ending TEXT NOT NULL,              -- End of 6-week window (Friday)
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    
    -- Rolling metrics
    avg_6w_volume INTEGER NOT NULL,         -- 6-week average volume
    avg_6w_trades INTEGER NOT NULL,         -- 6-week average trade count
    
    -- Trend analysis
    trend_direction TEXT NOT NULL,          -- UP | DOWN | FLAT
    trend_pct TEXT NOT NULL,                -- Percentage as Decimal string
    
    -- Completeness
    weeks_in_window INTEGER NOT NULL,       -- Actual weeks available (1-6)
    is_complete_window INTEGER NOT NULL,    -- 1 if weeks_in_window == 6, else 0
    
    -- Versioning
    rolling_version TEXT NOT NULL DEFAULT 'v1.0.0',
    
    -- Lineage
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    calculated_at TEXT DEFAULT (datetime('now')),
    
    -- Constraints
    PRIMARY KEY (week_ending, tier, symbol)
);

CREATE INDEX IF NOT EXISTS idx_rolling_week ON otc_symbol_rolling_6w(week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_rolling_symbol ON otc_symbol_rolling_6w(symbol, tier);
CREATE INDEX IF NOT EXISTS idx_rolling_complete ON otc_symbol_rolling_6w(is_complete_window);


-- ============================================================================
-- TABLE: otc_research_snapshot
-- Purpose: Research-ready denormalized view of a week's data
-- Combines: venue_volume + symbol_summary + rolling metrics
-- Written by: research_snapshot_week
-- ============================================================================
CREATE TABLE IF NOT EXISTS otc_research_snapshot (
    -- Natural key
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    
    -- From venue_volume (aggregated)
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    top_venue_mpid TEXT,                    -- MPID with highest volume
    top_venue_share_pct TEXT,               -- Share as Decimal string
    
    -- From symbol_summary
    avg_trade_size TEXT,
    
    -- From rolling (if available)
    rolling_avg_6w_volume INTEGER,
    rolling_avg_6w_trades INTEGER,
    rolling_trend_direction TEXT,
    rolling_weeks_available INTEGER,
    rolling_is_complete INTEGER,
    
    -- Quality indicators
    has_rolling_data INTEGER NOT NULL,      -- 1 if rolling exists, else 0
    quality_status TEXT,                    -- PASS | WARN | FAIL (from quality checks)
    
    -- Lineage
    snapshot_version TEXT NOT NULL DEFAULT 'v1.0.0',
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    
    -- Constraints
    PRIMARY KEY (week_ending, tier, symbol)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_week ON otc_research_snapshot(week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_snapshot_symbol ON otc_research_snapshot(symbol);


-- ============================================================================
-- TABLE: otc_quality_checks
-- Purpose: Record quality check results for each pipeline run
-- Written by: aggregate_week, compute_rolling, research_snapshot
-- ============================================================================
CREATE TABLE IF NOT EXISTS otc_quality_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Scope
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    pipeline_name TEXT NOT NULL,            -- Which pipeline ran the check
    
    -- Check details
    check_name TEXT NOT NULL,               -- e.g., "no_negative_volumes"
    check_category TEXT NOT NULL,           -- INTEGRITY | COMPLETENESS | BUSINESS_RULE
    status TEXT NOT NULL,                   -- PASS | WARN | FAIL
    
    -- Check results
    check_value TEXT,                       -- Actual value found (for debugging)
    expected_value TEXT,                    -- What was expected
    tolerance TEXT,                         -- Tolerance used (if applicable)
    message TEXT,                           -- Human-readable result message
    
    -- Lineage
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    checked_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_qc_week ON otc_quality_checks(week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_qc_status ON otc_quality_checks(status);
CREATE INDEX IF NOT EXISTS idx_qc_pipeline ON otc_quality_checks(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_qc_check ON otc_quality_checks(check_name);


-- ============================================================================
-- TABLE: executions (modify existing - add parent/batch)
-- ============================================================================
ALTER TABLE executions ADD COLUMN parent_execution_id TEXT;
ALTER TABLE executions ADD COLUMN batch_id TEXT;

CREATE INDEX IF NOT EXISTS idx_exec_parent ON executions(parent_execution_id);
CREATE INDEX IF NOT EXISTS idx_exec_batch ON executions(batch_id);
```

---

## Rejection Reason Codes

Standardized codes used in `otc_rejects.reason_code`:

| Code | Stage | Description |
|------|-------|-------------|
| `PARSE_ERROR` | INGEST | Line could not be parsed (wrong delimiter, missing fields) |
| `INVALID_DATE` | INGEST | Week ending is not a valid date |
| `NOT_FRIDAY` | INGEST | Week ending is not a Friday |
| `INVALID_TIER` | INGEST | Tier value not in enum |
| `NEGATIVE_VOLUME` | NORMALIZE | Total shares is negative |
| `NEGATIVE_TRADES` | NORMALIZE | Trade count is negative |
| `ZERO_VOLUME` | NORMALIZE | Total shares is zero (optional reject) |
| `INVALID_SYMBOL` | NORMALIZE | Symbol fails validation |
| `INVALID_MPID` | NORMALIZE | MPID not 4 characters |
| `DUPLICATE_KEY` | NORMALIZE | Natural key already exists |

---

## Quality Check Names

Standardized names used in `otc_quality_checks.check_name`:

| Check Name | Category | Pass Condition |
|------------|----------|----------------|
| `no_negative_volumes` | INTEGRITY | All volumes >= 0 |
| `no_negative_trades` | INTEGRITY | All trade counts >= 0 |
| `market_share_sum_100` | BUSINESS_RULE | Sum of market shares between 99.9% and 100.1% |
| `no_duplicate_natural_keys` | INTEGRITY | Zero duplicate keys in normalized data |
| `symbol_count_positive` | COMPLETENESS | At least 1 symbol in week |
| `venue_count_positive` | COMPLETENESS | At least 1 venue in week |
| `rolling_window_complete` | COMPLETENESS | 6 weeks of data available |

---

## Migration Runner Considerations

The migration runner must handle SQLite's limited `ALTER TABLE`:

```python
def run_migration_safe(conn: sqlite3.Connection, sql: str) -> None:
    """Run migration, ignoring 'duplicate column' errors."""
    for statement in sql.split(';'):
        statement = statement.strip()
        if not statement:
            continue
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as e:
            # Ignore "duplicate column name" errors
            if "duplicate column name" in str(e).lower():
                logger.debug(f"Column already exists, skipping: {e}")
            else:
                raise
    conn.commit()
```

---

## Next: Read [02-models-and-types.md](02-models-and-types.md) for domain models
