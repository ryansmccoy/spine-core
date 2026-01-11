# 03 — Calculation Lifecycle Scenarios

> **Stress tests for CREATE / CHANGE / VERSION / DEPRECATE / DELETE**

---

## Scenario A — CREATE (Add New Calcs)

### A1. Venue Concentration (Ratio/Share Calc)

**Purpose**: Compute each venue's market share within a tier for a given week.

**Formula**:
```
market_share_pct = venue_volume / tier_total_volume
```

**Business Keys**: `(week_ending, tier, mpid)`

#### Implementation

**File**: `packages/spine-domains/src/spine/domains/finra/otc_transparency/calculations.py`

```python
@dataclass
class VenueConcentrationRow:
    """Venue concentration (market share) for a single venue."""
    week_ending: date
    tier: Tier
    mpid: str
    total_volume: int
    total_trades: int
    symbol_count: int
    market_share_pct: float  # 0.0 to 1.0
    rank: int  # 1 = largest venue
    
    calc_name: str = "venue_concentration"
    calc_version: str = "v1"
    capture_id: str = ""
    captured_at: str = ""

def compute_venue_concentration_v1(
    venue_rows: Sequence[VenueVolumeRow],
) -> list[VenueConcentrationRow]:
    """
    Compute venue concentration (market share) for each MPID.
    
    Groups by (week, tier, mpid), computes share of total tier volume.
    """
    # Group by (week, tier)
    by_week_tier: dict[tuple[date, Tier], list[VenueVolumeRow]] = defaultdict(list)
    for row in venue_rows:
        by_week_tier[(row.week_ending, row.tier)].append(row)
    
    results = []
    for (week, tier), rows in by_week_tier.items():
        # Aggregate per MPID
        by_mpid: dict[str, list[VenueVolumeRow]] = defaultdict(list)
        for r in rows:
            by_mpid[r.mpid].append(r)
        
        # Compute totals
        venue_totals = []
        for mpid, mpid_rows in by_mpid.items():
            venue_totals.append({
                "mpid": mpid,
                "volume": sum(r.total_shares for r in mpid_rows),
                "trades": sum(r.total_trades for r in mpid_rows),
                "symbols": len(set(r.symbol for r in mpid_rows)),
            })
        
        tier_volume = sum(v["volume"] for v in venue_totals)
        
        # Compute shares and rank
        venue_totals.sort(key=lambda x: x["volume"], reverse=True)
        for rank, v in enumerate(venue_totals, 1):
            share = v["volume"] / tier_volume if tier_volume > 0 else 0.0
            results.append(VenueConcentrationRow(
                week_ending=week,
                tier=tier,
                mpid=v["mpid"],
                total_volume=v["volume"],
                total_trades=v["trades"],
                symbol_count=v["symbols"],
                market_share_pct=share,
                rank=rank,
            ))
    
    return results
```

**Schema** (added to `schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS finra_otc_transparency_venue_concentration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,
    market_share_pct TEXT NOT NULL,  -- Stored as decimal string
    rank INTEGER NOT NULL,
    
    -- Calc identity
    calc_name TEXT NOT NULL DEFAULT 'venue_concentration',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, mpid, capture_id, calc_version)
);

CREATE INDEX IF NOT EXISTS idx_venue_concentration_capture 
    ON finra_otc_transparency_venue_concentration(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_venue_concentration_rank 
    ON finra_otc_transparency_venue_concentration(week_ending, tier, rank);
```

**Pipeline**: `finra.otc_transparency.compute_venue_concentration`

**Tests**:
- Invariant: `SUM(market_share_pct) = 1.0` per (week, tier)
- Invariant: `rank` values are 1..N with no gaps
- Golden: Expected output for fixture data

---

### A2. Top-N Symbols (Concentration Calc)

**Purpose**: Find the top N symbols by volume and compute concentration metrics.

**Formula**:
```
top_n_share = SUM(top_n_volumes) / total_volume
hhi = SUM(share_i^2) for all symbols  # Herfindahl-Hirschman Index
```

**Business Keys**: `(week_ending, tier, rank)`

#### Implementation

```python
@dataclass
class TopNSymbolsRow:
    """Top-N symbol concentration for a tier."""
    week_ending: date
    tier: Tier
    rank: int  # 1 = largest
    symbol: str
    total_volume: int
    total_trades: int
    venue_count: int
    share_pct: float
    cumulative_share_pct: float  # Running total from rank 1
    
    calc_name: str = "top_n_symbols"
    calc_version: str = "v1"
    capture_id: str = ""
    captured_at: str = ""

@dataclass
class ConcentrationMetrics:
    """Tier-level concentration summary."""
    week_ending: date
    tier: Tier
    total_symbols: int
    top_5_share: float
    top_10_share: float
    top_20_share: float
    hhi: float  # Herfindahl-Hirschman Index (0-1 scale)
    
    calc_name: str = "concentration_metrics"
    calc_version: str = "v1"

def compute_top_n_symbols_v1(
    summaries: Sequence[SymbolAggregateRow],
    n: int = 20,
) -> tuple[list[TopNSymbolsRow], ConcentrationMetrics]:
    """
    Compute top-N symbols and concentration metrics.
    """
    # Group by (week, tier)
    by_week_tier: dict[tuple[date, Tier], list[SymbolAggregateRow]] = defaultdict(list)
    for s in summaries:
        by_week_tier[(s.week_ending, s.tier)].append(s)
    
    results = []
    metrics = []
    
    for (week, tier), rows in by_week_tier.items():
        # Sort by volume descending
        sorted_rows = sorted(rows, key=lambda x: x.total_shares, reverse=True)
        total_volume = sum(r.total_shares for r in sorted_rows)
        
        cumulative = 0.0
        for rank, row in enumerate(sorted_rows[:n], 1):
            share = row.total_shares / total_volume if total_volume > 0 else 0.0
            cumulative += share
            results.append(TopNSymbolsRow(
                week_ending=week,
                tier=tier,
                rank=rank,
                symbol=row.symbol,
                total_volume=row.total_shares,
                total_trades=row.total_trades,
                venue_count=row.venue_count,
                share_pct=share,
                cumulative_share_pct=cumulative,
            ))
        
        # Compute HHI
        shares = [r.total_shares / total_volume for r in sorted_rows] if total_volume > 0 else []
        hhi = sum(s * s for s in shares)
        
        # Get top-N shares
        top_5 = sum(shares[:5]) if len(shares) >= 5 else sum(shares)
        top_10 = sum(shares[:10]) if len(shares) >= 10 else sum(shares)
        top_20 = sum(shares[:20]) if len(shares) >= 20 else sum(shares)
        
        metrics.append(ConcentrationMetrics(
            week_ending=week,
            tier=tier,
            total_symbols=len(sorted_rows),
            top_5_share=top_5,
            top_10_share=top_10,
            top_20_share=top_20,
            hhi=hhi,
        ))
    
    return results, metrics
```

**Tests**:
- Invariant: `cumulative_share_pct` at rank N == `top_N_share`
- Invariant: HHI in range [0, 1]
- Invariant: Ranks 1..N consecutive

---

### A3. Week-over-Week Change (Temporal Calc) — Optional

**Purpose**: Compute WoW change in volume for each symbol.

```python
@dataclass
class WoWChangeRow:
    week_ending: date
    tier: Tier
    symbol: str
    current_volume: int
    prior_volume: int | None
    volume_change: int | None
    volume_change_pct: float | None
    
    calc_name: str = "wow_change"
    calc_version: str = "v1"
```

Deferred to future work — requires temporal join across weeks.

---

## Scenario B — CHANGE (Modify Existing Calc)

### Decision Rule

| Change Type | Version Impact | Example |
|-------------|---------------|---------|
| Bug fix (same semantics) | Stays v1 | Fix rounding error |
| Add new output field | Stays v1 | Add `avg_trade_size` |
| Change formula | Becomes v2 | Change share calculation |
| Change business keys | Becomes v2 | Add new grouping dimension |

### Example: Bug Fix (stays v1)

```python
# Before (bug: integer division)
market_share_pct = venue_volume // tier_volume

# After (fix: float division)
market_share_pct = venue_volume / tier_volume if tier_volume > 0 else 0.0
```

Action: Fix in place, rerun backfill with `force=true`.

### Example: Formula Change (becomes v2)

```python
# v1: Simple share
market_share_pct = venue_volume / tier_volume

# v2: Weighted by trade count
market_share_pct = (venue_volume * 0.7 + venue_trades * 0.3) / tier_weighted_total
```

Action:
1. Add `compute_venue_concentration_v2()` function
2. Pipeline selects by `calc_version` param
3. Keep v1 rows, add v2 rows with `calc_version='v2'`

---

## Scenario C — VERSION (v1 alongside v2)

### Implementation Pattern

```python
def compute_venue_concentration(
    venue_rows: Sequence[VenueVolumeRow],
    version: str = "v2",  # Default to latest
) -> list[VenueConcentrationRow]:
    if version == "v1":
        return compute_venue_concentration_v1(venue_rows)
    elif version == "v2":
        return compute_venue_concentration_v2(venue_rows)
    else:
        raise ValueError(f"Unknown version: {version}")
```

### Pipeline Parameter

```python
class ComputeVenueConcentrationPipeline(Pipeline):
    spec = PipelineSpec(
        optional_params={
            "calc_version": ParamDef(
                name="calc_version",
                type=str,
                description="Calc version (v1, v2). Default: v2",
                default="v2",
            ),
        },
    )
    
    def run(self):
        version = self.params.get("calc_version", "v2")
        results = compute_venue_concentration(venue_rows, version=version)
        # Insert with calc_version=version
```

### Query Selection

```sql
-- Latest version only (view)
SELECT * FROM finra_otc_transparency_venue_concentration_latest
WHERE week_ending = '2025-12-26' AND tier = 'OTC';

-- Specific version
SELECT * FROM finra_otc_transparency_venue_concentration
WHERE week_ending = '2025-12-26' AND tier = 'OTC' AND calc_version = 'v1';

-- All versions (for comparison)
SELECT * FROM finra_otc_transparency_venue_concentration
WHERE week_ending = '2025-12-26' AND tier = 'OTC'
ORDER BY mpid, calc_version;
```

### CLI

```bash
# Default (v2)
spine query venue-concentration -p tier=OTC -p week_ending=2025-12-26

# Explicit v1
spine query venue-concentration -p tier=OTC -p week_ending=2025-12-26 --calc-version=v1

# Compare versions
spine query venue-concentration -p tier=OTC -p week_ending=2025-12-26 --all-versions
```

---

## Scenario D — DEPRECATE → DELETE

### Deprecation Lifecycle

```
ACTIVE → DEPRECATED → SUNSET → DELETED
```

| Stage | Behavior |
|-------|----------|
| ACTIVE | Full support, default version |
| DEPRECATED | Writes allowed, warning logged, not default |
| SUNSET | Writes blocked, reads allowed |
| DELETED | Table/column dropped (migration required) |

### Implementation

**1. Mark in Registry**

```python
CALCS = {
    "venue_concentration": {
        "versions": ["v1", "v2"],
        "current": "v2",
        "deprecated": ["v1"],  # v1 is deprecated
        "sunset": [],
    },
}
```

**2. Pipeline Warning**

```python
def run(self):
    version = self.params.get("calc_version", "v2")
    
    if version in CALCS["venue_concentration"]["deprecated"]:
        log.warning(
            "calc.deprecated",
            calc="venue_concentration",
            version=version,
            message="v1 is deprecated, use v2",
        )
    
    if version in CALCS["venue_concentration"]["sunset"]:
        raise ValueError(f"Calc version {version} is sunset and cannot be written")
```

**3. Query Warning**

```python
def query_venue_concentration(version=None):
    if version in CALCS["venue_concentration"]["deprecated"]:
        log.warning("Querying deprecated calc version")
    return results
```

### Deletion (Migration-Gated)

**Never delete data without migration**:

```sql
-- migrations/002_drop_venue_concentration_v1.sql
-- DANGER: This deletes historical data. Review carefully.

BEGIN TRANSACTION;

-- Record deletion for audit
INSERT INTO _migrations (filename) VALUES ('002_drop_venue_concentration_v1.sql');

-- Delete v1 rows
DELETE FROM finra_otc_transparency_venue_concentration
WHERE calc_version = 'v1';

COMMIT;
```

**Deletion checklist**:
- [ ] All consumers migrated to v2
- [ ] No queries reference v1
- [ ] Audit trail preserved elsewhere if needed
- [ ] Migration reviewed by 2nd person
