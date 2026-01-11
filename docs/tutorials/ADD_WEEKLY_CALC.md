# Tutorial: Add a Weekly Calculation

> **Goal**: Add `liquidity_score_v1` to OTC domain  
> **Time**: 15 minutes  
> **Changes**: 2 files

---

## Background

You want to add a new metric to the OTC weekly summaries. The metric is:

```
liquidity_score = total_volume / venue_count
```

This measures how much volume is concentrated vs distributed across venues.

---

## Step 1: Add Pure Function

Open `src/spine/domains/otc/calculations.py` and add:

```python
from decimal import Decimal, ROUND_HALF_UP

def compute_liquidity_score(
    total_volume: int,
    venue_count: int,
    version: str = "v1"
) -> Decimal:
    """
    Compute liquidity score for a symbol.
    
    Version 1: Simple ratio of volume to venue count.
    Higher score = more concentrated liquidity.
    
    Args:
        total_volume: Total shares traded
        venue_count: Number of venues
        version: Algorithm version (for future changes)
        
    Returns:
        Liquidity score as Decimal
    """
    if venue_count == 0:
        return Decimal(0)
    
    score = Decimal(total_volume) / Decimal(venue_count)
    return score.quantize(Decimal("0.01"), ROUND_HALF_UP)
```

**Key points**:
- Pure function (no DB, no side effects)
- Version parameter for future algorithm changes
- Returns Decimal for precision

---

## Step 2: Update Pipeline

Open `src/spine/domains/otc/pipelines.py` and modify `AggregateWeekPipeline`:

```python
from spine.domains.otc.calculations import (
    compute_symbol_summaries,
    compute_venue_shares,
    compute_liquidity_score,  # Add import
)

@register_pipeline("otc.aggregate_week")
class AggregateWeekPipeline(Pipeline):
    
    def run(self) -> PipelineResult:
        # ... existing code ...
        
        summaries = compute_symbol_summaries(records)
        
        # NEW: Compute liquidity scores
        for s in summaries:
            s.liquidity_score = compute_liquidity_score(
                s.total_volume, 
                s.venue_count
            )
        
        # Write summaries (add new column)
        for s in summaries:
            conn.execute(f"""
                INSERT INTO {TABLES["symbol_summary"]} (
                    week_ending, tier, symbol,
                    total_volume, total_trades, venue_count, avg_trade_size,
                    liquidity_score,  -- NEW
                    execution_id, batch_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(s.week_ending), s.tier.value, s.symbol,
                s.total_volume, s.total_trades, s.venue_count,
                str(s.avg_trade_size) if s.avg_trade_size else None,
                str(s.liquidity_score),  # NEW
                ctx.execution_id, ctx.batch_id, datetime.utcnow().isoformat()
            ))
        
        # ... rest of existing code ...
```

---

## Step 3: Add Database Column

Create migration or run directly:

```sql
-- For SQLite
ALTER TABLE otc_symbol_summary ADD COLUMN liquidity_score TEXT;

-- For PostgreSQL
ALTER TABLE otc_symbol_summary ADD COLUMN liquidity_score NUMERIC;
```

---

## Step 4: Add to Data Model (Optional)

Update `calculations.py` SymbolSummary dataclass:

```python
@dataclass
class SymbolSummary:
    week_ending: date
    tier: Tier
    symbol: str
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal = None
    liquidity_score: Decimal = None  # NEW
```

---

## Step 5: Test

```bash
# Run aggregate for a week
spine run otc.aggregate_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1

# Check results
sqlite3 spine.db "SELECT symbol, liquidity_score FROM otc_symbol_summary WHERE week_ending = '2025-12-26' LIMIT 5;"
```

---

## What You Didn't Have to Do

Because of `spine.core` primitives, you did NOT need to:

- ❌ Create a new manifest table or stage
- ❌ Implement reject handling
- ❌ Write idempotency logic
- ❌ Set up lineage tracking
- ❌ Create quality check infrastructure
- ❌ Handle execution context

All that infrastructure is composed from `spine.core`.

---

## Adding a Quality Check

Want to validate liquidity scores? Add to the aggregate pipeline:

```python
def check_liquidity_scores(ctx: dict) -> QualityResult:
    """Warn if any liquidity score is suspiciously high."""
    summaries = ctx["summaries"]
    high_scores = [s for s in summaries if s.liquidity_score > 10_000_000]
    
    if not high_scores:
        return QualityResult(QualityStatus.PASS, "All scores reasonable")
    
    return QualityResult(
        QualityStatus.WARN,
        f"{len(high_scores)} symbols have very high liquidity scores",
        actual_value=[s.symbol for s in high_scores[:5]]
    )

# In pipeline run()
quality.add(QualityCheck(
    "liquidity_score_range", 
    QualityCategory.BUSINESS_RULE, 
    check_liquidity_scores
))
```

---

## Version 2 Later

When you want to change the algorithm:

```python
def compute_liquidity_score(
    total_volume: int,
    venue_count: int,
    total_trades: int = None,  # NEW parameter
    version: str = "v2"        # UPDATED default
) -> Decimal:
    if version == "v1":
        # Original logic
        return Decimal(total_volume) / Decimal(venue_count)
    
    # v2: Include trade count
    if total_trades and venue_count:
        vol_per_venue = Decimal(total_volume) / venue_count
        trades_per_venue = Decimal(total_trades) / venue_count
        return (vol_per_venue * trades_per_venue).sqrt()
    
    return Decimal(0)
```

Store the version in the database:

```sql
ALTER TABLE otc_symbol_summary ADD COLUMN liquidity_score_version TEXT;
```

---

## Summary

| Task | File Changed | Lines Changed |
|------|--------------|---------------|
| Add pure function | `calculations.py` | +15 |
| Call from pipeline | `pipelines.py` | +5 |
| Add DB column | migration | +1 |
| **Total** | **2 files** | **~21 lines** |

This is the power of thin domains + thick platform.

---

## Why This Works

The OTC domain uses **shared core infrastructure**:

| Infrastructure | Table | Owned By |
|----------------|-------|----------|
| Workflow tracking | `core_manifest` | `spine.core` |
| Validation failures | `core_rejects` | `spine.core` |
| Quality checks | `core_quality` | `spine.core` |

Adding `liquidity_score` only touches **domain data tables** (`otc_symbol_summary`).
The manifest/rejects/quality infrastructure is already set up and works automatically.

**Files you did NOT need to change**:
- `schema.py` ✅ (no new tables)
- `manifest.py` ✅ (uses core_manifest)
- `rejects.py` ✅ (uses core_rejects)
- `quality.py` ✅ (uses core_quality)
