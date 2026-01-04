# OTC Weekly Transparency Domain

> **Location**: `src/spine/domains/otc/`  
> **Purpose**: FINRA OTC weekly transparency data processing

---

## Overview

The OTC domain processes FINRA's weekly OTC transparency reports, computing:
- Per-symbol volume summaries
- Per-venue market shares
- 6-week rolling metrics and trends

This is a **thin domain** built on `spine.core` primitives.

---

## File Structure

```
spine/domains/otc/
├── __init__.py       # Package init, registers pipelines
├── schema.py         # Tables, stages, tiers, natural keys (40 LOC)
├── connector.py      # Parse FINRA PSV files (80 LOC)
├── normalizer.py     # Validate records (100 LOC)
├── calculations.py   # Pure aggregation functions (150 LOC)
└── pipelines.py      # Orchestration (350 LOC)
```

**Total: ~720 lines** (down from 2000+)

---

## FINRA File Format

FINRA publishes pipe-delimited (PSV) files:

```
tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc|Citadel Securities|CDRG|15000000|85000|2025-12-26
NMS Tier 1|AAPL|Apple Inc|Virtu Americas|NITE|12000000|62000|2025-12-26
```

### Simplified Test Format

For testing, use simplified PSV:

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-26|NMS_TIER_1|AAPL|NITE|1500000|8500
2025-12-26|NMS_TIER_1|AAPL|CITD|1200000|6200
```

---

## Tables

### Domain Data Tables (OTC-specific)

| Table | Natural Key | Purpose |
|-------|-------------|---------|
| `otc_raw` | `(week_ending, tier, symbol, mpid, record_hash)` | Raw ingested data |
| `otc_venue_volume` | `(week_ending, tier, symbol, mpid)` | Normalized venue data |
| `otc_symbol_summary` | `(week_ending, tier, symbol)` | Per-symbol aggregates |
| `otc_venue_share` | `(week_ending, tier, mpid)` | Venue market shares |
| `otc_symbol_rolling_6w` | `(week_ending, tier, symbol)` | Rolling metrics |

### Core Infrastructure Tables (shared)

OTC uses **shared core tables** with `domain="otc"`:

| Table | Partition Key | Purpose |
|-------|---------------|---------|
| `core_manifest` | `{"week_ending": ..., "tier": ...}` | Workflow tracking |
| `core_rejects` | `{"week_ending": ..., "tier": ...}` | Validation failures |
| `core_quality` | `{"week_ending": ..., "tier": ...}` | Quality checks |

**Note**: OTC does NOT define its own manifest/rejects/quality tables.

---

## Tiers

```python
class Tier(str, Enum):
    NMS_TIER_1 = "NMS_TIER_1"  # S&P 500, Russell 1000, high volume
    NMS_TIER_2 = "NMS_TIER_2"  # Other NMS stocks
    OTC = "OTC"                # Non-NMS stocks
```

---

## Workflow Stages

```
PENDING → INGESTED → NORMALIZED → AGGREGATED → ROLLING → SNAPSHOT
```

Each week/tier progresses through these stages.

---

## Pipelines

### `otc.ingest_week`
Ingest a FINRA file for one week.

```bash
spine run otc.ingest_week \
  -p week_ending=2025-12-26 \
  -p tier=NMS_TIER_1 \
  -p file_path=data/week_2025-12-26.psv
```

### `otc.normalize_week`
Validate and normalize raw records.

```bash
spine run otc.normalize_week \
  -p week_ending=2025-12-26 \
  -p tier=NMS_TIER_1
```

### `otc.aggregate_week`
Compute symbol summaries and venue shares.

```bash
spine run otc.aggregate_week \
  -p week_ending=2025-12-26 \
  -p tier=NMS_TIER_1
```

### `otc.compute_rolling`
Compute 6-week rolling metrics.

```bash
spine run otc.compute_rolling \
  -p week_ending=2025-12-26 \
  -p tier=NMS_TIER_1
```

### `otc.backfill_range`
Orchestrate full multi-week backfill.

```bash
spine run otc.backfill_range \
  -p tier=NMS_TIER_1 \
  -p weeks_back=6 \
  -p source_dir=data/fixtures/otc
```

---

## Running a Backfill

### 1. Prepare Data Files

```
data/fixtures/otc/
├── week_2025-11-21.psv
├── week_2025-11-28.psv
├── week_2025-12-05.psv
├── week_2025-12-12.psv
├── week_2025-12-19.psv
└── week_2025-12-26.psv
```

### 2. Run Backfill

```bash
spine run otc.backfill_range \
  -p tier=NMS_TIER_1 \
  -p weeks_back=6 \
  -p source_dir=data/fixtures/otc
```

### 3. Verify Results

```sql
-- Check manifest
SELECT week_ending, stage FROM otc_week_manifest 
WHERE tier = 'NMS_TIER_1' ORDER BY week_ending;

-- Check summaries
SELECT symbol, total_volume FROM otc_symbol_summary
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1';

-- Check rolling
SELECT symbol, avg_volume, trend_direction, is_complete
FROM otc_symbol_rolling_6w
WHERE week_ending = '2025-12-26';

-- Check rejects
SELECT reason_code, COUNT(*) FROM otc_rejects GROUP BY reason_code;
```

---

## Validation Rules

### Symbol
- Starts with letter
- Alphanumeric + dots/hyphens
- Max 10 characters
- Example: `AAPL`, `BRK.A`

### MPID
- Exactly 4 alphanumeric characters
- Example: `NITE`, `CITD`

### Volume/Trades
- Must be non-negative
- Zero volume allowed (unless `reject_zero_volume=True`)

### Reject Codes

| Code | Description |
|------|-------------|
| `INVALID_SYMBOL` | Symbol doesn't match pattern |
| `INVALID_MPID` | MPID not 4 alphanumeric chars |
| `NEGATIVE_VOLUME` | Volume < 0 |
| `NEGATIVE_TRADES` | Trade count < 0 |
| `ZERO_VOLUME` | Volume = 0 (if strict mode) |
| `DUPLICATE_KEY` | Duplicate natural key in batch |

---

## Calculations

All calculations are in `calculations.py` as **pure functions**:

```python
# Symbol summaries
summaries = compute_symbol_summaries(venue_records)

# Venue market shares
shares = compute_venue_shares(venue_records, tier)

# Rolling metrics
rolling = compute_rolling_metrics(summaries, as_of_week, tier, symbol)
```

### Market Share

```
market_share_pct = (venue_volume / tier_total_volume) * 100
```

### Trend

```
first_2w_avg = average of first 2 weeks
last_2w_avg = average of last 2 weeks
trend_pct = ((last_2w_avg - first_2w_avg) / first_2w_avg) * 100

if trend_pct > 5%: UP
if trend_pct < -5%: DOWN
else: FLAT
```

---

## Extending OTC

To add a new calculation (e.g., `liquidity_score`):

### 1. Add Pure Function

```python
# calculations.py

def compute_liquidity_score(summary: SymbolSummary) -> Decimal:
    """Compute liquidity score based on volume and venue count."""
    if summary.venue_count == 0:
        return Decimal(0)
    
    # Example formula
    return (Decimal(summary.total_volume) / Decimal(summary.venue_count)).quantize(
        Decimal("0.01")
    )
```

### 2. Call from Pipeline

```python
# pipelines.py, in AggregateWeekPipeline

for s in summaries:
    s.liquidity_score = compute_liquidity_score(s)
    # ... write to DB with new column
```

### 3. Add Column to Schema

```sql
ALTER TABLE otc_symbol_summary ADD COLUMN liquidity_score TEXT;
```

**That's it.** No new manifest, no new reject handling, no new primitives.

---

## Quality Checks

Built-in quality checks:

| Check | Category | Pass Condition |
|-------|----------|----------------|
| `market_share_sum` | BUSINESS_RULE | Sum between 99.9% and 100.1% |

Add custom checks:

```python
def check_min_symbols(ctx: dict) -> QualityResult:
    count = len(ctx["summaries"])
    if count >= 10:
        return QualityResult(QualityStatus.PASS, f"{count} symbols", count, 10)
    return QualityResult(QualityStatus.WARN, f"Only {count} symbols", count, 10)

quality.add(QualityCheck("min_symbols", QualityCategory.COMPLETENESS, check_min_symbols))
```
