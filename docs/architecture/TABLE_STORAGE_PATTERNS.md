# Table Explosion Mitigation Strategy

## Problem Statement

Analytics platforms face a fundamental tension:
- **Materialized Tables:** Fast queries, expensive storage, schema proliferation
- **Logical Calculations:** Flexible, storage-efficient, potential query performance issues

Market Spine has demonstrated this with FINRA OTC analytics:
- 4 calculation tables created (venue volume, venue share, HHI, tier split)
- Each requires: table definition, indexes, migration, tests, documentation
- Adding new calculations → more tables → schema management burden

**The Question:** When should we materialize a calculation vs compute it on-demand?

This document establishes **explicit policy** for storage patterns to prevent unbounded table growth while maintaining performance and correctness guarantees.

---

## Storage Pattern 1: Materialized Calculation Tables

### Definition

A dedicated table stores pre-computed aggregations, with each calculation persisted as rows.

### Current Examples

```sql
-- Materialized: Venue market share
CREATE TABLE finra_otc_transparency_weekly_symbol_venue_share (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    venue_share REAL NOT NULL,  -- Pre-computed
    ...
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);

-- Materialized: HHI concentration
CREATE TABLE finra_otc_transparency_weekly_symbol_venue_concentration_hhi (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    hhi REAL NOT NULL,  -- Pre-computed
    ...
    UNIQUE(week_ending, tier, symbol, capture_id)
);
```

### When to Use

**Use materialized tables when:**

1. **Complex Aggregation Logic**
   - Calculation spans multiple tables or stages
   - Non-trivial SQL (window functions, recursive CTEs, multi-pass)
   - Difficult to express as simple view

2. **Institutional Durability Requirements**
   - Regulators require "auditable snapshots as of date X"
   - Point-in-time replay critical (e.g., compliance reporting)
   - Need to prove "HHI we reported on Jan 10 was calculated from data state Y"

3. **High Query Frequency**
   - Calculation accessed >10x per day by trading desk
   - API endpoints serve this data interactively
   - Query latency SLA <1 second

4. **Versioning Critical**
   - Calculation methodology changes over time
   - Must compare v1 vs v2 results side-by-side
   - `calc_version` column distinguishes algorithm generations

5. **Intermediate Build Product**
   - Calculation feeds downstream analytics
   - Other calcs depend on this result
   - Breaking dependency chain would cascade complexity

### Pros

✅ **Query Performance**
- Pre-aggregated → fast lookups
- Indexes optimized for access patterns
- No compute overhead at query time

✅ **Point-in-Time Replay**
- capture_id preserves exact calculation state
- Can retrieve "HHI as of Monday morning" even if data revised Tuesday
- Audit trail for compliance

✅ **Schema Stability**
- Table definition locks in column types, constraints
- Breaking changes require migration (deliberate, not accidental)
- Downstream consumers have stable contract

✅ **Execution Visibility**
- execution_id, batch_id track lineage
- Can trace: "Who computed this? When? From what inputs?"
- Debugging failures easier

✅ **Versioning Support**
- calc_version allows coexistence of old and new algorithms
- Can backfill with new logic while keeping old results
- A/B testing of calculation changes

### Cons

❌ **Storage Overhead**
- Every calculation = new table
- Indexes multiply storage (3-5 indexes per table)
- 10 calculations × 52 weeks × 3 years = significant space

❌ **Schema Proliferation**
- Each table requires:
  - CREATE TABLE statement
  - Indexes
  - Migration coordination with DBA
  - Tests
  - Documentation
- 50 calculations = 50 tables to maintain

❌ **Backfill Burden**
- Adding new calculation to historical data:
  - Recompute 3 years × 52 weeks = 156 runs
  - Storage doubles (before and after)
  - Time-consuming for large datasets

❌ **Rigidity**
- Changing calculation logic requires:
  - New calc_version or new table
  - Migration to add columns
  - Backfill to populate historical data
- Inhibits experimentation

❌ **Synchronization Risk**
- If normalized table updated, must recompute downstream calcs
- Manual tracking: "Which calcs depend on this source?"
- Stale results if recomputation skipped

### Impact on Operational Concerns

**Replay:**
- ✅ Perfect replay: capture_id + calc_version = deterministic results
- ✅ Can reconstruct "state of world as of timestamp T"

**Versioning:**
- ✅ Strong: calc_version column allows multiple algorithms coexisting
- ✅ Can compare old vs new side-by-side

**Backfill:**
- ❌ Expensive: Must recompute and persist all historical partitions
- ❌ Storage doubles (before and after backfill)

**Dependency Management:**
- ⚠️ Requires explicit tracking (see core_calc_dependencies)
- ⚠️ No automatic invalidation—must manually recompute

---

## Storage Pattern 2: Logical Calculations (Views / Query-Time Aggregation)

### Definition

Calculations expressed as SQL views or application-layer logic, computed on-demand from base tables.

### Examples

```sql
-- Logical: Average trade size (not materialized)
CREATE VIEW finra_otc_transparency_avg_trade_size AS
SELECT 
    week_ending,
    tier,
    symbol,
    mpid,
    CAST(total_shares AS REAL) / total_trades AS avg_trade_size
FROM finra_otc_transparency_normalized
WHERE total_trades > 0;

-- Logical: Top 10 venues by market share (dynamic)
CREATE VIEW finra_otc_transparency_top_venues_latest AS
SELECT 
    week_ending,
    tier,
    mpid,
    SUM(total_shares) AS total_volume,
    ROW_NUMBER() OVER (PARTITION BY week_ending, tier ORDER BY SUM(total_shares) DESC) AS rank
FROM finra_otc_transparency_normalized_latest
GROUP BY week_ending, tier, mpid
HAVING rank <= 10;

-- Logical: Symbol liquidity score (composite formula)
CREATE VIEW finra_otc_transparency_liquidity_score_v2 AS
SELECT
    week_ending,
    tier,
    symbol,
    -- New experimental formula (no table change needed)
    LOG(total_volume + 1) * LOG(total_trades + 1) * LOG(venue_count + 1) AS liquidity_score_v2
FROM finra_otc_transparency_symbol_summary_latest;
```

### When to Use

**Use logical calculations when:**

1. **Simple Derivation**
   - Calculation is straightforward math on existing columns
   - Single-table operation (no joins required)
   - Example: `avg_trade_size = total_shares / total_trades`

2. **Low Query Frequency**
   - Accessed <1x per day
   - Ad-hoc analyst queries, not production API
   - Acceptable query latency >5 seconds

3. **Experimental / Exploratory**
   - Testing new metric ideas
   - Analyst wants to try different formulas
   - Not yet committed to production
   - Example: "What if we weight HHI by trade count instead of volume?"

4. **Highly Dynamic**
   - Calculation logic changes frequently
   - Parameters vary per user (personalized thresholds)
   - Example: "Top N venues" where N is user input

5. **Storage Constraints**
   - Database size limits approached
   - Cost of storage > cost of compute
   - Rare access doesn't justify persistence

6. **Derived from Latest Only**
   - No point-in-time replay needed
   - Always queries current state
   - Example: "Current top 10 symbols by volume"

### Pros

✅ **No Storage Overhead**
- Views store only definition, not data
- Indexes on base tables reused
- Storage scales with base data, not calculations

✅ **Schema Flexibility**
- Add new view = single CREATE VIEW statement
- No migration, no DBA approval
- Drop view anytime without data loss

✅ **Always Fresh**
- View reflects current base table state
- No synchronization issues
- Cannot be stale

✅ **Experimentation-Friendly**
- Try new formulas instantly
- A/B test: `liquidity_score_v1` vs `liquidity_score_v2` as separate views
- Iterate rapidly

✅ **Self-Documenting**
- View SQL shows calculation logic explicitly
- No hidden preprocessing steps
- Analysts can inspect and understand

### Cons

❌ **Query Performance**
- Recomputes on every query
- Complex views = slow queries
- Cannot add indexes directly to view

❌ **No Point-in-Time Replay**
- Views query current base table state
- Cannot retrieve "view as of timestamp T" (unless base table has capture_id)
- Audit trail lost

❌ **Versioning Challenges**
- View definition changes overwrite old logic
- Cannot compare "old formula vs new formula" on same dataset
- Must recreate old view to see historical results

❌ **Lineage Opacity**
- No execution_id tracking who queried when
- Cannot audit: "Did trading desk use stale view on Tuesday?"
- Provenance unclear

❌ **Dependency Fragility**
- View breaks if base table schema changes
- No explicit dependency tracking in database
- Must manually find all views using table X

### Impact on Operational Concerns

**Replay:**
- ❌ Weak: Views query current state only
- ⚠️ Can work if base tables preserve capture_id (query: `WHERE capture_id = X`)

**Versioning:**
- ❌ Difficult: Changing view overwrites old definition
- ⚠️ Workaround: Create `_v1`, `_v2` views explicitly

**Backfill:**
- ✅ No backfill needed: View reflects base data automatically
- ✅ Storage-efficient

**Dependency Management:**
- ❌ Implicit: No metadata links view to base tables
- ❌ Breaking changes to base table silently break views

---

## Decision Framework

### Flowchart for Choosing Storage Pattern

```
Start: New calculation proposed
│
├─ Is point-in-time replay required? (compliance, audit)
│  ├─ YES → Materialize
│  └─ NO → Continue
│
├─ Is query frequency > 10/day or latency SLA < 1s?
│  ├─ YES → Materialize
│  └─ NO → Continue
│
├─ Is calculation complex (multi-table, window functions)?
│  ├─ YES → Materialize
│  └─ NO → Continue
│
├─ Is this experimental or exploratory?
│  ├─ YES → Use View
│  └─ NO → Continue
│
├─ Will calculation logic change frequently?
│  ├─ YES → Use View (initially), materialize if becomes stable
│  └─ NO → Materialize
│
└─ Default → Use View (can promote to table later)
```

### Concrete Decision Examples

| Calculation | Pattern | Rationale |
|-------------|---------|-----------|
| Venue market share | Materialized | High query freq, audit trail, complex multi-pass SQL |
| HHI concentration | Materialized | Regulatory reporting, point-in-time critical |
| Tier volume split | Materialized | Feeds downstream calcs, versioning important |
| Average trade size | View | Simple division, low query freq |
| Top 10 venues | View | Dynamic ranking, user-parameterized |
| Experimental liquidity score v3 | View | Testing new formula, may discard |
| Symbol percentile ranks | View (initially) | Exploratory, promote to table if becomes standard |
| Daily VWAP | Materialized | High freq API, sub-second latency SLA |

---

## Hybrid Pattern: Materialized Views (Future Consideration)

Some databases support **materialized views**: views with cached results.

### Advantages
- Query performance of tables
- Schema flexibility of views
- Automatic refresh on base table changes (some DBs)

### SQLite Limitation
SQLite does not support materialized views natively.

### Workaround Pattern
```sql
-- Manually managed materialized view
CREATE TABLE _mv_liquidity_score AS
SELECT week_ending, tier, symbol, ...
FROM finra_otc_transparency_symbol_summary_latest;

-- Refresh trigger (manual or scheduled)
DELETE FROM _mv_liquidity_score WHERE week_ending = ?;
INSERT INTO _mv_liquidity_score SELECT ... WHERE week_ending = ?;
```

### When to Use
- Need view flexibility + table performance
- Acceptable to have eventual consistency (refresh lag)
- Can tolerate manual refresh management

---

## Migration Path: View → Table Promotion

### Scenario
Analyst creates experimental view. Usage grows. Now requires materialization.

### Migration Steps

**Step 1: Create Materialized Table**
```sql
CREATE TABLE finra_otc_transparency_liquidity_score_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    liquidity_score REAL NOT NULL,
    
    calc_name TEXT NOT NULL DEFAULT 'liquidity_score_v2',
    calc_version TEXT NOT NULL DEFAULT 'v2',
    
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);
```

**Step 2: Backfill Historical Data**
```python
for week in historical_weeks:
    for tier in tiers:
        compute_liquidity_score_v2(week, tier)
        # Persist to new table
```

**Step 3: Update Downstream Dependencies**
```sql
-- Old: Query view
SELECT * FROM finra_otc_transparency_liquidity_score_v2_view;

-- New: Query table (latest)
SELECT * FROM finra_otc_transparency_liquidity_score_v2_latest;
```

**Step 4: Deprecate View (Optional)**
```sql
-- Keep view as alias to latest for backward compatibility
CREATE VIEW finra_otc_transparency_liquidity_score_v2_view AS
SELECT * FROM finra_otc_transparency_liquidity_score_v2_latest;
```

---

## Storage Cost Analysis

### Example: 3 Years of FINRA OTC Data

**Base Tables (Normalized):**
- 52 weeks/year × 3 years × 3 tiers × 3,000 symbols × 150 venues
- ~70M rows in `finra_otc_transparency_normalized`
- Storage: ~10 GB (with indexes)

**Materialized Calculations (Current 4 tables):**
- Venue volume: ~70M rows → 10 GB
- Venue share: ~70M rows → 10 GB
- HHI: ~468k rows (per symbol, not venue) → 100 MB
- Tier split: ~468k rows → 100 MB
- **Total: ~20 GB additional**

**If All 20 Planned Calcs Materialized:**
- 20 tables × avg 5 GB = **100 GB additional**
- **5x storage growth**

**If 15 Calcs as Views:**
- Storage: **0 GB** (views are free)
- Trade-off: Query time increases (acceptable for low-freq queries)

### Cost-Benefit Table

| Approach | Storage | Query Time | Flexibility | Audit Trail |
|----------|---------|------------|-------------|-------------|
| All materialized (20 tables) | 100 GB | <1s | Low | Perfect |
| Hybrid (5 tables, 15 views) | 25 GB | 1-10s | High | Partial |
| All views | 10 GB | 5-30s | Very High | None |

**Recommended:** Hybrid approach
- Materialize: top 5 high-frequency, audit-critical calcs
- Views: 15 low-frequency, exploratory calcs
- Promote views to tables when usage justifies

---

## Policy Recommendations

### For Data Engineers

1. **Default to Views for New Calculations**
   - Start lightweight
   - Promote to table when usage/performance demands

2. **Require Justification for New Tables**
   - Document: Why not a view?
   - Approval: Lead architect signs off on new table

3. **Quarterly Review**
   - Identify unused tables → deprecate
   - Identify high-usage views → promote to tables

4. **Naming Convention**
   - Materialized: `{domain}_{entity}_{metric}`
   - Views: `{domain}_{entity}_{metric}_view` or `_vw`
   - Experimental: `{domain}_{entity}_{metric}_v{N}`

### For Analysts

1. **Create Views for Exploration**
   - No permission needed
   - Iterate rapidly
   - Document formula in view SQL

2. **Request Materialization When:**
   - Query time >10s and used daily
   - Need point-in-time replay
   - Calculation feeds downstream work

3. **Use Scratch Tables for One-Offs**
   - `CREATE TABLE _scratch_{analyst_name}_{metric} AS SELECT ...`
   - Self-contained, disposable
   - No long-term maintenance burden

### For DBAs

1. **Approve Materializations Quarterly**
   - Batch schema changes
   - Coordinate migrations
   - Prevent ad-hoc table sprawl

2. **Monitor View Query Performance**
   - Identify slow views (>30s)
   - Suggest: optimize query or materialize

3. **Enforce Storage Budgets**
   - Domain-level limits (e.g., FINRA ≤ 50 GB)
   - Trigger review when approaching limit

---

## Comparison to Industry Patterns

### Data Lakehouse (Databricks, Snowflake)
- **Pattern:** External tables + cached query results
- **Market Spine Equivalent:** Base tables (normalized) + views
- **When to Materialize:** When view becomes "business-critical table"

### Data Warehouse (Redshift, BigQuery)
- **Pattern:** Fact tables + aggregate tables + OLAP cubes
- **Market Spine Equivalent:** Normalized (fact) + calculation tables (aggregates)
- **Trade-off:** Query speed vs storage cost

### Operational Data Store (Postgres)
- **Pattern:** Normalized tables + materialized views
- **Market Spine Equivalent:** Normalized + calculation tables
- **SQLite Limitation:** No auto-refreshing materialized views

---

## Summary

| Aspect | Materialized Tables | Views |
|--------|---------------------|-------|
| **Use When** | High-freq, audit-critical, complex | Low-freq, experimental, simple |
| **Storage** | ❌ High | ✅ Zero |
| **Query Speed** | ✅ Fast (<1s) | ⚠️ Variable (1-30s) |
| **Replay** | ✅ Perfect (capture_id) | ❌ Current state only |
| **Versioning** | ✅ Strong (calc_version) | ❌ Weak (overwrite) |
| **Flexibility** | ❌ Rigid (migration needed) | ✅ Flexible (instant change) |
| **Backfill** | ❌ Expensive | ✅ Free |
| **Dependencies** | ⚠️ Requires tracking | ❌ Implicit |

**Default Strategy:**
1. Start with view (lightweight, flexible)
2. Promote to table when:
   - Query frequency >10/day
   - Latency SLA <1s
   - Audit trail required
3. Review quarterly: deprecate unused tables, promote high-usage views

This prevents unbounded table growth while maintaining performance for critical calculations.
