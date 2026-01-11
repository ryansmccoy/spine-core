# Market Spine Basic – Real Multi-Week Example + Hardening Alignment

> **Mission**: Market Spine Basic demonstrates an institutional-grade OTC data platform with **real multi-week workflows**—not toy examples. While intentionally simple (synchronous, SQLite-based, self-contained), it must prove the platform's core value: temporal data ingestion, per-week processing, and rolling analytics with full lineage and idempotency guarantees.

---

## Executive Summary

### The Problem with Current Basic Tier

The existing implementation is **architecturally correct but pedagogically incomplete**:

❌ "Example" domain feels like a Hello World toy  
❌ OTC pipelines process single files, not time-series windows  
❌ No demonstration of multi-week workflows (the platform's raison d'être)  
❌ Missing the canonical learning path: backfill → normalize → rolling analytics  

### The Solution: Week is the Unit of Work

This document reorients Basic tier around a **real institutional workflow**:

✅ **6-week OTC backfill** as the canonical example  
✅ **Per-week pipelines** (ingest_week, normalize_week, aggregate_week)  
✅ **Rolling analytics** (6-week moving averages, trend detection)  
✅ **Execution lineage** (batch_id groups related work, parent_execution_id chains pipelines)  
✅ **Idempotency guarantees** (re-run backfill safely, no duplicate data)  

### What Changes

1. **OTC becomes the primary example** (remove toy "example" domain)
2. **Week-scoped pipelines** replace generic file processors
3. **Rolling analysis** proves platform value (temporal aggregations)
4. **Execution lineage** demonstrated in multi-week context
5. **Documentation** shows institutional use case, not learning exercises

---

## Table of Contents

1. [Week is the Unit of Work - Canonical Workflow](#week-is-the-unit-of-work)
2. [Required Pipeline Set (Basic Tier)](#required-pipeline-set)
3. [Schema Changes for Multi-Week Support](#schema-changes)
4. [Execution Lineage in Multi-Week Context](#execution-lineage)
5. [Idempotency for Multi-Week Workflows](#idempotency-semantics)
6. [Domain Correctness (Lightweight Validators)](#domain-correctness)
7. [File Structure Changes](#file-structure)
8. [CLI Examples - 6-Week Workflow](#cli-examples)
9. [Test Strategy](#test-strategy)

---

## Week is the Unit of Work - Canonical Workflow

### The Institutional Story

**Context**: A market data platform must process FINRA OTC transparency data published weekly (every Friday).

**Real-world requirement**: 
- Ingest 6 weeks of historical data (backfill)
- Process each week independently for parallel processing in higher tiers
- Compute rolling 6-week metrics (moving averages, trends)
- Re-run safely when data corrections arrive

### Canonical Basic Tier Workflow

```bash
# Step 1: Backfill 6 weeks of NMS Tier 1 data
spine run otc.backfill_range \
  -p tier=NMS_TIER_1 \
  -p weeks_back=6

# This executes synchronously in Basic tier:
# - Creates batch_id for the backfill run
# - For each week (2025-11-22, 2025-11-29, ..., 2026-01-03):
#     1. otc.ingest_week (parent: backfill execution)
#     2. otc.normalize_week (parent: ingest_week execution)
#     3. otc.aggregate_week (parent: normalize_week execution)
# - Finally: otc.compute_rolling_6w (parent: backfill execution)

# Step 2: Query rolling metrics
spine run otc.query_rolling -p tier=NMS_TIER_1 -p week_ending=latest
```

**Output**:
```
6-Week Rolling Analysis (NMS Tier 1, Week Ending 2026-01-03)
Symbol  | 6W Avg Volume | 6W Avg Trades | Trend      | Weeks
--------|---------------|---------------|------------|------
AAPL    | 12,450,000    | 8,234         | UP +12%    | 6
TSLA    | 8,900,000     | 5,123         | DOWN -5%   | 6
NVDA    | 15,200,000    | 10,456        | FLAT +1%   | 6
```

### Why This Proves the Platform

**Temporal Reasoning**:
- Week boundaries are enforced (Fridays only)
- Per-week processing enables parallelization in higher tiers
- Rolling windows demonstrate time-series capabilities

**Execution Lineage**:
- `batch_id` groups all 6 weeks + rolling calc into one backfill run
- `parent_execution_id` chains: backfill → ingest_week → normalize_week → aggregate_week
- Reprocessing single week preserves lineage: "Re-run 2025-12-06 after data correction"

**Idempotency**:
- Re-run `backfill_range` with same `weeks_back=6`: no duplicate data
- `otc_venue_volume` UNIQUE constraint on (week_ending, tier, symbol, mpid)
- Rolling metrics recalculated from source data (state-idempotent)

**Forward Compatibility**:
- **Intermediate**: `backfill_range` submits async tasks instead of synchronous loop
- **Advanced**: Each week becomes Celery task in distributed queue
- **Full**: Week-scoped events enable event sourcing with temporal queries

---

## Required Pipeline Set (Basic Tier)

### 1. `otc.ingest_week`

**Purpose**: Ingest OTC data for a single week.

**Parameters**:
```python
{
    "tier": "NMS_TIER_1" | "NMS_TIER_2" | "OTC",
    "week_ending": "2026-01-03",  # ISO Friday date
    "source": "file" | "url",     # File path or FINRA URL
    "file_path": "data/finra/week_2026-01-03.csv",  # If source=file
    "url": "https://...",          # If source=url
    "force": false                 # Re-ingest even if exists
}
```

**Logic**:
1. Validate `week_ending` is a Friday (via `validate_week_ending_is_friday()`)
2. Check if week already ingested (unless `force=true`)
3. Parse FINRA CSV (pipe-delimited)
4. Insert into `otc_raw` with `record_hash` dedup
5. Record `execution_id`, `batch_id` in each row

**Idempotency**: Input-Idempotent (Level 2)
- Same file + same week → no duplicate records (via `record_hash`)

**Returns**:
```python
PipelineResult(
    status=COMPLETED,
    metrics={
        "week_ending": "2026-01-03",
        "tier": "NMS_TIER_1",
        "records_parsed": 14,
        "records_inserted": 14,
        "records_skipped": 0
    }
)
```

---

### 2. `otc.normalize_week`

**Purpose**: Normalize raw data for a single week into `otc_venue_volume`.

**Parameters**:
```python
{
    "tier": "NMS_TIER_1",
    "week_ending": "2026-01-03",
    "force": false  # Re-normalize even if exists
}
```

**Logic**:
1. Validate week_ending is Friday
2. Check if week already normalized (unless `force=true`)
3. Fetch raw records: `SELECT * FROM otc_raw WHERE week_ending = ? AND tier = ?`
4. Normalize: validate volume > 0, parse tier enum, calc avg_trade_size
5. Insert into `otc_venue_volume` (UNIQUE constraint handles duplicates)
6. Record `execution_id`, `batch_id`

**Idempotency**: State-Idempotent (Level 3)
- Re-running with same week → UNIQUE constraint prevents duplicates
- Uses `INSERT OR REPLACE` for safety

**Returns**:
```python
PipelineResult(
    status=COMPLETED,
    metrics={
        "week_ending": "2026-01-03",
        "tier": "NMS_TIER_1",
        "records_accepted": 14,
        "records_rejected": 0
    }
)
```

---

### 3. `otc.aggregate_week`

**Purpose**: Compute per-week aggregates (symbol summary, venue market share).

**Parameters**:
```python
{
    "tier": "NMS_TIER_1",
    "week_ending": "2026-01-03",
    "calc_version": "v1.0.0"  # Optional, defaults to current
}
```

**Logic**:
1. Validate week_ending
2. Fetch venue_volume data for week: `SELECT * FROM otc_venue_volume WHERE week_ending = ? AND tier = ?`
3. Compute symbol summaries (group by symbol)
4. Compute venue market shares (group by mpid)
5. Delete existing aggregates for this week+tier, insert new
6. Record `execution_id`, `batch_id`, `calculation_version`

**Idempotency**: State-Idempotent (Level 3)
- Uses `DELETE WHERE week_ending = ? AND tier = ?` then `INSERT`
- Same input → same aggregates

**Returns**:
```python
PipelineResult(
    status=COMPLETED,
    metrics={
        "week_ending": "2026-01-03",
        "tier": "NMS_TIER_1",
        "symbols_aggregated": 6,
        "venues_aggregated": 5,
        "calculation_version": "v1.0.0"
    }
)
```

---

### 4. `otc.compute_rolling_6w`

**Purpose**: Compute 6-week rolling metrics (moving averages, trends).

**Parameters**:
```python
{
    "tier": "NMS_TIER_1",
    "week_ending": "2026-01-03" | "latest",  # End of window
    "rolling_version": "v1.0.0"
}
```

**Logic**:
1. Determine window: if "latest", find max(week_ending) in otc_symbol_summary
2. Validate window has 6 weeks of data
3. For each symbol, compute:
   - 6-week average volume
   - 6-week average trades
   - Trend direction: compare last 2 weeks vs first 2 weeks
   - Weeks in window (may be <6 for new symbols)
4. Insert into `otc_symbol_rolling_6w` (UNIQUE on week_ending, tier, symbol, rolling_version)
5. Record `execution_id`, `batch_id`

**Trend Calculation**:
```python
last_2w_avg = avg(week5_volume, week6_volume)
first_2w_avg = avg(week1_volume, week2_volume)
pct_change = ((last_2w_avg - first_2w_avg) / first_2w_avg) * 100

if pct_change > 5: trend = "UP"
elif pct_change < -5: trend = "DOWN"
else: trend = "FLAT"
```

**Idempotency**: State-Idempotent (Level 3)
- Re-running with same window → same metrics
- Uses `DELETE + INSERT` pattern

**Returns**:
```python
PipelineResult(
    status=COMPLETED,
    metrics={
        "week_ending": "2026-01-03",
        "tier": "NMS_TIER_1",
        "symbols_with_rolling": 6,
        "window_weeks": 6,
        "rolling_version": "v1.0.0"
    }
)
```

---

### 5. `otc.backfill_range`

**Purpose**: Synchronously process a range of weeks (Basic tier orchestration).

**Parameters**:
```python
{
    "tier": "NMS_TIER_1",
    
    # Option A: Explicit range
    "start_week": "2025-11-22",  # ISO Friday
    "end_week": "2026-01-03",    # ISO Friday (inclusive)
    
    # Option B: Relative range (easier)
    "weeks_back": 6,  # From today, go back N weeks
    
    "force": false  # Re-process even if exists
}
```

**Logic**:
1. Determine week list (either from start/end or weeks_back)
2. Validate all weeks are Fridays
3. Create `batch_id` for this backfill run: `f"backfill_{tier}_{start}_{end}_{timestamp}"`
4. For each week (synchronously in Basic tier):
   ```python
   for week in week_list:
       # Ingest
       ingest_exec = dispatcher.submit(
           "otc.ingest_week",
           params={"tier": tier, "week_ending": week, "source": "file", "file_path": f"data/{week}.csv"},
           batch_id=batch_id,
           parent_execution_id=backfill_execution_id
       )
       
       # Normalize
       normalize_exec = dispatcher.submit(
           "otc.normalize_week",
           params={"tier": tier, "week_ending": week},
           batch_id=batch_id,
           parent_execution_id=ingest_exec.execution_id
       )
       
       # Aggregate
       aggregate_exec = dispatcher.submit(
           "otc.aggregate_week",
           params={"tier": tier, "week_ending": week},
           batch_id=batch_id,
           parent_execution_id=normalize_exec.execution_id
       )
   ```
5. Compute rolling for latest week:
   ```python
   rolling_exec = dispatcher.submit(
       "otc.compute_rolling_6w",
       params={"tier": tier, "week_ending": "latest"},
       batch_id=batch_id,
       parent_execution_id=backfill_execution_id
   )
   ```

**Idempotency**: State-Idempotent (Level 3)
- Re-running same range → per-week pipelines are idempotent → same final state
- Safe to retry on failure

**Returns**:
```python
PipelineResult(
    status=COMPLETED,
    metrics={
        "tier": "NMS_TIER_1",
        "weeks_processed": 6,
        "total_records_ingested": 84,
        "batch_id": "backfill_NMS_TIER_1_2025-11-22_2026-01-03_20260103T150022"
    }
)
```

**Evolution**:
- **Basic**: Synchronous loop (blocks until all weeks done)
- **Intermediate**: Submit async tasks, wait for completion
- **Advanced**: Celery chord pattern (parallel workers, final callback)
- **Full**: Event-driven saga with compensation logic

---

## Schema Changes for Multi-Week Support

### New Tables

#### 1. `otc_symbol_rolling_6w` (New)

**Purpose**: Store 6-week rolling metrics for symbols.

```sql
CREATE TABLE otc_symbol_rolling_6w (
    week_ending TEXT NOT NULL,           -- End of 6-week window (Friday)
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    
    avg_6w_volume INTEGER NOT NULL,      -- 6-week average volume
    avg_6w_trades INTEGER NOT NULL,      -- 6-week average trade count
    trend_direction TEXT NOT NULL,       -- "UP" | "DOWN" | "FLAT"
    trend_pct TEXT NOT NULL,             -- Percentage change (Decimal as text)
    weeks_in_window INTEGER NOT NULL,    -- Actual weeks available (may be <6)
    
    rolling_version TEXT NOT NULL,       -- Calculation version (e.g., "v1.0.0")
    execution_id TEXT NOT NULL,          -- Which execution created this
    batch_id TEXT,                       -- Group with related work
    calculated_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, rolling_version)
);

CREATE INDEX idx_otc_rolling_week ON otc_symbol_rolling_6w(week_ending, tier);
CREATE INDEX idx_otc_rolling_symbol ON otc_symbol_rolling_6w(symbol, tier);
```

### Modified Tables

#### 2. `otc_raw` (Add Lineage Columns)

```sql
-- Add columns to existing table
ALTER TABLE otc_raw ADD COLUMN execution_id TEXT;
ALTER TABLE otc_raw ADD COLUMN batch_id TEXT;

-- Index for lineage queries
CREATE INDEX idx_otc_raw_execution ON otc_raw(execution_id);
CREATE INDEX idx_otc_raw_batch ON otc_raw(batch_id);
```

**Lineage Use Case**:
```sql
-- Find all raw data from a backfill run
SELECT * FROM otc_raw WHERE batch_id = 'backfill_NMS_TIER_1_...';

-- Find data from specific execution
SELECT * FROM otc_raw WHERE execution_id = 'exec_abc123';
```

---

#### 3. `otc_venue_volume` (Add Lineage + Calculation Version)

```sql
ALTER TABLE otc_venue_volume ADD COLUMN execution_id TEXT;
ALTER TABLE otc_venue_volume ADD COLUMN batch_id TEXT;

CREATE INDEX idx_otc_venue_execution ON otc_venue_volume(execution_id);
CREATE INDEX idx_otc_venue_batch ON otc_venue_volume(batch_id);
```

---

#### 4. `otc_symbol_summary` (Add Lineage + Calculation Version)

```sql
ALTER TABLE otc_symbol_summary ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
ALTER TABLE otc_symbol_summary ADD COLUMN execution_id TEXT;
ALTER TABLE otc_symbol_summary ADD COLUMN batch_id TEXT;
ALTER TABLE otc_symbol_summary ADD COLUMN calculated_at TEXT DEFAULT (datetime('now'));

-- Update UNIQUE constraint to allow multiple versions
DROP INDEX IF EXISTS idx_otc_symbol_summary_unique;
CREATE UNIQUE INDEX idx_otc_symbol_summary_unique 
    ON otc_symbol_summary(week_ending, tier, symbol, calculation_version);

CREATE INDEX idx_otc_summary_execution ON otc_symbol_summary(execution_id);
CREATE INDEX idx_otc_summary_batch ON otc_symbol_summary(batch_id);
```

---

#### 5. `otc_venue_share` (Add Lineage + Calculation Version)

```sql
ALTER TABLE otc_venue_share ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
ALTER TABLE otc_venue_share ADD COLUMN execution_id TEXT;
ALTER TABLE otc_venue_share ADD COLUMN batch_id TEXT;
ALTER TABLE otc_venue_share ADD COLUMN calculated_at TEXT DEFAULT (datetime('now'));

DROP INDEX IF EXISTS idx_otc_venue_share_unique;
CREATE UNIQUE INDEX idx_otc_venue_share_unique 
    ON otc_venue_share(week_ending, mpid, calculation_version);

CREATE INDEX idx_otc_venue_share_execution ON otc_venue_share(execution_id);
CREATE INDEX idx_otc_venue_share_batch ON otc_venue_share(batch_id);
```

---

### Migration File: `021_otc_multi_week_support.sql`

```sql
-- Add lineage to existing tables
ALTER TABLE otc_raw ADD COLUMN execution_id TEXT;
ALTER TABLE otc_raw ADD COLUMN batch_id TEXT;

ALTER TABLE otc_venue_volume ADD COLUMN execution_id TEXT;
ALTER TABLE otc_venue_volume ADD COLUMN batch_id TEXT;

ALTER TABLE otc_symbol_summary ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
ALTER TABLE otc_symbol_summary ADD COLUMN execution_id TEXT;
ALTER TABLE otc_symbol_summary ADD COLUMN batch_id TEXT;
ALTER TABLE otc_symbol_summary ADD COLUMN calculated_at TEXT DEFAULT (datetime('now'));

ALTER TABLE otc_venue_share ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
ALTER TABLE otc_venue_share ADD COLUMN execution_id TEXT;
ALTER TABLE otc_venue_share ADD COLUMN batch_id TEXT;
ALTER TABLE otc_venue_share ADD COLUMN calculated_at TEXT DEFAULT (datetime('now'));

-- Create rolling metrics table
CREATE TABLE otc_symbol_rolling_6w (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    avg_6w_volume INTEGER NOT NULL,
    avg_6w_trades INTEGER NOT NULL,
    trend_direction TEXT NOT NULL,
    trend_pct TEXT NOT NULL,
    weeks_in_window INTEGER NOT NULL,
    rolling_version TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    calculated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(week_ending, tier, symbol, rolling_version)
);

-- Indexes for performance
CREATE INDEX idx_otc_raw_execution ON otc_raw(execution_id);
CREATE INDEX idx_otc_raw_batch ON otc_raw(batch_id);
CREATE INDEX idx_otc_venue_execution ON otc_venue_volume(execution_id);
CREATE INDEX idx_otc_venue_batch ON otc_venue_volume(batch_id);
CREATE INDEX idx_otc_summary_execution ON otc_symbol_summary(execution_id);
CREATE INDEX idx_otc_summary_batch ON otc_symbol_summary(batch_id);
CREATE INDEX idx_otc_venue_share_execution ON otc_venue_share(execution_id);
CREATE INDEX idx_otc_venue_share_batch ON otc_venue_share(batch_id);
CREATE INDEX idx_otc_rolling_week ON otc_symbol_rolling_6w(week_ending, tier);
CREATE INDEX idx_otc_rolling_symbol ON otc_symbol_rolling_6w(symbol, tier);
```

---

### Lineage Query Examples

**Find all work from a backfill run**:
```sql
SELECT 
    'raw' AS stage, COUNT(*) AS records 
FROM otc_raw 
WHERE batch_id = 'backfill_NMS_TIER_1_2025-11-22_2026-01-03_20260103T150022'

UNION ALL

SELECT 
    'normalized' AS stage, COUNT(*) AS records 
FROM otc_venue_volume 
WHERE batch_id = 'backfill_NMS_TIER_1_2025-11-22_2026-01-03_20260103T150022'

UNION ALL

SELECT 
    'aggregated' AS stage, COUNT(*) AS records 
FROM otc_symbol_summary 
WHERE batch_id = 'backfill_NMS_TIER_1_2025-11-22_2026-01-03_20260103T150022';
```

**Output**:
```
stage       | records
------------|--------
raw         | 84
normalized  | 84
aggregated  | 36
```

**Find execution chain**:
```sql
WITH RECURSIVE exec_chain AS (
    -- Start with backfill execution
    SELECT execution_id, parent_execution_id, pipeline_name, 0 AS depth
    FROM executions
    WHERE execution_id = 'exec_backfill_123'
    
    UNION ALL
    
    -- Find children
    SELECT e.execution_id, e.parent_execution_id, e.pipeline_name, ec.depth + 1
    FROM executions e
    JOIN exec_chain ec ON e.parent_execution_id = ec.execution_id
)
SELECT * FROM exec_chain ORDER BY depth;
```

**Output**:
```
execution_id        | parent_id          | pipeline_name          | depth
--------------------|-------------------|------------------------|------
exec_backfill_123   | NULL              | otc.backfill_range     | 0
exec_ingest_w1      | exec_backfill_123 | otc.ingest_week        | 1
exec_normalize_w1   | exec_ingest_w1    | otc.normalize_week     | 2
exec_aggregate_w1   | exec_normalize_w1 | otc.aggregate_week     | 3
...
exec_rolling_123    | exec_backfill_123 | otc.compute_rolling_6w | 1
```

## Execution Lineage in Multi-Week Context

### How Lineage Works in the 6-Week Backfill

**Scenario**: User runs `otc.backfill_range` with `weeks_back=6`.

**Lineage Tree**:
```
backfill_range (execution_id: exec_bf_001, batch_id: batch_bf_001)
│
├── ingest_week (2025-11-22) (exec_ig_001, parent: exec_bf_001, batch: batch_bf_001)
│   └── normalize_week (2025-11-22) (exec_nm_001, parent: exec_ig_001, batch: batch_bf_001)
│       └── aggregate_week (2025-11-22) (exec_ag_001, parent: exec_nm_001, batch: batch_bf_001)
│
├── ingest_week (2025-11-29) (exec_ig_002, parent: exec_bf_001, batch: batch_bf_001)
│   └── normalize_week (2025-11-29) (exec_nm_002, parent: exec_ig_002, batch: batch_bf_001)
│       └── aggregate_week (2025-11-29) (exec_ag_002, parent: exec_nm_002, batch: batch_bf_001)
│
├── ... (4 more weeks)
│
└── compute_rolling_6w (2026-01-03) (exec_rl_001, parent: exec_bf_001, batch: batch_bf_001)
```

**Key Properties**:
- **Single batch_id**: All 6 weeks + rolling calc share `batch_bf_001`
- **Parent chaining**: Each execution knows its parent
- **Week isolation**: Each week's ingest → normalize → aggregate chain is independent

**Benefits**:
1. **Audit**: "Show me everything from this backfill" → `WHERE batch_id = 'batch_bf_001'`
2. **Reprocessing**: "Re-run 2025-12-06 only" → Create new execution with same week_ending, different batch_id
3. **Debugging**: "Which normalize created this bad data?" → Follow execution_id in otc_venue_volume

---

### Batch Identity Design for Multi-Week

**Format**:
```python
# Backfill batch
batch_id = f"backfill_{tier}_{start_week}_{end_week}_{timestamp}"
# Example: "backfill_NMS_TIER_1_2025-11-22_2026-01-03_20260103T150022"

# Single-week reprocessing batch
batch_id = f"reprocess_{tier}_{week_ending}_{timestamp}"
# Example: "reprocess_NMS_TIER_1_2025-12-06_20260110T093000"
```

**Properties**:
- **Temporal**: Encodes week range (for backfill) or single week (for reprocessing)
- **Tier-scoped**: Different tiers = different batches
- **Unique**: Timestamp ensures re-running backfill creates new batch
- **Queryable**: `WHERE batch_id LIKE 'backfill_NMS_TIER_1%'`

**Evolution**:
- **Basic**: Single string identifier
- **Intermediate**: Stored in `batches` table with metadata (status, created_at, user)
- **Advanced**: Batch becomes saga identifier with compensation logic
- **Full**: Batch ID is event stream partition key

---

### Implementation in Dispatcher (Basic Tier)

**Updated Execution Model**:
```python
@dataclass
class Execution:
    execution_id: str
    pipeline_name: str
    parent_execution_id: str | None  # NEW
    batch_id: str | None              # NEW
    params: dict[str, Any]
    trigger_source: TriggerSource
    logical_key: str | None
    lane: Lane
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    metrics: dict[str, Any]
```

**Updated Submit Signature**:
```python
def submit(
    self,
    pipeline: str,
    params: dict[str, Any] | None = None,
    parent_execution_id: str | None = None,  # NEW
    batch_id: str | None = None,             # NEW
    lane: Lane = Lane.NORMAL,
    trigger_source: TriggerSource = TriggerSource.CLI,
    logical_key: str | None = None,
) -> Execution:
    execution_id = str(uuid.uuid4())
    
    # Store execution with lineage
    execution = Execution(
        execution_id=execution_id,
        pipeline_name=pipeline,
        parent_execution_id=parent_execution_id,
        batch_id=batch_id,
        params=params or {},
        trigger_source=trigger_source,
        logical_key=logical_key,
        lane=lane,
        status=PipelineStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        error=None,
        metrics={}
    )
    
    # Execute pipeline
    result = self._runner.run(pipeline, params)
    
    # Update execution with result
    execution.status = result.status
    execution.completed_at = result.completed_at
    execution.error = result.error
    execution.metrics = result.metrics
    
    return execution
```

**Database Schema**:
```sql
-- Update executions table
ALTER TABLE executions ADD COLUMN parent_execution_id TEXT;
ALTER TABLE executions ADD COLUMN batch_id TEXT;

CREATE INDEX idx_executions_parent ON executions(parent_execution_id);
CREATE INDEX idx_executions_batch ON executions(batch_id);
```

---

### Usage Example in Pipelines

**In `otc.backfill_range`**:
```python
class OTCBackfillRangePipeline(Pipeline):
    def run(self) -> PipelineResult:
        # Create batch identity
        batch_id = f"backfill_{self.params['tier']}_{start}_{end}_{timestamp}"
        
        # Get current execution ID (from context)
        backfill_exec_id = self.execution_id  # Injected by runner
        
        weeks = self._generate_week_list()
        
        for week in weeks:
            # Ingest
            ingest_exec = get_dispatcher().submit(
                "otc.ingest_week",
                params={"tier": tier, "week_ending": week, ...},
                parent_execution_id=backfill_exec_id,
                batch_id=batch_id
            )
            
            # Normalize (parent = ingest)
            normalize_exec = get_dispatcher().submit(
                "otc.normalize_week",
                params={"tier": tier, "week_ending": week},
                parent_execution_id=ingest_exec.execution_id,
                batch_id=batch_id
            )
            
            # Aggregate (parent = normalize)
            aggregate_exec = get_dispatcher().submit(
                "otc.aggregate_week",
                params={"tier": tier, "week_ending": week},
                parent_execution_id=normalize_exec.execution_id,
                batch_id=batch_id
            )
        
        # Rolling (parent = backfill)
        rolling_exec = get_dispatcher().submit(
            "otc.compute_rolling_6w",
            params={"tier": tier, "week_ending": "latest"},
            parent_execution_id=backfill_exec_id,
            batch_id=batch_id
        )
        
        return PipelineResult(...)
```

**In `otc.ingest_week`**:
```python
class OTCIngestWeekPipeline(Pipeline):
    def run(self) -> PipelineResult:
        # Parse file
        records = parse_finra_file(self.params["file_path"])
        
        # Get execution metadata from context
        execution_id = self.execution_id
        batch_id = self.batch_id
        
        # Insert with lineage
        for record in records:
            conn.execute("""
                INSERT INTO otc_raw (
                    batch_id, execution_id, record_hash, week_ending, ...
                ) VALUES (?, ?, ?, ?, ...)
            """, (batch_id, execution_id, record.hash(), record.week_ending, ...))
        
        return PipelineResult(...)
```

## Idempotency for Multi-Week Workflows

### The Critical Question

**What happens if you re-run `otc.backfill_range` with the same parameters?**

Answer: **Identical final state, no duplicate data.**

### Idempotency Guarantees by Pipeline

| Pipeline | Level | Re-run Behavior | Mechanism |
|----------|-------|-----------------|-----------|
| `otc.ingest_week` | Input-Idempotent | Duplicate records skipped | `record_hash UNIQUE` constraint |
| `otc.normalize_week` | State-Idempotent | Re-creates normalized records | `INSERT OR REPLACE` on natural key |
| `otc.aggregate_week` | State-Idempotent | Recalculates from source | `DELETE + INSERT` pattern |
| `otc.compute_rolling_6w` | State-Idempotent | Recalculates window | `DELETE + INSERT` on (week, tier, symbol, version) |
| `otc.backfill_range` | State-Idempotent | Re-runs all sub-pipelines safely | Composition of idempotent pipelines |

### Detailed Idempotency Semantics

#### Level 2: Input-Idempotent (`otc.ingest_week`)

**Contract**: Running with same (tier, week_ending, file_path) multiple times inserts records **exactly once**.

**Implementation**:
```python
# In parser.py
def generate_record_hash(record: dict) -> str:
    """Deterministic hash based on domain key + content."""
    key = f"{record['week_ending']}|{record['tier']}|{record['symbol']}|{record['mpid']}"
    content = f"{record['share_volume']}|{record['trade_count']}"
    return hashlib.sha256(f"{key}|{content}".encode()).hexdigest()[:16]

# In otc.ingest_week pipeline
for record in records:
    hash_value = generate_record_hash(record)
    try:
        conn.execute("""
            INSERT INTO otc_raw (record_hash, week_ending, ...)
            VALUES (?, ?, ...)
        """, (hash_value, week_ending, ...))
    except sqlite3.IntegrityError:
        # record_hash UNIQUE constraint violated = already exists
        skipped += 1
        continue
```

**Result**:
```python
# First run
PipelineResult(metrics={"inserted": 14, "skipped": 0})

# Second run (same file)
PipelineResult(metrics={"inserted": 0, "skipped": 14})
```

---

#### Level 3: State-Idempotent (`otc.normalize_week`, `otc.aggregate_week`)

**Contract**: Running with same (tier, week_ending) multiple times produces **identical output state**.

**Pattern A: INSERT OR REPLACE** (for `otc.normalize_week`):
```python
# Natural key: (week_ending, tier, symbol, mpid)
conn.execute("""
    INSERT INTO otc_venue_volume (
        week_ending, tier, symbol, mpid, share_volume, trade_count, 
        avg_trade_size, record_hash, execution_id, batch_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(week_ending, tier, symbol, mpid) 
    DO UPDATE SET
        share_volume = excluded.share_volume,
        trade_count = excluded.trade_count,
        avg_trade_size = excluded.avg_trade_size,
        record_hash = excluded.record_hash,
        execution_id = excluded.execution_id,
        batch_id = excluded.batch_id,
        normalized_at = datetime('now')
""", (week, tier, symbol, mpid, volume, trades, avg_size, hash, exec_id, batch_id))
```

**Pattern B: DELETE + INSERT** (for `otc.aggregate_week`):
```python
# Remove old aggregates for this week+tier
conn.execute("""
    DELETE FROM otc_symbol_summary 
    WHERE week_ending = ? AND tier = ? AND calculation_version = ?
""", (week_ending, tier, calc_version))

conn.execute("""
    DELETE FROM otc_venue_share 
    WHERE week_ending = ? AND calculation_version = ?
""", (week_ending, calc_version))

# Insert fresh aggregates
for summary in symbol_summaries:
    conn.execute("INSERT INTO otc_symbol_summary (...) VALUES (...)")

for share in venue_shares:
    conn.execute("INSERT INTO otc_venue_share (...) VALUES (...)")
```

**Why DELETE + INSERT?**
- **Handles removals**: If source data changed, old symbols are removed
- **Clean slate**: No orphaned records from previous runs
- **Auditable**: calculation_version + execution_id track which run created data

---

### Multi-Week Backfill Idempotency

**Scenario**: Run backfill twice with same parameters.

**First Run**:
```bash
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=6
```

**Output**:
```
Execution: exec_bf_001
Batch: batch_bf_001
Weeks processed: 6
Records ingested: 84 (inserted: 84, skipped: 0)
Records normalized: 84
Symbols aggregated: 36
Rolling metrics: 6 symbols
```

**Second Run** (5 minutes later):
```bash
spine run otc.backfill_range -p tier=NMS_TIER_1 -p weeks_back=6
```

**Output**:
```
Execution: exec_bf_002
Batch: batch_bf_002
Weeks processed: 6
Records ingested: 0 (inserted: 0, skipped: 84)  ← All duplicates skipped
Records normalized: 84                           ← Re-normalized (idempotent)
Symbols aggregated: 36                           ← Recalculated (idempotent)
Rolling metrics: 6 symbols                       ← Recalculated (idempotent)
```

**Final Database State**: Identical to first run
- `otc_raw`: 84 records (batch_bf_001 execution_ids)
- `otc_venue_volume`: 84 records (batch_bf_002 execution_ids, updated)
- `otc_symbol_summary`: 36 records (batch_bf_002, calc v1.0.0)
- `otc_symbol_rolling_6w`: 6 records (batch_bf_002, rolling v1.0.0)

**Key Insight**: Re-running is safe but updates `execution_id` and `batch_id` in derived tables for lineage.

---

### Partial Reprocessing (Single Week)

**Scenario**: Week 2025-12-06 had bad data. Correct the file and reprocess.

```bash
# Reprocess just one week
spine run otc.ingest_week \
  -p tier=NMS_TIER_1 \
  -p week_ending=2025-12-06 \
  -p source=file \
  -p file_path=data/corrected_2025-12-06.csv \
  -p force=true

spine run otc.normalize_week -p tier=NMS_TIER_1 -p week_ending=2025-12-06
spine run otc.aggregate_week -p tier=NMS_TIER_1 -p week_ending=2025-12-06
spine run otc.compute_rolling_6w -p tier=NMS_TIER_1 -p week_ending=latest
```

**Result**:
- Week 2025-12-06 data replaced (new execution_id, new batch_id)
- Other weeks unchanged
- Rolling metrics recalculated using corrected data

**Lineage Query**:
```sql
-- Find all data from the reprocessing
SELECT * FROM otc_raw 
WHERE week_ending = '2025-12-06' 
ORDER BY ingested_at DESC 
LIMIT 14;

-- See both old and new execution_ids
```

---

### Force Flag Behavior

**Without `force=false` (default)**:
```python
# In otc.ingest_week
existing_count = conn.execute("""
    SELECT COUNT(*) FROM otc_raw 
    WHERE week_ending = ? AND tier = ?
""", (week_ending, tier)).fetchone()[0]

if existing_count > 0 and not self.params.get("force", False):
    return PipelineResult(
        status=PipelineStatus.SKIPPED,
        metrics={"reason": "Week already ingested. Use force=true to re-ingest."}
    )
```

**With `force=true`**:
- Skips the check, proceeds with ingestion
- `record_hash` still prevents duplicates from same file
- Useful for: adding new records to existing week, re-ingesting after schema changes

---

### Idempotency Testing Strategy

**Golden Fixtures**: 6 weeks of test data
```
tests/fixtures/otc/
├── week_2025-11-22.csv (14 records, NMS Tier 1)
├── week_2025-11-29.csv (14 records, NMS Tier 1)
├── week_2025-12-06.csv (14 records, NMS Tier 1)
├── week_2025-12-13.csv (14 records, NMS Tier 1)
├── week_2025-12-20.csv (14 records, NMS Tier 1)
└── week_2026-01-03.csv (14 records, NMS Tier 1)
```

**Test Cases**:
```python
def test_backfill_idempotency():
    """Backfill twice → identical final state."""
    # First run
    result1 = dispatcher.submit("otc.backfill_range", {
        "tier": "NMS_TIER_1",
        "weeks_back": 6
    })
    
    # Capture state
    state1 = {
        "raw": conn.execute("SELECT COUNT(*) FROM otc_raw").fetchone()[0],
        "normalized": conn.execute("SELECT COUNT(*) FROM otc_venue_volume").fetchone()[0],
        "summaries": conn.execute("SELECT COUNT(*) FROM otc_symbol_summary").fetchone()[0],
        "rolling": conn.execute("SELECT COUNT(*) FROM otc_symbol_rolling_6w").fetchone()[0]
    }
    
    # Second run
    result2 = dispatcher.submit("otc.backfill_range", {
        "tier": "NMS_TIER_1",
        "weeks_back": 6
    })
    
    # Capture state
    state2 = {
        "raw": conn.execute("SELECT COUNT(*) FROM otc_raw").fetchone()[0],
        "normalized": conn.execute("SELECT COUNT(*) FROM otc_venue_volume").fetchone()[0],
        "summaries": conn.execute("SELECT COUNT(*) FROM otc_symbol_summary").fetchone()[0],
        "rolling": conn.execute("SELECT COUNT(*) FROM otc_symbol_rolling_6w").fetchone()[0]
    }
    
    # Assert identical counts
    assert state1 == state2
    
    # Assert execution lineage updated
    assert result1.execution_id != result2.execution_id
    assert result1.batch_id != result2.batch_id
```

**Test Output**:
```
✓ test_backfill_idempotency
  First run:  raw=84, normalized=84, summaries=36, rolling=6
  Second run: raw=84, normalized=84, summaries=36, rolling=6
  PASS: Counts identical, lineage updated
```

---

## Domain Correctness (Lightweight Validators)

## Domain Correctness (Lightweight Validators)

### Design Philosophy for Basic Tier

**Avoid Heavy Value Objects**: Reserve `WeekEnding` and `Symbol` classes for Intermediate tier where PostgreSQL and repositories justify the complexity.

**Use Lightweight Validators**: Simple functions that raise descriptive errors.

---

### Week Ending Validation

**Function**:
```python
# In domains/otc/validators.py
from datetime import date

def validate_week_ending_is_friday(week_ending: str | date) -> date:
    """
    Validate that week_ending is a Friday.
    
    Args:
        week_ending: ISO date string "YYYY-MM-DD" or date object
    
    Returns:
        date object (validated Friday)
    
    Raises:
        ValueError: If not a Friday
    """
    if isinstance(week_ending, str):
        parsed = date.fromisoformat(week_ending)
    else:
        parsed = week_ending
    
    if parsed.weekday() != 4:  # 0=Monday, 4=Friday
        raise ValueError(
            f"Week ending must be a Friday. "
            f"Got {parsed.isoformat()} ({parsed.strftime('%A')})"
        )
    
    return parsed
```

**Usage**:
```python
# In otc.ingest_week pipeline
def run(self) -> PipelineResult:
    week_ending = validate_week_ending_is_friday(self.params["week_ending"])
    # Proceeds only if Friday...
```

**Error Message** (user-friendly):
```
ValueError: Week ending must be a Friday. Got 2026-01-03 (Saturday)
```

---

### Symbol Normalization

**Function**:
```python
# In domains/otc/validators.py
import re

def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol to uppercase, alphanumeric + dash/dot only.
    
    Args:
        symbol: Raw symbol from data file
    
    Returns:
        Normalized symbol (uppercase, validated)
    
    Raises:
        ValueError: If symbol format invalid
    """
    normalized = symbol.strip().upper()
    
    if not re.match(r"^[A-Z0-9.\-]+$", normalized):
        raise ValueError(
            f"Invalid symbol format: '{symbol}'. "
            f"Must be alphanumeric with optional dots/dashes."
        )
    
    return normalized
```

**Usage**:
```python
# In parser.py
def parse_finra_file(file_path: Path) -> Iterator[dict]:
    for row in csv.DictReader(f, delimiter="|"):
        yield {
            "symbol": normalize_symbol(row["Symbol"]),  # "aapl" → "AAPL"
            "week_ending": row["WeekEnding"],
            ...
        }
```

**Why Lightweight?**
- No class overhead
- Easy to test: `assert normalize_symbol("aapl") == "AAPL"`
- Upgrade path: In Intermediate, wrap in `Symbol` class with same validation logic

---

### Tier Validation

**Already Exists**: `Tier` enum in `models.py`
```python
class Tier(str, Enum):
    NMS_TIER_1 = "NMS Tier 1"
    NMS_TIER_2 = "NMS Tier 2"
    OTC = "OTC"
```

**Validation Happens Automatically**:
```python
# In parser.py
tier = Tier(row["TierName"])  # Raises ValueError if invalid
```

---

### Natural Key Invariants

**Document in Code**:
```python
# In domains/otc/models.py
"""
OTC Domain Natural Keys (Immutable Across All Tiers)

Venue Volume:
    (week_ending: date, tier: Tier, symbol: str, mpid: str)
    
Symbol Summary:
    (week_ending: date, tier: Tier, symbol: str)
    
Venue Market Share:
    (week_ending: date, mpid: str)

These keys are FROZEN and will never change. They become:
- Composite partition keys in TimescaleDB (Advanced tier)
- Event stream routing keys (Full tier)
"""

@dataclass
class VenueVolume:
    week_ending: str  # ISO Friday date
    tier: Tier
    symbol: str       # Normalized uppercase
    mpid: str         # 4-char venue code
    
    share_volume: int
    trade_count: int
    avg_trade_size: Decimal | None
    record_hash: str
    
    # Lineage
    execution_id: str | None = None
    batch_id: str | None = None
```

---

## File Structure Changes

### Current OTC Domain Structure

```
domains/otc/
├── __init__.py
├── models.py          # RawRecord, VenueVolume, SymbolSummary, VenueShare
├── parser.py          # parse_finra_file()
├── normalizer.py      # normalize_records()
├── calculations.py    # compute_symbol_summaries(), compute_venue_shares()
└── pipelines.py       # 3 pipelines (ingest, normalize, summarize)
```

### Proposed Structure (Multi-Week Support)

```
domains/otc/
├── __init__.py
├── models.py          # All domain models + Rolling6Week
├── validators.py      # NEW: validate_week_ending_is_friday(), normalize_symbol()
├── parser.py          # parse_finra_file()
├── normalizer.py      # normalize_records()
├── calculations.py    # compute_symbol_summaries(), compute_venue_shares()
├── rolling.py         # NEW: compute_rolling_6w(), TrendCalculator
├── week_utils.py      # NEW: generate_week_list(), find_latest_week()
└── pipelines.py       # 5 pipelines (ingest_week, normalize_week, aggregate_week, rolling_6w, backfill_range)
```

### New Files

#### `validators.py`

```python
"""Lightweight validators for OTC domain."""
from datetime import date
import re

def validate_week_ending_is_friday(week_ending: str | date) -> date:
    """Validate week_ending is a Friday."""
    ...

def normalize_symbol(symbol: str) -> str:
    """Normalize symbol to uppercase."""
    ...

def validate_tier(tier: str) -> str:
    """Validate tier is recognized value."""
    from market_spine.domains.otc.models import Tier
    return Tier(tier).value  # Raises ValueError if invalid
```

#### `rolling.py`

```python
"""6-week rolling metric calculations."""
from decimal import Decimal
from market_spine.domains.otc.models import VenueVolume, Rolling6Week

def compute_rolling_6w(
    venue_data: list[VenueVolume],
    tier: str,
    week_ending: str,
    rolling_version: str = "v1.0.0"
) -> list[Rolling6Week]:
    """
    Compute 6-week rolling metrics.
    
    Args:
        venue_data: All venue_volume records for 6-week window
        tier: Tier to compute for
        week_ending: End of 6-week window
        rolling_version: Calculation version
    
    Returns:
        List of Rolling6Week metrics (one per symbol)
    """
    ...

class TrendCalculator:
    """Calculate trend direction from time series."""
    
    @staticmethod
    def calculate_trend(volumes: list[int]) -> tuple[str, Decimal]:
        """
        Compare last 2 weeks vs first 2 weeks.
        
        Returns:
            ("UP"|"DOWN"|"FLAT", pct_change)
        """
        ...
```

#### `week_utils.py`

```python
"""Utilities for working with OTC weeks."""
from datetime import date, timedelta

def generate_week_list(
    start_week: str | None = None,
    end_week: str | None = None,
    weeks_back: int | None = None
) -> list[str]:
    """
    Generate list of Friday dates.
    
    Args:
        start_week: ISO date (Friday)
        end_week: ISO date (Friday, inclusive)
        weeks_back: Alternative: N weeks back from today
    
    Returns:
        List of ISO date strings (all Fridays)
    """
    ...

def find_latest_week(conn, tier: str) -> str | None:
    """Find most recent week_ending in otc_symbol_summary."""
    ...

def get_friday_for_date(d: date) -> date:
    """Find the Friday ending the week containing date d."""
    ...
```

#### Updated `models.py`

Add `Rolling6Week`:
```python
@dataclass
class Rolling6Week:
    """6-week rolling metrics for a symbol."""
    week_ending: str  # End of window
    tier: str
    symbol: str
    
    avg_6w_volume: int
    avg_6w_trades: int
    trend_direction: str  # "UP" | "DOWN" | "FLAT"
    trend_pct: Decimal
    weeks_in_window: int  # Actual weeks (may be <6 for new symbols)
    
    rolling_version: str
    execution_id: str
    batch_id: str | None
```

---

## CLI Examples - 6-Week Workflow

### Full Workflow

**Scenario**: Load 6 weeks of NMS Tier 1 data and compute rolling metrics.

```bash
# Initialize database
spine db init

# Backfill 6 weeks
spine run otc.backfill_range \
  -p tier=NMS_TIER_1 \
  -p weeks_back=6

# Output:
# ✓ Pipeline completed successfully!
#   Execution: exec_bf_20260103_150022
#   Batch: backfill_NMS_TIER_1_2025-11-22_2026-01-03_20260103T150022
#   Metrics: {'weeks_processed': 6, 'total_records_ingested': 84, ...}
```

### Single Week Processing

```bash
# Ingest one week
spine run otc.ingest_week \
  -p tier=NMS_TIER_1 \
  -p week_ending=2026-01-03 \
  -p source=file \
  -p file_path=data/finra/week_2026-01-03.csv

# Normalize
spine run otc.normalize_week \
  -p tier=NMS_TIER_1 \
  -p week_ending=2026-01-03

# Aggregate
spine run otc.aggregate_week \
  -p tier=NMS_TIER_1 \
  -p week_ending=2026-01-03
```

### Rolling Metrics

```bash
# Compute rolling for latest week
spine run otc.compute_rolling_6w \
  -p tier=NMS_TIER_1 \
  -p week_ending=latest

# Or specific week
spine run otc.compute_rolling_6w \
  -p tier=NMS_TIER_1 \
  -p week_ending=2026-01-03 \
  -p rolling_version=v1.0.0
```

### Querying Results

```bash
# Interactive shell
spine shell

# In shell:
>>> conn = get_connection()

# View rolling metrics
>>> rows = conn.execute("""
...   SELECT symbol, avg_6w_volume, trend_direction, trend_pct
...   FROM otc_symbol_rolling_6w
...   WHERE tier = 'NMS Tier 1'
...   ORDER BY avg_6w_volume DESC
... """).fetchall()

>>> for row in rows:
...     print(f"{row['symbol']:6} {row['avg_6w_volume']:>12,} {row['trend_direction']:>5} {row['trend_pct']:>7}%")

# Output:
# NVDA   15,200,000  UP    +12.5%
# AAPL   12,450,000  FLAT   +1.2%
# TSLA    8,900,000  DOWN   -5.3%
```

### Reprocessing After Data Correction

```bash
# Week had bad data, re-ingest with corrected file
spine run otc.ingest_week \
  -p tier=NMS_TIER_1 \
  -p week_ending=2025-12-06 \
  -p source=file \
  -p file_path=data/finra/corrected_week_2025-12-06.csv \
  -p force=true

# Re-normalize and aggregate
spine run otc.normalize_week -p tier=NMS_TIER_1 -p week_ending=2025-12-06
spine run otc.aggregate_week -p tier=NMS_TIER_1 -p week_ending=2025-12-06

# Recalculate rolling (uses corrected data)
spine run otc.compute_rolling_6w -p tier=NMS_TIER_1 -p week_ending=latest
```

---

## Test Strategy

### Golden Fixtures

**Location**: `tests/fixtures/otc/golden_6w/`

```
tests/fixtures/otc/golden_6w/
├── week_2025-11-22_NMS_TIER_1.csv (14 records: AAPL, TSLA, NVDA, ...)
├── week_2025-11-29_NMS_TIER_1.csv (14 records)
├── week_2025-12-06_NMS_TIER_1.csv (14 records)
├── week_2025-12-13_NMS_TIER_1.csv (14 records)
├── week_2025-12-20_NMS_TIER_1.csv (14 records)
├── week_2026-01-03_NMS_TIER_1.csv (14 records)
└── expected_results.json (expected aggregates + rolling metrics)
```

**expected_results.json**:
```json
{
  "raw_count": 84,
  "normalized_count": 84,
  "symbol_summaries": 36,
  "venue_shares": 30,
  "rolling_metrics": {
    "AAPL": {
      "avg_6w_volume": 12450000,
      "avg_6w_trades": 8234,
      "trend_direction": "UP",
      "trend_pct": "12.5",
      "weeks_in_window": 6
    },
    ...
  }
}
```

### Test Cases

```python
# tests/test_otc_multi_week.py
import json
import pytest
from pathlib import Path

@pytest.fixture
def golden_fixture_path():
    return Path(__file__).parent / "fixtures" / "otc" / "golden_6w"

def test_full_6_week_workflow(golden_fixture_path):
    """End-to-end test: backfill → validate results."""
    # Reset database
    init_db()
    
    # Backfill
    result = get_dispatcher().submit("otc.backfill_range", {
        "tier": "NMS_TIER_1",
        "start_week": "2025-11-22",
        "end_week": "2026-01-03"
    })
    
    assert result.status == PipelineStatus.COMPLETED
    assert result.metrics["weeks_processed"] == 6
    
    # Load expected results
    expected = json.loads((golden_fixture_path / "expected_results.json").read_text())
    
    # Validate counts
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM otc_raw").fetchone()[0] == expected["raw_count"]
    assert conn.execute("SELECT COUNT(*) FROM otc_venue_volume").fetchone()[0] == expected["normalized_count"]
    
    # Validate rolling metrics for AAPL
    aapl_rolling = conn.execute("""
        SELECT * FROM otc_symbol_rolling_6w 
        WHERE symbol = 'AAPL' AND tier = 'NMS Tier 1'
    """).fetchone()
    
    expected_aapl = expected["rolling_metrics"]["AAPL"]
    assert aapl_rolling["avg_6w_volume"] == expected_aapl["avg_6w_volume"]
    assert aapl_rolling["trend_direction"] == expected_aapl["trend_direction"]

def test_idempotency_backfill():
    """Backfill twice → identical state."""
    # First run
    result1 = get_dispatcher().submit("otc.backfill_range", {
        "tier": "NMS_TIER_1",
        "weeks_back": 6
    })
    
    state1 = capture_database_state()
    
    # Second run
    result2 = get_dispatcher().submit("otc.backfill_range", {
        "tier": "NMS_TIER_1",
        "weeks_back": 6
    })
    
    state2 = capture_database_state()
    
    assert state1["counts"] == state2["counts"]  # Same row counts
    assert result1.execution_id != result2.execution_id  # Different executions
    assert result1.batch_id != result2.batch_id  # Different batches

def test_partial_reprocessing():
    """Reprocess single week → only that week updated."""
    # Initial backfill
    get_dispatcher().submit("otc.backfill_range", {"tier": "NMS_TIER_1", "weeks_back": 6})
    
    # Capture AAPL rolling metric
    conn = get_connection()
    aapl_before = conn.execute("""
        SELECT avg_6w_volume, execution_id 
        FROM otc_symbol_rolling_6w 
        WHERE symbol = 'AAPL'
    """).fetchone()
    
    # Reprocess week 2025-12-06 with different data
    get_dispatcher().submit("otc.ingest_week", {
        "tier": "NMS_TIER_1",
        "week_ending": "2025-12-06",
        "source": "file",
        "file_path": "tests/fixtures/modified_week_2025-12-06.csv",
        "force": True
    })
    get_dispatcher().submit("otc.normalize_week", {"tier": "NMS_TIER_1", "week_ending": "2025-12-06"})
    get_dispatcher().submit("otc.aggregate_week", {"tier": "NMS_TIER_1", "week_ending": "2025-12-06"})
    get_dispatcher().submit("otc.compute_rolling_6w", {"tier": "NMS_TIER_1", "week_ending": "latest"})
    
    # Check AAPL rolling metric changed
    aapl_after = conn.execute("""
        SELECT avg_6w_volume, execution_id 
        FROM otc_symbol_rolling_6w 
        WHERE symbol = 'AAPL'
    """).fetchone()
    
    assert aapl_after["avg_6w_volume"] != aapl_before["avg_6w_volume"]  # Volume changed
    assert aapl_after["execution_id"] != aapl_before["execution_id"]  # New execution

def test_week_validation():
    """Non-Friday week_ending → error."""
    with pytest.raises(ValueError, match="must be a Friday"):
        get_dispatcher().submit("otc.ingest_week", {
            "tier": "NMS_TIER_1",
            "week_ending": "2026-01-03",  # Saturday!
            "source": "file",
            "file_path": "data/file.csv"
        })
```

### Test Execution

```bash
# Run full test suite
pytest tests/test_otc_multi_week.py -v

# Output:
# tests/test_otc_multi_week.py::test_full_6_week_workflow PASSED
# tests/test_otc_multi_week.py::test_idempotency_backfill PASSED
# tests/test_otc_multi_week.py::test_partial_reprocessing PASSED
# tests/test_otc_multi_week.py::test_week_validation PASSED
```

---

## Summary: Real Multi-Week Example Changes

### What Changed

1. **Removed toy "example" domain** → OTC is the primary example
2. **Week-scoped pipelines** → ingest_week, normalize_week, aggregate_week
3. **Rolling analytics** → compute_rolling_6w with trend detection
4. **Orchestration pipeline** → backfill_range synchronously processes N weeks
5. **Execution lineage** → parent_execution_id + batch_id throughout
6. **Idempotency guarantees** → documented and tested

### What Stayed the Same

✅ Synchronous execution only (no async, no workers, no queues)  
✅ SQLite database (no PostgreSQL, no Redis)  
✅ Simple architecture (no microservices, no message bus)  
✅ Decorator-based registration  
✅ Forward compatible (same API for Intermediate/Advanced/Full)  

### Implementation Checklist

**Code Changes**:
- [ ] Add `parent_execution_id`, `batch_id` to `Execution` model
- [ ] Update `Dispatcher.submit()` signature
- [ ] Create `validators.py`, `rolling.py`, `week_utils.py`
- [ ] Refactor `pipelines.py` → 5 new pipelines
- [ ] Update `models.py` → add `Rolling6Week`

**Schema Changes**:
- [ ] Create migration `021_otc_multi_week_support.sql`
- [ ] Add `execution_id`, `batch_id` to existing tables
- [ ] Create `otc_symbol_rolling_6w` table
- [ ] Add indexes for lineage queries

**Documentation Changes**:
- [ ] Update BASIC_TIER_ARCHITECTURE.md with 6-week workflow
- [ ] Add CLI examples showing backfill_range
- [ ] Document idempotency guarantees per pipeline
- [ ] Add "Natural Keys & Idempotency" section

**Testing**:
- [ ] Create golden fixtures (6 weeks of test data)
- [ ] Write end-to-end workflow test
- [ ] Write idempotency test (run backfill twice)
- [ ] Write partial reprocessing test
- [ ] Write validator tests

### Benefits Achieved

**For Basic Tier Users**:
- Learn real temporal data workflows (not toy examples)
- Understand idempotency through 6-week backfill
- See execution lineage in multi-week context

**For Higher Tiers**:
- Same pipeline names/params → easy upgrade path
- Natural keys frozen → stable partition keys for TimescaleDB
- Execution lineage → distributed tracing in Advanced tier
- Idempotency contracts → exactly-once delivery in Full tier

**For Institutional Adoption**:
- Proves platform value: temporal analytics, rolling windows, trend detection
- Demonstrates audit trail: batch_id groups related work
- Shows reprocessing safety: re-run backfill without data corruption

**Example**: `otc.ingest`
- Running with same file twice inserts records once (via record_hash)
- Safe to retry on failure

#### Level 3: State-Idempotent  
Pipeline can be re-run; overwrites previous output with same result.

**Example**: `otc.summarize`
- Re-running with same source data produces same aggregates
- Uses `INSERT OR REPLACE` / `DELETE + INSERT` pattern

#### Level 4: Append-Only
Pipeline never overwrites; each run adds new data.

**Example**: Audit log pipelines (future)
```

**Documentation for OTC Pipelines**:

```markdown
### OTC Pipeline Idempotency Guarantees

| Pipeline | Level | Behavior on Re-run |
|----------|-------|-------------------|
| `otc.ingest` | Input-Idempotent | Duplicate records skipped via `record_hash`. Same file → same inserts. |
| `otc.normalize` | State-Idempotent | Re-processes all unnormalized records. Safe to re-run. |
| `otc.summarize` | State-Idempotent | Recalculates summaries from current `otc_venue_volume`. Uses `DELETE + INSERT`. |

**Critical Invariant**: 
Running the full workflow twice (`ingest → normalize → summarize`) on the same file produces **identical final state**.
```

---

#### 2.2 Add Execution-Level Idempotency Keys

**Purpose**: Enable "run once per logical work item" semantics.

**Change**: Use `logical_key` parameter in Dispatcher:

```python
# In CLI or orchestration
execution = dispatcher.submit(
    "otc.ingest",
    params={"file_path": "data/file.csv"},
    logical_key=f"otc.ingest::{file_hash}",  # Prevents duplicate processing
    batch_id=batch_id
)
```

**Implementation (Basic Tier)**:

```python
# In dispatcher.py
def submit(self, ..., logical_key: str | None = None) -> Execution:
    if logical_key:
        # Check if execution with this logical_key already completed
        existing = conn.execute(
            "SELECT execution_id FROM executions WHERE logical_key = ? AND status = 'COMPLETED'",
            (logical_key,)
        ).fetchone()
        
        if existing:
            # Return existing execution (no-op)
            return self._load_execution(existing["execution_id"])
    
    # Proceed with execution...
```

**Why This Matters**:
- **Advanced tier**: Prevents duplicate Celery task submissions
- **Full tier**: Becomes event deduplication key in event store
- **Disaster recovery**: "Resume from last successful execution"

---

## 3. OTC Domain Correctness

### Current State

**What Works**:
- Natural keys exist: `(week_ending, tier, symbol, mpid)` for venue volume
- Database constraints enforce uniqueness
- Tier enum prevents invalid tier values

**What's Missing**:
- **No validation that week_ending is actually a Friday** (OTC weeks end Fridays)
- **No enforcement that tier is a recognized value** before database insert
- **No symbol normalization** (is "AAPL" the same as "aapl"?)

### Semantic Improvements

#### 3.1 Freeze Temporal Semantics

**Purpose**: Establish `week_ending` as a **first-class temporal type** with validation.

**Change**: Create `WeekEnding` value object:

```python
# In domains/otc/models.py
from datetime import date, timedelta

class WeekEnding:
    """OTC week ending date (always a Friday in ISO format)."""
    
    def __init__(self, value: str | date):
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
        else:
            parsed = value
        
        # Validate it's a Friday (weekday() == 4)
        if parsed.weekday() != 4:
            raise ValueError(f"Week ending must be a Friday, got {parsed} ({parsed.strftime('%A')})")
        
        self._value = parsed
    
    def __str__(self) -> str:
        return self._value.isoformat()
    
    @property
    def date(self) -> date:
        return self._value
    
    @classmethod
    def from_any_date(cls, d: date) -> "WeekEnding":
        """Find the Friday ending the week containing date d."""
        days_until_friday = (4 - d.weekday()) % 7
        friday = d + timedelta(days=days_until_friday)
        return cls(friday)
```

**Usage**:

```python
# In parser.py
week_ending = WeekEnding(row["WeekEnding"])  # Validates it's a Friday

# In calculations.py
def compute_symbol_summaries(venue_data: list[VenueVolume]) -> list[SymbolSummary]:
    # Group by WeekEnding object, not string
    by_week = defaultdict(list)
    for vv in venue_data:
        week = WeekEnding(vv.week_ending)  # Enforces domain invariant
        by_week[week].append(vv)
```

**Why This Matters**:
- **Data quality**: Prevents "2026-01-03" (Saturday) from entering system
- **Canonical form**: All code uses validated type, not strings
- **Evolution**: When adding "month ending" aggregates, same pattern applies
- **Event sourcing**: Week boundaries are event stream partition keys

---

#### 3.2 Enforce Symbol Normalization

**Purpose**: Prevent "AAPL" vs "aapl" from creating duplicate summaries.

**Change**: Add `Symbol` value object:

```python
class Symbol:
    """Normalized symbol identifier."""
    
    def __init__(self, value: str):
        # Normalize: uppercase, strip whitespace
        normalized = value.strip().upper()
        
        # Validate: alphanumeric + common chars only
        if not re.match(r"^[A-Z0-9.\-]+$", normalized):
            raise ValueError(f"Invalid symbol format: {value}")
        
        self._value = normalized
    
    def __str__(self) -> str:
        return self._value
    
    def __eq__(self, other):
        return isinstance(other, Symbol) and self._value == other._value
    
    def __hash__(self):
        return hash(self._value)
```

**Why This Matters**:
- **Aggregation correctness**: "aapl" and "AAPL" count as same symbol
- **Join keys**: When joining with reference data, symbols match
- **Advanced tier**: Symbol becomes entity ID in master data service

---

#### 3.3 Document Natural Key Invariants

**Purpose**: Make natural keys **explicit domain contracts**, not implementation details.

**Documentation Addition**:

```markdown
### OTC Domain Natural Keys (Immutable)

These composite keys are **domain invariants** frozen in Basic tier:

#### Venue Volume Natural Key
```python
(week_ending: WeekEnding, tier: Tier, symbol: Symbol, mpid: str)
```

**Invariants**:
- `week_ending` MUST be a Friday
- `tier` MUST be a valid `Tier` enum value
- `symbol` MUST be uppercase normalized
- `mpid` MUST be exactly 4 characters

**Evolution Guarantees**:
- These four fields will **never change** across all tiers
- Advanced tier: Becomes composite partition key in TimescaleDB
- Full tier: Becomes event stream routing key

#### Symbol Summary Natural Key
```python
(week_ending: WeekEnding, tier: Tier, symbol: Symbol)
```

#### Venue Market Share Natural Key
```python
(week_ending: WeekEnding, mpid: str)
```

**Why Freeze Early?**
- Event sourcing relies on **stable partition keys**
- Microservices need **agreed entity identifiers**
- Time-series databases require **immutable hypertable keys**
```

---

## 4. Calculation Evolution

### Current State

**What Works**:
- Calculations are deterministic (same input → same output)
- Logic is isolated in `calculations.py`

**What's Missing**:
- **No versioning** of calculation logic
- **No way to track** which version of `compute_venue_shares()` produced a result
- **No recalculation strategy** when logic changes

### Semantic Improvements

#### 4.1 Add Calculation Version Metadata

**Purpose**: Track which version of aggregation logic produced each result.

**Change**: Add `calculation_version` to summary tables:

```sql
-- In 020_otc_tables.sql
CREATE TABLE otc_symbol_summary (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    
    calculation_version TEXT NOT NULL,  -- NEW: e.g., "v1.0.0"
    calculated_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, calculation_version)  -- Allow multiple versions
);
```

**In calculations.py**:

```python
CALCULATION_VERSION = "v1.0.0"  # Increment when logic changes

def compute_symbol_summaries(...) -> list[SymbolSummary]:
    """
    Compute symbol summaries.
    
    Version: v1.0.0
    Changes from v0.9.0:
    - Added avg_trade_size calculation
    - Changed venue_count to exclude venues with <100 trades
    """
    summaries = []
    for symbol, records in grouped_data:
        summary = SymbolSummary(
            # ... calculations ...
            calculation_version=CALCULATION_VERSION
        )
        summaries.append(summary)
    return summaries
```

**Why This Matters**:
- **Auditing**: "Show me all summaries calculated with old logic"
- **Migration**: "Recalculate Q4 2025 data with v1.1.0 logic"
- **A/B Testing**: Run v1 and v2 logic in parallel, compare results
- **Regulatory**: "This report used calculation version certified by compliance"

---

#### 4.2 Document Calculation Invariants

**Purpose**: Distinguish **semantic changes** (require reprocessing) from **performance optimizations** (don't change results).

**Documentation Addition**:

```markdown
### Calculation Evolution Policy

#### Semantic Versioning for Calculations

**Version Format**: `vMAJOR.MINOR.PATCH`

- **MAJOR**: Changes result values (require full reprocessing)
  - Example: Changing market share from simple average to volume-weighted
  - Example: Excluding certain tiers from aggregates
  
- **MINOR**: Adds new metrics without changing existing ones
  - Example: Adding `median_trade_size` alongside `avg_trade_size`
  - Example: Adding new summary table
  
- **PATCH**: Performance optimizations, no semantic changes
  - Example: Using bulk insert instead of row-by-row
  - Example: SQL query optimization

#### Current OTC Calculation Versions

| Function | Version | Status | Notes |
|----------|---------|--------|-------|
| `compute_symbol_summaries()` | v1.0.0 | Active | Initial implementation |
| `compute_venue_shares()` | v1.0.0 | Active | Market share = total_volume / sum(all_volumes) |

#### Reprocessing Strategy

When MAJOR version changes:

```bash
# 1. Update calculation version constant
# 2. Re-run summarize for affected periods
spine run otc.summarize -p reprocess_weeks=2025-Q4 -p calc_version=v2.0.0

# 3. Query by version
SELECT * FROM otc_symbol_summary WHERE calculation_version = 'v2.0.0'
```

**Forward Compatibility**:
- **Advanced tier**: Celery task versioning matches calculation versions
- **Full tier**: Calculation versions become event metadata
```

---

## 5. Additional Hardening Recommendations

### 5.1 Add Data Quality Assertions

**Purpose**: Fail fast on domain invariant violations.

**Change**: Add validation to pipelines:

```python
# In otc.summarize pipeline
def run(self) -> PipelineResult:
    # ... compute summaries ...
    
    # ASSERTION: Market shares must sum to ~100%
    total_share = sum(Decimal(v.market_share_pct) for v in venue_shares)
    if not (Decimal("99.99") <= total_share <= Decimal("100.01")):
        return PipelineResult(
            status=PipelineStatus.FAILED,
            error=f"Market shares sum to {total_share}%, expected 100%",
            # ... other fields ...
        )
    
    # ASSERTION: No negative volumes
    negative_volumes = [s for s in symbol_summaries if s.total_volume < 0]
    if negative_volumes:
        return PipelineResult(
            status=PipelineStatus.FAILED,
            error=f"Found {len(negative_volumes)} symbols with negative volume",
            # ... other fields ...
        )
```

---

### 5.2 Add Schema Migration Tests

**Purpose**: Ensure migrations are idempotent and reversible.

**Documentation Addition**:

```markdown
### Migration Testing Policy

Every migration MUST:

1. **Be idempotent**: Running twice produces same result
   ```sql
   -- Good: Uses IF NOT EXISTS
   CREATE TABLE IF NOT EXISTS otc_raw (...);
   
   -- Bad: Fails on second run
   CREATE TABLE otc_raw (...);
   ```

2. **Have a rollback script**: `migrations/020_otc_tables_rollback.sql`
   ```sql
   DROP TABLE IF EXISTS otc_venue_share;
   DROP TABLE IF EXISTS otc_symbol_summary;
   DROP TABLE IF EXISTS otc_venue_volume;
   DROP TABLE IF EXISTS otc_raw;
   ```

3. **Preserve data**: Additive changes preferred over destructive
   ```sql
   -- Good: Add column with default
   ALTER TABLE otc_raw ADD COLUMN calculation_version TEXT DEFAULT 'v1.0.0';
   
   -- Bad: Drop column (data loss)
   ALTER TABLE otc_raw DROP COLUMN source_file;
   ```

**Evolution**:
- **Intermediate**: Add migration validation in CI
- **Advanced**: Use Alembic/Flyway for complex migrations
- **Full**: Event store is append-only (no schema migrations)
```

---

## 6. Summary of Proposed Changes

### Documentation Updates (No Code Changes Required)

1. **Add "Execution Lineage" section** explaining parent/child relationships
2. **Add "Batch Identity Design" section** explaining batch_id semantics
3. **Add "Idempotency Levels" section** formalizing replay contracts
4. **Add "Natural Key Invariants" section** freezing OTC domain keys
5. **Add "Calculation Evolution Policy" section** for versioning strategy
6. **Add "Migration Testing Policy" section** for schema evolution rules

### Light Structural Tweaks (Minimal Code Changes)

1. **Add `parent_execution_id` and `batch_id` to Execution model**
   - Update `Dispatcher.submit()` signature
   - Update `executions` table schema
   
2. **Add `calculation_version` to summary tables**
   - Update `otc_symbol_summary`, `otc_venue_share` schemas
   - Add `CALCULATION_VERSION` constant to `calculations.py`

3. **Add value objects for domain types** (optional for Basic, recommended for Intermediate)
   - `WeekEnding` class with Friday validation
   - `Symbol` class with normalization
   - `Tier` enum (already exists)

4. **Add data quality assertions to pipelines**
   - Market share sum validation
   - Negative volume detection
   - Natural key uniqueness checks

### What NOT to Change

❌ Do NOT add async execution  
❌ Do NOT split Dispatcher/Runner layers  
❌ Do NOT introduce message queues  
❌ Do NOT add ORM or complex repository patterns  
❌ Do NOT change synchronous execution model  

---

## 7. Benefits of These Improvements

### For Basic Tier Users (Today)

1. **Better error messages**: "Week ending must be a Friday" vs "Invalid date"
2. **Safer re-runs**: Clear idempotency guarantees prevent accidental data corruption
3. **Easier debugging**: Execution lineage shows "why this data exists"
4. **Data quality**: Assertions catch calculation bugs early

### For Evolution to Higher Tiers (Tomorrow)

1. **Execution lineage** → Distributed tracing in Advanced tier
2. **Batch identity** → Saga identifiers in Full tier
3. **Natural keys** → Event stream partition keys in Full tier
4. **Calculation versions** → A/B testing framework in Advanced tier
5. **Idempotency contracts** → Exactly-once delivery guarantees in Full tier

### For Institutional Compliance (Always)

1. **Audit trail**: "Which execution produced this regulatory report?"
2. **Reproducibility**: "Re-run Q3 2025 with original calculation logic"
3. **Certification**: "Market share calculations are version v1.0.0, certified by compliance"
4. **Data lineage**: "This summary came from batch X, ingested at timestamp Y"

---

## Conclusion

Market Spine Basic is **architecturally sound** for its purpose: teaching core concepts with minimal complexity.

These improvements add **semantic precision** without adding **structural complexity**:

- Value objects enforce domain invariants at the type level
- Execution lineage provides provenance without changing the execution model
- Calculation versioning enables evolution without breaking existing code
- Idempotency contracts make implicit behaviors explicit

**The goal**: Basic tier graduates from "learning framework" to "foundation tier for institutional data platforms."

When a data engineer learns Market Spine on Basic tier, they should internalize:

✅ Natural keys are domain invariants, not implementation details  
✅ Execution identity enables reproducibility and auditing  
✅ Calculations evolve; version them like code  
✅ Idempotency is a contract, not an accident  

These lessons transfer directly to Advanced/Full tiers, where the stakes (regulatory compliance, multi-billion dollar trades, real-time risk systems) demand semantic correctness.

**Recommendation**: Implement documentation updates immediately; defer code changes to Intermediate tier (where they're easier to test with PostgreSQL and async patterns).
