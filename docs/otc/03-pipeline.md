# OTC Pipeline Stages

## Overview

```
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│  INGEST  │ →  │  NORMALIZE  │ →  │   COMPUTE   │
│          │    │             │    │             │
│ Parse    │    │ Clean &     │    │ Summaries & │
│ Store    │    │ Validate    │    │ Analytics   │
│ Raw      │    │             │    │             │
└──────────┘    └─────────────┘    └─────────────┘
```

---

## Stage 1: Ingest (`ingest_otc_weekly`)

**Purpose:** Parse FINRA files, store raw data with lineage.

### Inputs/Outputs

```
Inputs:
  - week_ending: date
  - tier: str ("T1", "T2", or "OTC")
  - file_path: Path

Outputs:
  - capture_id: str (ULID)
  - record_count: int
  - symbols_count: int
  - venues_count: int
```

### Pre-Store Checks

| Check | Severity | Action |
|-------|----------|--------|
| File exists | FAIL | Abort immediately |
| Pipe-delimited | FAIL | Try CSV fallback, then abort |
| All 8 columns present | FAIL | Abort with details |
| week_ending matches | FAIL | Reject if >1 day mismatch |
| Record count reasonable | WARN | T1 <1000 or T2 <5000 |
| Known MPIDs present | WARN | Log missing venues |

### Idempotency

```python
# Check for existing data before insert
existing = await db.fetch_one("""
    SELECT capture_id, COUNT(*) as cnt
    FROM otc.raw_weekly
    WHERE last_update_date = $1 AND tier_description LIKE $2
    GROUP BY capture_id
    ORDER BY ingested_at DESC LIMIT 1
""", week_ending, f"%{tier}%")

if existing:
    # Compare checksum - skip if unchanged
    new_checksum = compute_file_checksum(file_path)
    if new_checksum == existing.checksum:
        return {"status": "skipped", "capture_id": existing.capture_id}
    # Otherwise store new version (correction)
```

---

## Stage 2: Normalize (`normalize_otc_weekly`)

**Purpose:** Clean, validate, and standardize raw data.

### Inputs/Outputs

```
Inputs:
  - capture_id: str

Outputs:
  - normalized_count: int
  - rejected_count: int
  - warnings: list
```

### Transformations

| Field | Transformation |
|-------|----------------|
| `issue_symbol_identifier` → `symbol` | Uppercase, trim |
| `tier_description` → `tier` | "NMS Tier 1" → "T1" |
| `last_update_date` → `week_ending` | Direct copy |
| `total_weekly_share_quantity` → `share_volume` | Validate ≥ 0 |
| `total_weekly_trade_count` → `trade_count` | Validate ≥ 0 |
| (computed) `avg_trade_size` | `share_volume / trade_count` |

### Validation

```python
class WeeklyVolumeValidator:
    def validate(self, row: FinraOtcRawRow) -> ValidationResult:
        errors = []
        warnings = []
        
        # Hard failures
        if not row.issue_symbol_identifier:
            errors.append("missing_symbol")
        if row.total_weekly_share_quantity < 0:
            errors.append("negative_volume")
        if row.total_weekly_trade_count < 0:
            errors.append("negative_trades")
        if len(row.mpid) < 3:
            errors.append("invalid_mpid")
        
        # Soft warnings
        if row.total_weekly_share_quantity == 0:
            warnings.append("zero_volume")
        if row.total_weekly_trade_count == 0 and row.total_weekly_share_quantity > 0:
            warnings.append("volume_without_trades")
        
        avg = row.avg_trade_size or 0
        if avg > 100_000:
            warnings.append("unusually_large_avg_trade")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
```

---

## Stage 3: Compute Summaries (`compute_weekly_summary`)

**Purpose:** Aggregate venue data into symbol and venue summaries.

### Inputs/Outputs

```
Inputs:
  - week_ending: date

Outputs:
  - symbols_computed: int
  - venues_computed: int
```

### Readiness Check

```python
async def check_readiness(self, week_ending: date) -> ReadinessResult:
    venue_count = await self.db.fetch_val("""
        SELECT COUNT(DISTINCT mpid) FROM otc.venue_volume
        WHERE week_ending = $1
    """, week_ending)
    
    if venue_count == 0:
        return ReadinessResult(ready=False, reason="no_data")
    
    if venue_count < 5:
        return ReadinessResult(ready=True, 
            warnings=[f"Only {venue_count} venues"])
    
    return ReadinessResult(ready=True)
```

### Symbol Summary SQL

```sql
INSERT INTO otc.symbol_weekly_summary (
    execution_id, week_ending, symbol,
    total_volume, total_trades, venue_count, avg_trade_size,
    top_venue, top_venue_volume, top_venue_pct,
    data_quality_flags, computed_at
)
SELECT
    $1 as execution_id,
    week_ending,
    symbol,
    
    SUM(share_volume) as total_volume,
    SUM(trade_count) as total_trades,
    COUNT(DISTINCT mpid) as venue_count,
    SUM(share_volume)::numeric / NULLIF(SUM(trade_count), 0) as avg_trade_size,
    
    (ARRAY_AGG(mpid ORDER BY share_volume DESC))[1] as top_venue,
    MAX(share_volume) as top_venue_volume,
    MAX(share_volume)::numeric / NULLIF(SUM(share_volume), 0) * 100 as top_venue_pct,
    
    $2::jsonb as data_quality_flags,
    now()
    
FROM otc.venue_volume
WHERE week_ending = $3
GROUP BY week_ending, symbol;
```

### Venue Market Share SQL

```sql
WITH venue_totals AS (
    SELECT
        week_ending,
        mpid,
        SUM(share_volume) as venue_volume,
        SUM(trade_count) as venue_trades,
        COUNT(DISTINCT symbol) as symbol_count
    FROM otc.venue_volume
    WHERE week_ending = $1
    GROUP BY week_ending, mpid
),
week_total AS (
    SELECT SUM(share_volume) as total FROM venue_totals
)
INSERT INTO otc.venue_market_share (
    execution_id, week_ending, mpid,
    total_volume, total_trades, symbol_count,
    market_share_pct, rank, computed_at
)
SELECT
    $2 as execution_id,
    v.week_ending,
    v.mpid,
    v.venue_volume,
    v.venue_trades,
    v.symbol_count,
    v.venue_volume::numeric / NULLIF(w.total, 0) * 100,
    RANK() OVER (ORDER BY v.venue_volume DESC),
    now()
FROM venue_totals v, week_total w;
```

---

## Scheduling

| Job | Trigger | Description |
|-----|---------|-------------|
| `ingest_t1` | Wednesday 6am (T1 publication day + 2 weeks) | Ingest T1 files |
| `ingest_t2` | Wednesday 6am (T2 publication day + 4 weeks) | Ingest T2 files |
| `normalize` | After ingest completes | Clean and validate |
| `compute` | After normalize completes | Generate summaries |
| `rolling_avg` | After compute completes | 6-week rolling averages |
