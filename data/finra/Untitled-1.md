# Market Spine — Real Trading Analytics Calc Fitness Test (Venue Share + Concentration)

The cross-domain calendar normalization was a good architecture test but doesn’t feel like real trading analytics.
Now implement a trading-analytics-realistic calculation family and an end-to-end smoke test.

## Implement 3 calculations (v1)

### 1) Base aggregate: weekly_symbol_venue_class_volume_v1
- Input: FINRA OTC normalized trades (or best available table)
- Define venue_class taxonomy (OTC / ATS / EXCHANGE / UNKNOWN) based on available fields
- Output grain: (symbol, week_ending, venue_class, capture_id)
- Columns: volume, trade_count (and notional if available)

### 2) Derived ratio: weekly_symbol_venue_share_v1
- Input: weekly_symbol_venue_class_volume_v1
- Output grain: (symbol, week_ending, venue_class, capture_id)
- Column: share = volume / total_volume_for_symbol_week
- Invariants:
  - share in [0,1]
  - sum(share) == 1 per (symbol, week_ending, capture_id) within tolerance
  - if total_volume == 0: either no rows or share==0; choose and document

### 3) Derived concentration: weekly_symbol_venue_concentration_hhi_v1
- Input: weekly_symbol_venue_share_v1
- Output grain: (symbol, week_ending, capture_id)
- Column: hhi = sum(share^2)
- Invariants:
  - hhi in [0,1]
  - if only one venue_class has share 1 => hhi == 1

## DB/schema requirements
- Create dedicated tables for each calc (do not add columns to unrelated existing tables)
- Unique constraints use capture_id
- Add indexes for latest/as-of and symbol/week filtering
- Add CALCS registry entries and versions

## End-to-end smoke test (must feel real)
Add `tests/test_trading_analytics_smoke.py` that:
1) Creates a temp SQLite DB and initializes schema
2) Loads minimal fixtures for:
   - a small set of normalized trades that include multiple venue classes for at least one symbol
3) Runs pipelines end-to-end (dispatcher/runner path) to produce:
   - venue_class_volume
   - venue_share
   - hhi
4) Asserts:
   - volumes reconcile (sum by venue_class == total)
   - shares sum to 1 per symbol/week
   - hhi is bounded and correct in at least one known fixture case
5) Optionally hits the API (FastAPI test client) to query venue_share rows and checks response metadata

## Deliverables
- Change Surface Map (layers changed + why)
- Code + schema + tests passing
- Docs update: “Trading analytics calc family example”
Proceed without follow-up questions; make reasonable assumptions and document them.