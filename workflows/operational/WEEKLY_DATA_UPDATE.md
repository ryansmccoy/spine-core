# Weekly Data Update Workflow

**Type:** Operational  
**Frequency:** Weekly (every Friday after FINRA publishes)  
**Duration:** ~15 minutes  
**Owner:** Data Operations

---

## Trigger

Run this workflow every Friday after FINRA publishes OTC transparency data (typically by 8 AM ET).

---

## Prerequisites

- [ ] Access to production database
- [ ] FINRA data available (check finra.org or fixture files)
- [ ] Python environment configured
- [ ] No ongoing incidents

---

## Steps

### 1. Check FINRA Data Availability

**Verify new week published:**
```bash
# Check FINRA website or use test fixture
ls data/fixtures/finra_otc/
```

### 2. Run Weekly Scheduler (Standard Mode)

**Command:**
```bash
python scripts/run_finra_weekly_schedule.py \
  --lookback-weeks 6 \
  --source file \
  --verbose
```

**What it does:**
- Processes last 6 weeks (to catch FINRA revisions)
- Uses revision detection (skips unchanged weeks)
- Runs: Ingest → Normalize → Calculate
- Updates data readiness flags

**Expected duration:** 5-10 minutes

### 3. Monitor Execution

**Watch for:**
- ✓ Green checkmarks = success
- ⚠ Yellow warnings = partial success (some symbols skipped)
- ✗ Red errors = partition failed

**Example output:**
```
[INFO]      === Phase 1: Ingestion ===
[INFO]      2026-01-09 / NMS_TIER_1: ✓ Ingested (NEW)
[INFO]      2026-01-09 / NMS_TIER_2: → Skipped (unchanged)
```

### 4. Verify Summary Statistics

**Check final summary:**
```
SUMMARY
======================================================================
Weeks processed:      6
Total partitions:     18 (6 weeks × 3 tiers)

Ingestion:
  Ingested:           3
  Skipped (unchanged): 14
  Failed:             1  ← INVESTIGATE IF > 0
```

### 5. Review Data Readiness

**Query readiness status:**
```sql
SELECT 
    partition_key,
    is_ready,
    blocking_issues,
    updated_at
FROM core_data_readiness
WHERE domain = 'finra.otc_transparency'
  AND partition_key LIKE '2026-01%'
ORDER BY partition_key DESC;
```

**Expected:** `is_ready = 1` for all current week partitions

### 6. Check for Anomalies

**Query unresolved issues:**
```sql
SELECT 
    severity,
    category,
    partition_key,
    message,
    detected_at
FROM core_anomalies
WHERE domain = 'finra.otc_transparency'
  AND resolved_at IS NULL
  AND severity IN ('ERROR', 'CRITICAL')
ORDER BY detected_at DESC
LIMIT 20;
```

**Expected:** No CRITICAL anomalies for current week

---

## Success Criteria

- [ ] All 3 tiers ingested or skipped (no failures)
- [ ] Current week marked `is_ready = 1`
- [ ] No CRITICAL anomalies for current week
- [ ] Calculations ran successfully

---

## Common Issues

### Issue: "Fetch failed: File not found"

**Cause:** Fixture file missing for this week  
**Fix:** 
```bash
# Check if FINRA published yet
# Or create fixture file if using test data
```

### Issue: "RAW stage missing, skipping normalize"

**Cause:** Ingestion failed for this tier  
**Fix:** Re-run ingestion for that specific tier:
```bash
python scripts/run_finra_weekly_schedule.py \
  --weeks 2026-01-09 \
  --tiers NMS_TIER_1 \
  --only-stage ingest
```

### Issue: "Missing tiers [...], skipping calcs"

**Cause:** Not all tiers normalized yet  
**Fix:** Complete normalization first:
```bash
python scripts/run_finra_weekly_schedule.py \
  --weeks 2026-01-09 \
  --only-stage normalize
```

---

## Rollback

**If data is bad:**
```sql
-- Delete captures for bad week
DELETE FROM core_manifest
WHERE domain = 'finra.otc_transparency'
  AND partition_key LIKE '2026-01-09%';

-- Mark as not ready
UPDATE core_data_readiness
SET is_ready = 0,
    blocking_issues = 'Manual rollback - bad data'
WHERE partition_key LIKE '2026-01-09%';
```

Then re-run scheduler with `--force` flag.

---

## References

- **Script:** `scripts/run_finra_weekly_schedule.py`
- **Init DB:** `scripts/init_database.py`
- **CLI Docs:** `docs/CLI.md`
- **Revision Handling:** `docs/FINRA_REVISION_HANDLING.md`

---

## Monitoring Dashboard Queries

**Weekly completeness trend:**
```sql
SELECT 
    substr(partition_key, 1, 10) as week,
    COUNT(*) as total_partitions,
    SUM(is_ready) as ready_partitions
FROM core_data_readiness
WHERE domain = 'finra.otc_transparency'
GROUP BY week
ORDER BY week DESC
LIMIT 8;
```

**Anomaly rate by week:**
```sql
SELECT 
    substr(partition_key, 1, 10) as week,
    COUNT(*) as anomaly_count,
    SUM(CASE WHEN severity = 'CRITICAL' THEN 1 ELSE 0 END) as critical_count
FROM core_anomalies
WHERE domain = 'finra.otc_transparency'
  AND resolved_at IS NULL
GROUP BY week
ORDER BY week DESC;
```
