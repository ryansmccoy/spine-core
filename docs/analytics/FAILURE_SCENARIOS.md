# Real Trading Analytics Failure Scenarios

## Overview

This document identifies 5 realistic failure scenarios for institutional analytics platforms processing FINRA OTC Transparency data. For each scenario, we detail:
- What breaks in the current system
- What signals users receive
- What diagnostic capabilities are missing
- Recommended hardening measures

These scenarios are based on real operational experience with regulatory data feeds and institutional trading workflows.

---

## Scenario 1: Missing Tier for a Week

### Description

FINRA publishes weekly OTC data across 3 tiers (NMS_TIER_1, NMS_TIER_2, OTC). Due to a FINRA system issue, the OTC tier file for week ending 2025-12-22 is not published on Monday. It arrives 48 hours late on Wednesday.

### What Breaks Today

**Pipeline Behavior:**
- `ingest_week` for OTC tier fails with HTTP 404
- State: FAILED in `core_work_items` after max retries
- Downstream calculations proceed with only 2 tiers
- `finra_otc_transparency_weekly_symbol_tier_volume_share` produces incorrect results
  - Symbols that only trade OTC show 0% total volume
  - Tier share calculations missing denominator component

**Data Artifacts:**
```sql
-- Week 2025-12-22 has incomplete data
SELECT week_ending, tier, COUNT(*) as symbols
FROM finra_otc_transparency_normalized
WHERE week_ending = '2025-12-22'
GROUP BY week_ending, tier;

-- Result: Only NMS_TIER_1 and NMS_TIER_2 present
-- OTC tier missing → 1/3 of market volume absent
```

### What Users See

**Trading Desk Analyst:**
- Queries tier split for XYZT symbol
- Sees 100% volume in NMS_TIER_1, 0% in OTC
- No indication this is incomplete data
- Makes incorrect liquidity assessment

**Compliance Officer:**
- Runs monthly HHI report
- OTC-exclusive symbols show artificially high concentration
- Passes inflated HHI scores to regulators
- Potential regulatory exposure

**Operations Team:**
- `spine doctor` shows gap: "Missing partition: 2025-12-22/OTC"
- But no context about downstream impact
- No alert fired because 2/3 tiers succeeded

### What's Missing for Diagnosis

1. **Partial Success Detection:**
   - System treats tier ingestion independently
   - No concept of "expected tier set per week"
   - Cannot distinguish "OTC not published yet" from "OTC discontinued"

2. **Downstream Propagation Tracking:**
   - Tier split calculation doesn't validate input completeness
   - No warning: "Computed from 2/3 tiers only"
   - Manifest shows stage=COMPLETE even though inputs incomplete

3. **Data Freshness vs Completeness:**
   - `captured_at` tracks when data arrived
   - Doesn't track "expected vs actual partitions"
   - No SLA: "All 3 tiers should arrive within 24h of Monday 8am"

4. **User-Facing Warnings:**
   - Analytics queries return results with no caveats
   - Latest views show incomplete data without annotation
   - No `is_complete` flag or `missing_tiers` column

### Recommended Hardening

**Schema Additions:**
```sql
-- Add to core_anomalies
INSERT INTO core_anomalies (
    domain, pipeline, partition_key, 
    severity, category, message,
    detected_at, capture_id
) VALUES (
    'finra.otc_transparency',
    'compute_tier_volume_share',
    '{"week_ending": "2025-12-22"}',
    'WARN',
    'INCOMPLETE_INPUT',
    'Tier split calculated from 2/3 tiers. Missing: OTC. Results may be inaccurate.',
    '2025-12-23T10:30:00Z',
    'finra.otc_transparency:ALL:2025-12-22:20251223'
);

-- Add completeness tracking to calculations
ALTER TABLE finra_otc_transparency_weekly_symbol_tier_volume_share
ADD COLUMN input_tiers_present INTEGER;  -- e.g., 2 out of 3

ALTER TABLE finra_otc_transparency_weekly_symbol_tier_volume_share
ADD COLUMN is_complete INTEGER DEFAULT 1;  -- 0 if inputs incomplete
```

**Operational Changes:**
- Define expected tier set per domain
- Doctor command checks: "All expected tiers present?"
- Analytics queries filter or annotate incomplete partitions
- Readiness check blocks "ready for trading" until all tiers arrive

---

## Scenario 2: Partial Venue Coverage (Data Quality Degradation)

### Description

FINRA's venue reporting system has an outage affecting smaller venues. Week ending 2025-12-15 data contains only 45 venues instead of the usual 150+. Large venues (VNDM, UBSS, GSCO) are present, but 70% of mid-tier and all long-tail venues are missing.

### What Breaks Today

**Pipeline Behavior:**
- Ingestion succeeds (HTTP 200, valid CSV)
- Normalization succeeds (no schema violations)
- Calculations execute without errors
- All stages show COMPLETE in manifest

**Data Artifacts:**
```sql
-- Venue count drops dramatically
SELECT week_ending, COUNT(DISTINCT mpid) as venue_count
FROM finra_otc_transparency_normalized
WHERE week_ending BETWEEN '2025-11-01' AND '2025-12-22'
GROUP BY week_ending
ORDER BY week_ending;

-- Typical week: 150-180 venues
-- 2025-12-15: 45 venues  ← anomaly not flagged
```

**Calculation Impact:**
- `finra_otc_transparency_weekly_symbol_venue_concentration_hhi`:
  - HHI scores artificially inflated (missing venues → appears more concentrated)
  - Top 3 venues show 95% share instead of typical 65%
- `finra_otc_transparency_venue_share`:
  - Large venues show inflated market share
  - Mid-tier venues absent from rankings

### What Users See

**Quantitative Analyst:**
- Builds venue selection model using HHI
- Model flags concentrated symbols as "avoid"
- Trading desk misses liquidity opportunities
- Model degradation not attributed to data quality

**Trading Compliance:**
- Best execution analysis shows VNDM dominance
- Incorrectly concludes "routing to VNDM always optimal"
- Overlooks diversification opportunities
- Audit trail shows compliant process, wrong conclusion

### What's Missing for Diagnosis

1. **Historical Baseline Validation:**
   - No automatic comparison to "typical venue count"
   - No anomaly: "45 venues this week vs 150-180 historical avg"
   - System assumes whatever arrives is correct

2. **Quality Metrics Tracking:**
   - Manifest tracks row_count but not venue_count, symbol_count
   - No metrics: distinct_venues, distinct_symbols, total_volume
   - Cannot detect "data present but coverage poor"

3. **Cross-Week Consistency Checks:**
   - No validation: "If symbol traded last week, should trade this week"
   - No warning: "95% of symbols missing this week"
   - Each week processed independently

4. **Calculation Input Validation:**
   - HHI calculation doesn't check: "venue_count abnormally low?"
   - No annotation on results: "Computed from limited venue set"

### Recommended Hardening

**Schema Additions:**
```sql
-- Expand core_quality to track distribution metrics
INSERT INTO core_quality (
    domain, partition_key, 
    check_name, category, status, message,
    actual_value, expected_value,
    details_json,
    execution_id, created_at
) VALUES (
    'finra.otc_transparency',
    '{"week_ending": "2025-12-15", "tier": "NMS_TIER_1"}',
    'venue_count_consistency',
    'COMPLETENESS',
    'WARN',
    'Venue count significantly below historical average',
    '45',
    '150-180',
    '{"historical_p50": 165, "historical_p10": 140, "current": 45}',
    'exec_123',
    '2025-12-16T09:00:00Z'
);

-- Add quality metrics to manifest
ALTER TABLE core_manifest
ADD COLUMN metrics_json TEXT;  -- Store: {"distinct_venues": 45, "distinct_symbols": 2800, ...}
```

**Quality Checks:**
```python
def validate_venue_coverage(week_ending, tier, current_venue_count):
    """Compare to 12-week rolling baseline"""
    baseline = get_historical_venue_count(weeks=12)
    p10, p50, p90 = baseline.quantile([0.1, 0.5, 0.9])
    
    if current_venue_count < p10:
        record_anomaly(
            severity='WARN',
            category='COMPLETENESS',
            message=f'Venue count {current_venue_count} below p10 threshold {p10}',
            actual=current_venue_count,
            expected=f'{p10}-{p90}'
        )
```

---

## Scenario 3: Zero-Volume Anomalies (Business Rule Violation)

### Description

A data pipeline bug or upstream encoding issue causes 150 symbols in week ending 2025-12-08 to have `total_shares = 0` despite `total_trades > 0`. This is logically impossible (trades require share volume).

### What Breaks Today

**Pipeline Behavior:**
- Ingestion succeeds (CSV schema valid)
- Normalization succeeds (no type errors)
- Calculations proceed:
  - `avg_trade_size = 0 / total_trades = 0` (wrong, should be NULL or error)
  - Venue share: `0 / total_symbol_volume = 0.0%` (wrong, denominator inflated)
  - Tier split: includes zero-volume symbols in count but not volume

**Data Artifacts:**
```sql
-- Impossible records present
SELECT week_ending, tier, symbol, mpid, total_shares, total_trades
FROM finra_otc_transparency_normalized
WHERE total_shares = 0 AND total_trades > 0
  AND week_ending = '2025-12-08';

-- 150 rows returned ← business rule violation not caught
```

### What Users See

**Portfolio Manager:**
- Queries liquidity score for affected symbols
- Sees `liquidity_score = 0` (garbage in, garbage out)
- Excludes symbols from tradeable universe
- Loses opportunity or misjudges risk

**Data Scientist:**
- Trains ML model on volume/trade ratios
- Model learns impossible pattern (0 shares, N trades)
- Model degrades on future predictions
- No data quality flag raised

### What's Missing for Diagnosis

1. **Business Rule Validation:**
   - No CHECK constraint: `total_shares = 0 IMPLIES total_trades = 0`
   - No pipeline validation step
   - Garbage data flows to gold layer unchanged

2. **Automatic Anomaly Detection:**
   - No statistical outlier detection
   - No validation: "avg_trade_size within expected range"
   - Historical patterns not compared

3. **Reject vs Warn Strategy:**
   - Should these records be rejected outright?
   - Or normalized with annotation: `is_suspect = 1`?
   - No policy for handling suspect data

4. **Downstream Propagation:**
   - Calculations don't validate inputs
   - No `NULLIF(total_shares, 0)` defensive coding
   - Bad data contaminates aggregates

### Recommended Hardening

**Schema Constraints:**
```sql
-- Add CHECK constraints to enforce business rules
-- (Note: SQLite supports CHECK but enforcement varies by version)
CREATE TABLE finra_otc_transparency_normalized_v2 (
    ...
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    
    -- Business rule: trades require volume
    CHECK (total_trades = 0 OR total_shares > 0)
);
```

**Pipeline Validation:**
```python
def validate_business_rules(df):
    """Catch impossible data before persistence"""
    
    # Rule 1: Trades require volume
    impossible = df[(df['total_trades'] > 0) & (df['total_shares'] == 0)]
    if not impossible.empty:
        record_anomalies(
            domain='finra.otc_transparency',
            severity='ERROR',
            category='BUSINESS_RULE',
            message=f'{len(impossible)} records with trades but zero volume',
            details={'sample_symbols': impossible['symbol'].head(5).tolist()}
        )
        # Decision: Reject or quarantine these records
        raise DataQualityError("Business rule violation: trades without volume")
    
    # Rule 2: Average trade size reasonable (100 - 1M shares)
    df['avg_size'] = df['total_shares'] / df['total_trades']
    outliers = df[(df['avg_size'] < 100) | (df['avg_size'] > 1_000_000)]
    if not outliers.empty:
        record_anomalies(
            domain='finra.otc_transparency',
            severity='WARN',
            category='BUSINESS_RULE',
            message=f'{len(outliers)} records with unusual avg trade size',
            details={'p01': outliers['avg_size'].quantile(0.01), 
                    'p99': outliers['avg_size'].quantile(0.99)}
        )
```

---

## Scenario 4: Late-Arriving Data (Temporal Ordering)

### Description

FINRA publishes week ending 2025-12-22 on Monday 2025-12-23 at 8:00 AM as expected. Platform ingests, normalizes, and computes analytics by 10:00 AM. 

On Wednesday 2025-12-25, FINRA republishes the same week with corrections (updated `source_last_update_date = 2025-12-25`). File contains 200 additional symbols that were omitted in Monday's file.

### What Breaks Today

**Pipeline Behavior:**
- Wednesday ingestion creates new capture_id
- Both Monday and Wednesday captures coexist (correct)
- `_latest` views show Wednesday data (correct)
- **Problem:** Trading desk used Monday's incomplete data for Tuesday trading
- No retroactive notification that Monday's data was incomplete

**User Impact:**
- Tuesday trading decisions made on incomplete analytics
- Wednesday shows different liquidity scores for 200 symbols
- Compliance audit: "Why did symbol XYZ routing change mid-week?"
- No audit trail showing "data corrected after use"

### What Users See

**Trading Desk (Tuesday Morning):**
- Queries liquidity scores from Monday capture
- Makes routing decisions for 2,800 symbols
- No warning: "This data may be revised"

**Trading Desk (Wednesday Morning):**
- Same query now returns 3,000 symbols (200 more)
- Some symbols' scores changed significantly
- Confusion: "Did we miss tradeable symbols yesterday?"

**Audit Team (Thursday):**
- Reviews Tuesday's execution quality
- Compares to Wednesday's analytics
- Asks: "Why didn't we route to venue X for symbol Y on Tuesday?"
- Answer: "Data not available until Wednesday" ← not documented

### What's Missing for Diagnosis

1. **Data Stability Signal:**
   - No flag: "This capture may be preliminary"
   - No SLA: "Data is final after 48h"
   - Users don't know when to trust results

2. **Revision Tracking:**
   - Multiple capture_ids exist, but no explicit "revision sequence"
   - No field: `is_preliminary`, `is_final`, `revision_reason`
   - Cannot distinguish "routine republish" from "correction"

3. **Retroactive Impact Analysis:**
   - When Wednesday capture arrives, no alert:
     - "200 symbols added since last capture"
     - "HHI scores changed for 15 symbols"
     - "Tier splits revised for 50 symbols"
   - No automated impact report

4. **Downstream Notification:**
   - Calculations run on Monday capture
   - Results delivered to users
   - Wednesday capture arrives → calculations re-run
   - **No notification to users who consumed Monday results**

### Recommended Hardening

**Schema Additions:**
```sql
-- Add revision tracking
ALTER TABLE finra_otc_transparency_raw
ADD COLUMN is_preliminary INTEGER DEFAULT 0;

ALTER TABLE finra_otc_transparency_raw
ADD COLUMN revision_sequence INTEGER DEFAULT 1;

-- Track impact of revisions
CREATE TABLE core_data_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    previous_capture_id TEXT NOT NULL,
    new_capture_id TEXT NOT NULL,
    revision_type TEXT NOT NULL,  -- CORRECTION, ADDITION, REMOVAL
    impact_summary TEXT,  -- JSON: {"symbols_added": 200, "symbols_changed": 15}
    detected_at TEXT NOT NULL,
    notified_at TEXT
);
```

**Operational Process:**
```python
def detect_revision_impact(week_ending, tier, previous_capture_id, new_capture_id):
    """Compare two captures and quantify differences"""
    
    prev_symbols = get_symbols(week_ending, tier, previous_capture_id)
    new_symbols = get_symbols(week_ending, tier, new_capture_id)
    
    added = new_symbols - prev_symbols
    removed = prev_symbols - new_symbols
    
    # Compare calculations
    prev_hhi = get_hhi_scores(week_ending, tier, previous_capture_id)
    new_hhi = get_hhi_scores(week_ending, tier, new_capture_id)
    
    significant_changes = [
        s for s in prev_hhi.index 
        if abs(prev_hhi[s] - new_hhi[s]) > 0.05  # 5% threshold
    ]
    
    record_revision(
        domain='finra.otc_transparency',
        partition_key={'week_ending': week_ending, 'tier': tier},
        previous_capture_id=previous_capture_id,
        new_capture_id=new_capture_id,
        revision_type='ADDITION' if added else 'CORRECTION',
        impact_summary={
            'symbols_added': len(added),
            'symbols_removed': len(removed),
            'hhi_scores_changed': len(significant_changes),
            'sample_changes': significant_changes[:5]
        }
    )
    
    # Alert users who consumed previous capture
    if len(added) > 50 or len(significant_changes) > 10:
        notify_users(
            message=f"FINRA OTC {week_ending}/{tier} revised: {len(added)} symbols added, "
                   f"{len(significant_changes)} HHI scores changed significantly"
        )
```

**Readiness Policy:**
```yaml
# Data readiness rules
finra.otc_transparency:
  preliminary_period_hours: 48
  readiness_criteria:
    - all_tiers_present
    - no_critical_anomalies
    - age_hours >= 48  # Don't certify until stabilization window passes
```

---

## Scenario 5: Calendar Corrections After Analytics Ran

### Description

Exchange calendar data for 2025 shows MLK Day (Jan 20) as a holiday. Analytics run on Jan 21 to compute "trading days in January" for normalization factors.

On Jan 25, exchange issues correction: MLK Day was NOT a holiday for OTC markets (they traded). Calendar data revised, but analytics already delivered to users.

### What Breaks Today

**Pipeline Behavior:**
- Jan 21: `reference_exchange_calendar_trading_days` computed with MLK Day as holiday
- Result: January has 20 trading days (wrong, should be 21)
- FINRA analytics normalized by 20 days (understated volume/day)
- Jan 25: Calendar corrected, but analytics not automatically re-triggered
- Two versions of "January 2025 trading days" coexist

**Calculation Impact:**
```sql
-- Volume per trading day calculation
SELECT 
    month,
    total_volume / trading_days as avg_daily_volume
FROM finra_otc_transparency_monthly_summary
WHERE year = 2025 AND month = 1;

-- Using old calendar: avg_daily_volume = total / 20 (overstated)
-- Using new calendar: avg_daily_volume = total / 21 (correct)
```

**Cross-Domain Dependency Failure:**
- FINRA analytics depend on calendar domain
- Calendar correction doesn't trigger FINRA recalculation
- No dependency graph tracking "what analytics use this calendar"

### What Users See

**Risk Manager:**
- Compares January 2025 vs January 2024 trading volume
- Uses published analytics (based on 20 trading days)
- Sees inflated daily average → concludes market more active
- Makes wrong inference about market conditions

**Operations Team:**
- Sees gap in doctor output: "Calendar revised, FINRA not recomputed"
- No automatic remediation
- Manual intervention required but unclear which calcs to rerun

### What's Missing for Diagnosis

1. **Cross-Domain Lineage:**
   - FINRA calcs use calendar data
   - Calendar revision doesn't trigger downstream invalidation
   - No dependency metadata: "If calendar changes, recompute X, Y, Z"

2. **Data Versioning Coordination:**
   - Calendar has capture_id, FINRA has capture_id
   - No linkage: "FINRA capture A used calendar capture B"
   - Cannot identify "analytics based on stale dependencies"

3. **Automatic Invalidation:**
   - When calendar corrected, should FINRA analytics be marked "stale"?
   - Should downstream queries fail with "dependency outdated"?
   - Or annotate: "Based on calendar version X, now superseded by Y"

4. **Recomputation Triggers:**
   - Manual process to identify affected analytics
   - No declarative: "If calendar changes, auto-enqueue FINRA recalc"
   - Operational burden on humans to maintain consistency

### Recommended Hardening

**Schema Additions:**
```sql
-- Track dependencies between calculations
CREATE TABLE core_calc_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calc_domain TEXT NOT NULL,
    calc_pipeline TEXT NOT NULL,
    depends_on_domain TEXT NOT NULL,
    depends_on_table TEXT NOT NULL,
    dependency_type TEXT NOT NULL,  -- REQUIRED, OPTIONAL
    created_at TEXT NOT NULL
);

-- Example:
INSERT INTO core_calc_dependencies VALUES (
    1,
    'finra.otc_transparency',
    'compute_normalized_volume_per_day',
    'reference.exchange_calendar',
    'reference_exchange_calendar_trading_days',
    'REQUIRED',
    '2025-01-01T00:00:00Z'
);

-- Track which dependency versions were used
ALTER TABLE finra_otc_transparency_normalized_volume_per_day
ADD COLUMN calendar_capture_id TEXT;  -- Links to specific calendar version
```

**Invalidation Logic:**
```python
def on_calendar_revision(domain, partition_key, new_capture_id):
    """When calendar is corrected, find affected downstream calcs"""
    
    # Find all calcs that depend on this calendar
    affected = db.execute("""
        SELECT calc_domain, calc_pipeline
        FROM core_calc_dependencies
        WHERE depends_on_domain = ?
    """, (domain,))
    
    for calc_domain, calc_pipeline in affected:
        # Record anomaly
        record_anomaly(
            domain=calc_domain,
            pipeline=calc_pipeline,
            severity='WARN',
            category='STALE_DEPENDENCY',
            message=f'Dependency {domain} revised. This calc may be outdated.',
            detected_at=datetime.now()
        )
        
        # Optionally: Auto-enqueue recalculation
        if config.auto_recompute_on_dependency_change:
            enqueue_work(
                domain=calc_domain,
                pipeline=calc_pipeline,
                partition_key=partition_key,
                reason=f'Dependency {domain} updated'
            )
```

**Readiness Check:**
```python
def check_dependency_freshness(calc_domain, calc_pipeline, partition_key):
    """Verify all dependencies are current"""
    
    dependencies = get_dependencies(calc_domain, calc_pipeline)
    
    for dep in dependencies:
        # Get capture_id used by this calc
        calc_dep_version = get_calc_dependency_version(
            calc_domain, calc_pipeline, partition_key, dep.domain
        )
        
        # Get latest capture_id available for dependency
        latest_dep_version = get_latest_capture_id(
            dep.domain, partition_key
        )
        
        if calc_dep_version != latest_dep_version:
            return ReadinessResult(
                ready=False,
                reason=f'Dependency {dep.domain} outdated. '
                       f'Calc uses {calc_dep_version}, latest is {latest_dep_version}'
            )
    
    return ReadinessResult(ready=True)
```

---

## Summary: Common Themes

### What's Missing Across All Scenarios

1. **Proactive Anomaly Detection:**
   - Historical baseline comparisons
   - Business rule validation
   - Statistical outlier detection
   - Cross-domain consistency checks

2. **Completeness vs Correctness:**
   - System tracks "data arrived" but not "all expected data arrived"
   - No concept of "expected partition set"
   - Partial success treated as full success

3. **Quality Annotations:**
   - Results don't carry quality flags
   - Users can't distinguish:
     - Complete vs incomplete
     - Preliminary vs final
     - Current vs superseded

4. **Cross-Domain Dependencies:**
   - Calculations use other data sources
   - No automatic invalidation on upstream changes
   - Manual effort to maintain consistency

5. **User Notification:**
   - Data revisions don't trigger alerts
   - Analytics consumers not notified of corrections
   - No audit trail of "who used outdated data when"

### Hardening Priorities

**Tier 1 (Must Have):**
- Anomaly persistence (`core_anomalies` table)
- Partition completeness checks
- Business rule validation
- Quality metrics in manifest

**Tier 2 (Should Have):**
- Revision tracking and impact analysis
- Dependency graph with invalidation
- Readiness certification with completeness criteria
- User notification on data corrections

**Tier 3 (Nice to Have):**
- Automatic recomputation on dependency changes
- ML-based anomaly detection
- Advanced lineage tracking
- Predictive quality scoring

These scenarios will guide the implementation of institutional-grade hardening measures in the following sections.
