# History Window Quality Gate Implementation

## Overview

Implemented a quality gate for rolling-window calculations to ensure sufficient historical data exists before computing rolling averages. This prevents incomplete or misleading calculations when data history is sparse.

## Components Implemented

### 1. Helper Functions (validators.py)

**`require_history_window(conn, table, week_ending, window_weeks, tier, symbol, check_readiness)`**
- Validates that N distinct weeks exist in the source table
- Optionally checks core_data_readiness for each week
- Returns `(ok: bool, missing_weeks: list[str])`
- Logs warnings when history is insufficient

**`get_symbols_with_sufficient_history(conn, table, week_ending, window_weeks, tier)`**
- Returns set of symbols that have complete history windows
- Used for per-symbol quality filtering in rolling calculations
- Enables partial computation (skip symbols with gaps, compute others)

### 2. Rolling Pipeline Updates (pipelines.py)

**Quality Gates Added:**
1. **Tier-level gate**: Check if the tier has 6 weeks of data
   - If insufficient: Record ERROR anomaly, skip entire tier, return early
2. **Symbol-level gate**: Filter symbols with insufficient history
   - Compute rolling metrics only for symbols with 6+ weeks
   - Record WARN anomaly listing skipped symbolsa

**Anomaly Recording:**
```python
severity="ERROR" -> Entire tier skipped
severity="WARN"  -> Partial coverage (some symbols skipped)
```

**Metrics Enhanced:**
```python
{
    "symbols_computed": count,
    "symbols_skipped": len(skipped_symbols),
    "capture_id": output_capture_id
}
```

### 3. SQL Views (views.py)

**`finra_otc_transparency_rolling_6w_avg_symbol_volume_latest`**
- Latest rolling data (one row per week/tier/symbol)
- **Quality gate:** `WHERE is_complete = 1`
- Only surfaces rows with full 6-week window

**`finra_otc_transparency_rolling_6w_clean`**
- Latest rolling data excluding weeks with unresolved errors
- Joins with core_anomalies to filter out error states
- Production-ready view for analytics

**`finra_otc_transparency_rolling_6w_stats`**
- Aggregated completeness metrics per week/tier
- Shows: total_symbols, complete_symbols, incomplete_symbols, completeness_pct
- Useful for monitoring data quality trends

### 4. Comprehensive Tests (test_rolling_quality_gate.py)

**Test Coverage:**
- ✅ `test_require_history_window_sufficient` - 6 weeks exist → passes
- ✅ `test_require_history_window_insufficient` - Only 3 weeks → fails, returns missing weeks
- ✅ `test_get_symbols_with_sufficient_history` - Filters symbols by history
- ✅ `test_require_history_window_with_readiness_check` - Validates readiness flags
- ✅ `test_rolling_calculation_deterministic` - Same inputs → same outputs
- ✅ `test_rolling_idempotency_same_capture` - Rerun with same capture_id is idempotent
- ✅ `test_rolling_new_capture_coexists` - New capture_id creates separate records

All tests pass ✅

## Usage Examples

### Basic Validation
```python
from spine.domains.finra.otc_transparency.validators import require_history_window

ok, missing = require_history_window(
    conn,
    table="finra_otc_transparency_symbol_summary",
    week_ending=date(2026, 1, 9),
    window_weeks=6,
    tier="NMS_TIER_1",
    symbol="AAPL"
)

if not ok:
    print(f"Insufficient history. Missing weeks: {missing}")
```

### Get Valid Symbols
```python
valid_symbols = get_symbols_with_sufficient_history(
    conn,
    table="finra_otc_transparency_symbol_summary",
    week_ending=date(2026, 1, 9),
    window_weeks=6,
    tier="NMS_TIER_1"
)
# Returns: {"AAPL", "MSFT", "GOOGL"} - only symbols with 6+ weeks
```

### Query Latest Rolling Data
```sql
-- Get latest rolling averages (only complete windows)
SELECT * FROM finra_otc_transparency_rolling_6w_avg_symbol_volume_latest
WHERE week_ending = '2026-01-09'
  AND tier = 'NMS_TIER_1'
ORDER BY symbol;

-- Get clean data (no unresolved errors)
SELECT * FROM finra_otc_transparency_rolling_6w_clean
WHERE week_ending = '2026-01-09';

-- Monitor completeness
SELECT * FROM finra_otc_transparency_rolling_6w_stats
WHERE week_ending >= '2025-12-01'
ORDER BY week_ending DESC, tier;
```

### Create Views in Database
```python
from spine.domains.finra.otc_transparency.views import create_views

conn = get_connection()
create_views(conn)  # Creates all 3 views
```

## Behavior Changes

### Before (No Quality Gate)
- Rolling calculations run even with 1 week of data
- Produces misleading "6-week average" from 1-2 weeks
- No visibility into data completeness
- Silent failures

### After (With Quality Gate)
- **Tier insufficient**: Skip entire tier, record ERROR anomaly
- **Symbol insufficient**: Skip symbol, record WARN anomaly, compute others
- **All sufficient**: Compute normally, set `is_complete=1`
- **Views**: Only surface complete, error-free data

## Metrics & Monitoring

### Check Anomalies
```sql
SELECT 
    severity,
    category,
    message,
    COUNT(*) as count
FROM core_anomalies
WHERE domain = 'finra.otc_transparency'
  AND stage = 'ROLLING'
  AND resolved_at IS NULL
GROUP BY severity, category, message;
```

### Monitor Completeness Trend
```sql
SELECT 
    week_ending,
    tier,
    completeness_pct,
    total_symbols,
    complete_symbols
FROM finra_otc_transparency_rolling_6w_stats
WHERE week_ending >= '2025-11-01'
ORDER BY week_ending DESC, tier;
```

## Edge Cases Handled

1. **Partial week coverage**: Some symbols have 6 weeks, others have 3
   - ✅ Compute for valid symbols, skip others, record WARN
2. **No data at all**: Tier completely empty
   - ✅ Skip tier, record ERROR, return early
3. **Exactly 6 weeks**: Boundary condition
   - ✅ Passes validation, computes normally
4. **Multiple captures**: Historical restatements
   - ✅ Uses latest capture per week, coexists peacefully
5. **Readiness not set**: core_data_readiness empty
   - ✅ Optional check, can skip readiness validation

## Performance Considerations

- **Symbol filtering**: Single query with GROUP BY + HAVING
- **Window weeks**: Parameterized IN clause (6 values)
- **View materialization**: Consider materializing stats view for dashboards
- **Index recommendation**:
  ```sql
  CREATE INDEX idx_symbol_summary_week_tier_symbol 
    ON finra_otc_transparency_symbol_summary(week_ending, tier, symbol);
  ```

## Future Enhancements

1. **Configurable window size**: Pass window_weeks as pipeline param
2. **Degraded mode**: Compute with partial window if > threshold (e.g., 4/6 weeks)
3. **Alerting integration**: Webhook to PagerDuty when ERROR anomalies occur
4. **Historical backfill**: Batch job to recompute all weeks with quality gate
5. **Dashboard**: Grafana panel showing completeness_pct over time

## Files Modified

- ✅ `src/spine/domains/finra/otc_transparency/validators.py` (NEW - 200 lines)
- ✅ `src/spine/domains/finra/otc_transparency/pipelines.py` (UPDATED - added quality gate)
- ✅ `src/spine/domains/finra/otc_transparency/views.py` (NEW - 90 lines)
- ✅ `tests/finra/otc_transparency/test_rolling_quality_gate.py` (NEW - 400 lines)

## Testing

```bash
# Run quality gate tests
pytest tests/finra/otc_transparency/test_rolling_quality_gate.py -v

# Run full domain tests
pytest tests/finra/otc_transparency/ -v

# With coverage
pytest tests/finra/otc_transparency/test_rolling_quality_gate.py --cov=spine.domains.finra.otc_transparency.validators --cov-report=term-missing
```

## Summary

✅ Implemented history window quality gate with:
- 2 helper functions for validation
- Tier-level and symbol-level filtering
- Comprehensive anomaly recording
- 3 SQL views for production use
- 7 passing tests covering all scenarios

The rolling calculation pipeline now ensures data quality by rejecting incomplete windows, providing clear visibility into data gaps, and enabling partial computation where appropriate.
