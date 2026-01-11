# Add Complementary Data Sources to Spine (Implementation Brief for Claude)

This document is a **handoff spec** for implementing additional data sources that **complement FINRA OTC weekly** and validate that the Spine model generalizes.

It includes:
- What to add (recommended sources + sequence)
- Why it’s valuable (reasoning)
- Exactly how to obtain data (URLs / endpoints / download methods)
- Proposed folder structure, schema, and pipelines
- Test scenarios and fixtures
- Milestones (Basic vs Intermediate)

---

## 0) Design principles (carry-over from FINRA OTC)

We will preserve the same “Spine truths” already established:

### The 3 clocks (always store all when possible)
1) **Business time** — when the underlying economic event occurred (e.g., trading day, week ending)
2) **Source system time** — when the publisher released/updated the data (e.g., lastUpdateDate, revised_at)
3) **Platform capture time** — when we ingested it (captured_at + capture_id)

### Stable capture semantics
- Every ingest produces a `capture_id`
- Re-ingesting the same file should be **deterministic and tested** (either dedupe/overwrite or multi-capture behavior)
- Pipelines should infer business time **in the domain pipeline**, not in the CLI

---

## 1) Recommended additional sources (and why)

### A) Daily OHLCV price/volume (FIRST to implement)
**Why it complements FINRA OTC**
- FINRA OTC = *who traded, where, and how much (weekly aggregates)*
- OHLCV = *what the instrument did (daily price action + volume)*

Together, they enable validation and future analytics:
- “Did OTC liquidity spikes coincide with price moves?”
- “Does venue concentration correlate with volatility or volume?”

**Why it’s a great Spine test**
- Different cadence: daily vs weekly
- Clean business time semantics (trading date)
- Forces careful typing + constraints (prices, volume)

### B) Short interest (SECOND to implement; Intermediate-friendly)
**Why it complements FINRA OTC**
- Adds market positioning context
- Naturally delayed reporting + occasional revisions
- Excellent for validating the 3-clock model

### C) Reference trading calendar (NYSE holidays) (supporting dataset)
**Why it matters**
- Makes “week ending” derivations holiday-aware (Intermediate upgrade)
- Adds a clean reference-data pattern (slow-changing dimension)

---

## 2) Implementation plan overview

### Phase 1 (Basic): Add OHLCV daily prices domain
- Add domain package: `spine-domains-prices`
- Add schema: `prices_daily_raw` (and optional `prices_daily`)
- Add pipelines:
  - `prices.ingest_daily` (required)
  - `prices.normalize_daily` (optional)
- Add fixtures in repo
- Add scenario tests (missing rows, duplicates, malformed numeric)

### Phase 2 (Intermediate): Add short interest + calendar
- Add `short_interest` domain + pipeline
- Add `calendar` domain or reference table
- Add revision/backfill semantics and tests

---

## 3) Daily OHLCV prices (Basic) — concrete spec

### 3.1 Source options (choose one)

#### Option 1 (recommended): Stooq (free, CSV over HTTP)
- Pros: free, simple CSV downloads, no API key required
- Cons: data quality is “retail grade” but fine for spine testing

Stooq base site (for reference):
- https://stooq.com/

Common download pattern (examples):
- US stocks / ETFs are often available as symbols like `spy.us`
- Stooq supports CSV downloads via a URL pattern

> Note: Stooq’s exact URL pattern can vary; if it’s inconvenient, use Option 2 (Alpha Vantage) or commit small fixtures only.

#### Option 2: Alpha Vantage (free tier, API key)
- Pros: stable API, well-known format
- Cons: API key, rate limits

Docs:
- https://www.alphavantage.co/documentation/

Daily adjusted time series endpoint:
- Function: `TIME_SERIES_DAILY_ADJUSTED`
- Example (requires API key):
  - https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=SPY&apikey=YOUR_KEY&outputsize=compact

#### Option 3: “Fixtures only” for Basic (recommended initially)
For Basic, you can implement ingestion using a local CSV fixture:
- `market-spine-basic/data/prices/fixtures/spy_daily_2025.csv`

Then later (Intermediate), add a connector to fetch from Stooq/AlphaVantage.

**Recommendation for Basic:** fixtures-only first, then add network fetch in Intermediate.

---

### 3.2 Data format (canonical internal representation)

**Input CSV (fixture or downloaded):**
```csv
date,symbol,open,high,low,close,volume
2025-12-15,SPY,470.10,472.30,468.80,471.60,52341234
2025-12-16,SPY,471.60,473.90,470.70,473.20,49811220
```

**Business time:** `date`  
**Source time:** optional (if API provides “last refreshed”)  
**Capture time:** `captured_at`

---

### 3.3 Proposed folder structure

**Package (reusable):**
```
packages/
  spine-domains-prices/
    pyproject.toml
    src/
      spine_domains_prices/
        __init__.py
        connectors/
          __init__.py
          csv_daily.py
          (optional later) stooq.py
          (optional later) alphavantage.py
        pipelines/
          __init__.py
          ingest_daily.py
          normalize_daily.py   # optional
        schema/
          010_prices_tables.sql
        registry.py
```

**Basic app wiring + fixtures:**
```
market-spine-basic/
  data/
    prices/
      fixtures/
        spy_daily_2025.csv
  docs/
    samples/
      prices_daily.md
```

---

### 3.4 Schema (example)

Add a raw table that mirrors the incoming fields, plus clocks:

```sql
CREATE TABLE IF NOT EXISTS prices_daily_raw (
  symbol TEXT NOT NULL,
  trade_date DATE NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume INTEGER NOT NULL,

  -- clocks
  source_last_update_date DATE NULL,
  captured_at TIMESTAMP NOT NULL,
  capture_id TEXT NOT NULL,

  -- helpful metadata
  source TEXT NULL,

  -- Basic uniqueness rule (choose one and be explicit):
  -- Option A: allow multiple captures
  --   UNIQUE(symbol, trade_date, capture_id)
  -- Option B: overwrite semantics per day
  --   UNIQUE(symbol, trade_date)
);
```

Recommendation:
- For parity with OTC capture semantics, prefer **Option A** for multi-capture (Basic can still reset DB frequently).

Indexes:
- `(symbol, trade_date)`
- `(capture_id)`

---

### 3.5 Pipelines

#### `prices.ingest_daily`
Inputs:
- `file_path` OR `symbol + date_range` (Basic: file_path only)
Outputs:
- rows inserted
- capture_id
- date_range inferred

Logs:
- `prices.parse_file.end` (timing + rows)
- `prices.bulk_insert.end` (timing + rows + table)
- `prices.completed` (rows_in/out + capture_id)

#### `prices.normalize_daily` (optional)
- validate numeric types and ranges
- enforce:
  - open/high/low/close > 0
  - high >= max(open, close)
  - low <= min(open, close)
  - volume >= 0
- emit rows_rejected

---

### 3.6 CLI examples (Basic)

```bash
uv run python -m market_spine.cli run prices.ingest_daily -p file_path=./data/prices/fixtures/spy_daily_2025.csv
uv run python -m market_spine.cli run prices.normalize_daily -p symbol=SPY -p start_date=2025-12-15 -p end_date=2025-12-31
```

---

## 4) Tests (prices domain + scenario tests)

### 4.1 Fixtures
- Good file: `spy_daily_2025.csv`
- Bad numeric: `spy_daily_bad_numeric.csv`
- Missing column: `spy_daily_missing_close.csv`
- Duplicate rows: `spy_daily_duplicates.csv`
- Empty file: `spy_daily_empty.csv`

### 4.2 Scenario tests to add
In `tests/data_scenarios/`:

1) ingest succeeds and inserts N rows
2) normalize rejects invalid rows deterministically
3) duplicates handled deterministically (reject or dedupe)
4) re-ingesting same fixture produces explicit behavior (multi-capture or overwrite)
5) malformed date rows rejected with reason

Assertions:
- rows_in/out/rejected
- capture_id present
- invariants: accepted + rejected == rows_in

---

## 5) Short interest (Intermediate) — spec stub

**Why:** delayed cadence + revision-prone = great 3-clock test.

### Potential sources
- FINRA short interest (commonly referenced by broker sites; official access varies)
- Nasdaq short interest (often provides downloadable reports)
- For Intermediate prototype: use fixtures mirroring the real shape.

### Suggested table
- `short_interest_raw(symbol, settlement_date, short_interest, avg_daily_volume, days_to_cover, source_last_update_date, captured_at, capture_id)`

Cadence:
- biweekly or monthly depending on source

Scenarios:
- revisions/backfills for prior settlement dates
- missing fields

---

## 6) Trading calendar (Intermediate) — spec stub

Store a simple calendar table:
- `trading_calendar(date, is_open, close_time, notes, source_last_update_date, captured_at, capture_id)`

Use it to:
- validate week ending derivation
- make “last trading day” holiday-aware

---

## 7) Milestones / PR breakdown

### PR 1 (Basic): prices domain fixture-only
- schema + pipeline + registry
- fixture files
- docs: sample usage
- scenario tests

### PR 2 (Basic): integrate into Basic app
- ensure `spine list` shows prices pipelines
- ensure `uv run ...` works
- add README section

### PR 3 (Intermediate later): network fetch connector
- Stooq or AlphaVantage connector
- add caching + source_last_update_date
- add tests with recorded responses

---

## 8) Acceptance criteria

Basic is “done” when:
- `prices.ingest_daily` works from fixture
- logs contain execution_id/pipeline/capture_id and timings
- scenario tests cover missing/incomplete/duplicate/corrupt cases
- docs show example commands and expected outputs

---

## 9) Notes / reasoning recap

Why add these sources?
- They validate Spine beyond FINRA OTC
- They stress different temporal cadences
- They force clean schema + invariants
- They create a natural bridge into Intermediate features (eventing, revisions, multi-backend)

