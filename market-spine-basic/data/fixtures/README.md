# FINRA OTC Test Fixtures

This directory contains test data files for validating the multi-week scheduler and data quality checks.

## Directory Structure

```
data/fixtures/
└── finra_otc/
    ├── nms_tier_1_week_YYYY-MM-DD.psv
    ├── nms_tier_2_week_YYYY-MM-DD.psv
    └── otc_week_YYYY-MM-DD.psv
```

## Test Scenarios

### Week 2026-01-02 (Most Recent) - ✅ NORMAL DATA
- **All tiers:** Clean, valid data with proper formatting
- **Purpose:** Baseline for successful ingestion
- **Expected behavior:** Should ingest without errors

### Week 2025-12-26 - ⚠️ VARIOUS DATA QUALITY ISSUES

#### NMS Tier 1 - Duplicate Rows
- Contains duplicate records for AAPL/NASDAQ, GOOGL/NYSE, NVDA/NYSE
- **Expected validation:** Should detect and report duplicates
- **Expected behavior:** May fail validation or deduplicate

#### NMS Tier 2 - Missing Required Fields
- Missing values in TotalWeeklyShareVolume, TotalWeeklyTrades, AverageTradeSize columns
- Missing Venue for UBER row
- **Expected validation:** Should detect missing required fields
- **Expected behavior:** May skip invalid rows or fail validation

#### OTC - Zero Volume Anomalies
- ABCD/OTC_PINK: Zero volume and trades
- EFGH/OTC_QB: Zero volume despite trades
- MNOP/OTC_PINK: Zero trades despite volume
- **Expected validation:** Should flag zero-value anomalies
- **Expected behavior:** Should record anomalies in core_anomalies table

### Week 2025-12-19 - 🔴 SEVERE DATA ISSUES

#### NMS Tier 1 - Malformed Data
- Contains rows with comma delimiters instead of pipes
- **Expected validation:** Should fail parsing
- **Expected behavior:** May skip malformed rows or fail file

#### NMS Tier 2 - Partial Venue Coverage
- Missing ZM/NYSE, TWTR/NYSE, LYFT/CBOE, PINS/NASDAQ
- Incomplete venue distribution per symbol
- **Expected validation:** May flag coverage gaps
- **Expected behavior:** Should ingest available data

#### OTC - Incomplete File
- File truncated mid-row (MNOP/OTC_QB incomplete)
- **Expected validation:** Should detect incomplete records
- **Expected behavior:** May fail parsing or skip last row

### Week 2025-12-12 (Oldest) - 🔴 EXTREME VALUES

#### NMS Tier 1 - Outliers and Invalid Values
- AAPL/NASDAQ: Extreme values (999 billion shares)
- MSFT/NYSE: Suspiciously low values (1 share, 1 trade)
- TSLA/NASDAQ: Negative volume (-50M)
- **Expected validation:** Should flag outliers, reject negative values
- **Expected behavior:** May fail validation or record anomalies

#### NMS Tier 2 - Invalid Date Formats
- Multiple date format variations: "12/12/2025", "Dec 12, 2025", "2025/12/12"
- **Expected validation:** Should fail date parsing
- **Expected behavior:** May skip rows with invalid dates

#### OTC - Good Data
- Clean data for comparison with other problematic weeks
- **Expected validation:** Should pass all checks
- **Expected behavior:** Should ingest successfully

## File Format

All files use pipe-separated values (PSV) with the following schema:

```
Symbol|Venue|Date|TotalWeeklyShareVolume|TotalWeeklyTrades|AverageDailyShareVolume|AverageTradeSize
```

### Field Descriptions

- **Symbol:** Stock ticker symbol (e.g., AAPL, MSFT)
- **Venue:** Trading venue (NASDAQ, NYSE, CBOE, IEX, OTC_PINK, OTC_QB)
- **Date:** Week ending date in ISO format (YYYY-MM-DD)
- **TotalWeeklyShareVolume:** Total shares traded during the week
- **TotalWeeklyTrades:** Total number of trades during the week
- **AverageDailyShareVolume:** Average shares traded per day
- **AverageTradeSize:** Average shares per trade

## Testing the Scheduler

### Test with All Weeks (Including Problematic Data)

```bash
# Dry run to see what would be processed
python scripts/run_finra_weekly_schedule.py \
  --lookback-weeks 4 \
  --source file \
  --mode dry-run \
  --verbose

# Actual run (will encounter validation errors)
python scripts/run_finra_weekly_schedule.py \
  --lookback-weeks 4 \
  --source file \
  --mode run \
  --verbose
```

### Test with Specific Weeks

```bash
# Only good weeks (2026-01-02, 2025-12-12 OTC)
python scripts/run_finra_weekly_schedule.py \
  --weeks 2026-01-02,2025-12-12 \
  --tiers OTC \
  --source file \
  --mode run \
  --verbose

# Only problematic week (test error handling)
python scripts/run_finra_weekly_schedule.py \
  --weeks 2025-12-19 \
  --source file \
  --mode run \
  --verbose
```

### Test Revision Detection

```bash
# First run: Ingest all 4 weeks
python scripts/run_finra_weekly_schedule.py --lookback-weeks 4 --source file --mode run

# Second run: Should skip all unchanged weeks (revision detection)
python scripts/run_finra_weekly_schedule.py --lookback-weeks 4 --source file --mode run

# Modify a file, then run again: Should re-ingest only changed week
# (Edit data/fixtures/finra_otc/nms_tier_1_week_2026-01-02.psv)
python scripts/run_finra_weekly_schedule.py --lookback-weeks 4 --source file --mode run
```

## Expected Outcomes

### Successful Ingestion
- Week 2026-01-02 (all tiers)
- Week 2025-12-12 (OTC tier)

### Partial Success with Anomalies
- Week 2025-12-26 (NMS Tier 2, OTC) - Should record anomalies for missing data and zero volumes

### Likely Failures
- Week 2025-12-26 (NMS Tier 1) - Duplicates
- Week 2025-12-19 (NMS Tier 1) - Malformed delimiter
- Week 2025-12-19 (OTC) - Incomplete file
- Week 2025-12-12 (NMS Tier 1) - Negative values, extreme outliers
- Week 2025-12-12 (NMS Tier 2) - Invalid date formats

## Validation Monitoring

Check the anomalies table after running:

```sql
SELECT 
    domain,
    severity,
    category,
    message,
    COUNT(*) as count
FROM core_anomalies
WHERE domain = 'finra.otc_transparency'
GROUP BY domain, severity, category, message
ORDER BY severity DESC, count DESC;
```

Check capture history:

```sql
SELECT 
    capture_id,
    source,
    status,
    row_count,
    created_at
FROM core_manifest
WHERE domain = 'finra.otc_transparency'
ORDER BY created_at DESC
LIMIT 20;
```
