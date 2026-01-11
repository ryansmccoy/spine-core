# Pipeline Reference

This document provides detailed documentation for each FINRA OTC Transparency pipeline.

## Pipeline Hierarchy

```
finra.otc_transparency.backfill_range (orchestrator)
    │
    ├── finra.otc_transparency.ingest_week
    │       │
    │       └── finra.otc_transparency.normalize_week
    │               │
    │               └── finra.otc_transparency.aggregate_week
    │
    └── finra.otc_transparency.compute_rolling
```

## Pipeline Details

---

### finra.otc_transparency.ingest_week

**Purpose**: Parse and load raw FINRA PSV file into the database.

**Layer**: Bronze (raw data)

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | ✅ | Path to PSV file |
| `tier` | enum | ❌ | `NMS_TIER_1`, `NMS_TIER_2`, or `OTC` |
| `week_ending` | date | ❌ | Override for business time |
| `file_date` | date | ❌ | Override for publication date |
| `force` | bool | ❌ | Re-ingest even if already done |
| `batch_id` | string | ❌ | Explicit batch identifier |

**Date Inference**:
- If `tier` not specified, attempts to detect from filename
- If `week_ending` not specified, derives from file date

**Output**: Records in `otc_raw` table

**Example**:
```bash
# Basic usage
uv run spine run finra.otc_transparency.ingest_week \
    --file-path data/finra_otc_weekly_tier1_20251222.psv \
    --tier NMS_TIER_1

# With explicit date override
uv run spine run finra.otc_transparency.ingest_week \
    --file-path data/manual.psv \
    --tier NMS_TIER_1 \
    --week-ending 2025-12-19

# Force re-ingest
uv run spine run finra.otc_transparency.ingest_week \
    --file-path data/tier1.psv \
    --tier NMS_TIER_1 \
    --force
```

**Idempotency**: Skips if already ingested (unless `--force`)

---

### finra.otc_transparency.normalize_week

**Purpose**: Validate and clean raw records.

**Layer**: Silver (validated data)

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_ending` | date | ✅ | Business time (Friday) |
| `tier` | enum | ✅ | `NMS_TIER_1`, `NMS_TIER_2`, or `OTC` |
| `capture_id` | string | ❌ | Specific capture to normalize |
| `force` | bool | ❌ | Re-normalize even if done |
| `batch_id` | string | ❌ | Explicit batch identifier |

**Validation Rules**:
- Valid tier enumeration
- Non-empty symbol
- Non-empty MPID
- Non-negative volume/trades
- Rejects zero-volume records

**Output**: 
- Valid records → `otc_venue_volume` table
- Invalid records → `core_rejects` table

**Example**:
```bash
uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-19 \
    --tier NMS_TIER_1
```

**Idempotency**: Deletes and replaces existing normalized data for the capture

---

### finra.otc_transparency.aggregate_week

**Purpose**: Compute symbol-level aggregates from venue-level data.

**Layer**: Gold (analytics-ready)

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_ending` | date | ✅ | Business time (Friday) |
| `tier` | enum | ✅ | `NMS_TIER_1`, `NMS_TIER_2`, or `OTC` |
| `capture_id` | string | ❌ | Specific capture to aggregate |
| `force` | bool | ❌ | Re-aggregate even if done |
| `batch_id` | string | ❌ | Explicit batch identifier |

**Computations**:
- `total_volume`: Sum of shares across all venues
- `total_trades`: Sum of trades across all venues
- `venue_count`: Count of distinct MPIDs
- `avg_trade_size`: `total_volume / total_trades`

**Output**: Records in `otc_symbol_summary` table

**Example**:
```bash
uv run spine run finra.otc_transparency.aggregate_week \
    --week-ending 2025-12-19 \
    --tier NMS_TIER_1
```

**Idempotency**: Deletes and replaces existing aggregates for the capture

---

### finra.otc_transparency.compute_rolling

**Purpose**: Compute rolling window metrics across weeks.

**Layer**: Gold (analytics-ready)

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_ending` | date | ✅ | End of rolling window |
| `tier` | enum | ✅ | `NMS_TIER_1`, `NMS_TIER_2`, or `OTC` |
| `force` | bool | ❌ | Re-compute even if done |
| `batch_id` | string | ❌ | Explicit batch identifier |

**Computations** (default 6-week window):
- `avg_volume`: Average weekly volume
- `avg_trades`: Average weekly trades
- `min_volume` / `max_volume`: Range
- `trend_direction`: `UP`, `DOWN`, or `FLAT`
- `trend_pct`: Percentage change first-to-last week

**Output**: Records in `otc_rolling` table

**Example**:
```bash
uv run spine run finra.otc_transparency.compute_rolling \
    --week-ending 2025-12-19 \
    --tier NMS_TIER_1
```

**Note**: Uses latest capture per historical week for calculations

---

### finra.otc_transparency.backfill_range

**Purpose**: Orchestrate multi-week data processing.

**Layer**: Meta (orchestrator)

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tier` | enum | ✅ | `NMS_TIER_1`, `NMS_TIER_2`, or `OTC` |
| `weeks_back` | int | ❌ | Number of weeks (default: 6) |
| `source_dir` | path | ❌ | Directory with PSV files |
| `file_pattern` | string | ❌ | Filename pattern with `{week}` |
| `force` | bool | ❌ | Force reprocess all weeks |

**Workflow**:
1. Generate list of weeks to process
2. For each week: ingest → normalize → aggregate
3. Compute rolling for latest week

**Example**:
```bash
# Process last 6 weeks
uv run spine run finra.otc_transparency.backfill_range \
    --tier NMS_TIER_1 \
    --weeks-back 6 \
    --source-dir data/finra/tier1

# Force reprocess
uv run spine run finra.otc_transparency.backfill_range \
    --tier NMS_TIER_1 \
    --force
```

---

## Manifest Stages

Pipelines track progress through stages in `core_manifest`:

| Stage | Pipeline | Description |
|-------|----------|-------------|
| `INGESTED` | ingest_week | Raw data loaded |
| `NORMALIZED` | normalize_week | Data validated |
| `AGGREGATED` | aggregate_week | Summaries computed |
| `ROLLING` | compute_rolling | Rolling metrics done |

Check manifest state:
```sql
SELECT * FROM core_manifest 
WHERE domain = 'finra_otc_transparency'
ORDER BY week_ending DESC, tier;
```

---

## Error Handling

### Missing Raw Data
```
ERROR: normalize.no_raw_data - No raw data found for this week
```
**Solution**: Run `ingest_week` first

### Invalid Tier
```
ERROR: ValueError - Tier not specified and could not be detected
```
**Solution**: Add explicit `--tier` parameter

### File Not Found
```
ERROR: Cannot determine dates for /path/to/file
```
**Solution**: Check file path and ensure file exists

---

## Python API

Pipelines can also be invoked programmatically:

```python
from spine.domains.finra.otc_transparency.pipelines import (
    IngestWeekPipeline,
    NormalizeWeekPipeline,
    AggregateWeekPipeline,
)

# Run ingest
result = IngestWeekPipeline({
    "file_path": "data/tier1.psv",
    "tier": "NMS_TIER_1",
    "week_ending": "2025-12-19",
}).run()

print(f"Ingested {result.metrics['records']} records")
```
