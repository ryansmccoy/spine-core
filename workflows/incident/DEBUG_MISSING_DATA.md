# Debug Missing Data Workflow

**Type:** Incident Response  
**Severity:** P2 (Data unavailable)  
**Owner:** On-call engineer

---

## Trigger

- Dashboard shows no data for expected week
- Query returns empty results
- Readiness check fails

---

## Diagnostic Steps

### 1. Identify Missing Partition

```sql
-- Check what's missing
SELECT 
    d.expected_week,
    d.expected_tier,
    CASE WHEN m.id IS NULL THEN 'MISSING' ELSE 'PRESENT' END as status
FROM (
    -- Expected partitions
    VALUES 
        ('2026-01-09', 'NMS_TIER_1'),
        ('2026-01-09', 'NMS_TIER_2'),
        ('2026-01-09', 'OTC')
) d(expected_week, expected_tier)
LEFT JOIN core_manifest m 
    ON m.partition_key = d.expected_week || '|' || d.expected_tier
    AND m.domain = 'finra.otc_transparency'
WHERE m.id IS NULL;
```

### 2. Check Scheduler Logs

**Search for errors:**
```bash
# If using systemd
journalctl -u market-spine-weekly -n 100 | grep ERROR

# Or check script output
grep "ERROR\|CRITICAL" /var/log/market-spine/weekly_*.log
```

### 3. Check Anomalies

```sql
SELECT 
    partition_key,
    stage,
    severity,
    category,
    message,
    detected_at
FROM core_anomalies
WHERE partition_key LIKE '2026-01-09%'
  AND resolved_at IS NULL
ORDER BY severity DESC, detected_at DESC;
```

---

## Common Root Causes

### Cause 1: Source File Missing

**Symptoms:**
- Anomaly: "Fetch failed: File not found"
- Stage: RAW

**Fix:**
```bash
# Check if file exists
ls data/fixtures/finra_otc/*2026-01-09*

# If missing, create or download
# Then re-run ingest
python scripts/run_finra_weekly_schedule.py \
  --weeks 2026-01-09 \
  --only-stage ingest
```

### Cause 2: Quality Gate Failure

**Symptoms:**
- Anomaly: "Insufficient history: missing weeks"
- Stage: ROLLING or calculations

**Fix:**
```sql
-- Check history completeness
SELECT DISTINCT week_ending
FROM finra_otc_transparency_symbol_summary
WHERE week_ending >= '2025-12-01'
ORDER BY week_ending DESC;
```

If gaps exist, backfill missing weeks:
```bash
python scripts/run_finra_weekly_schedule.py \
  --weeks 2025-12-12,2025-12-19,2025-12-26
```

### Cause 3: Pipeline Failure

**Symptoms:**
- Anomaly: severity=CRITICAL, category=PROCESSING
- Specific partition missing

**Fix:**
```bash
# Re-run specific partition
python scripts/run_finra_weekly_schedule.py \
  --weeks 2026-01-09 \
  --tiers NMS_TIER_1 \
  --force  # Ignore revision detection
```

### Cause 4: Readiness Not Updated

**Symptoms:**
- Data exists in manifest
- But `is_ready = 0`

**Fix:**
```sql
-- Check readiness blocker
SELECT 
    partition_key,
    is_ready,
    all_partitions_present,
    all_stages_complete,
    no_critical_anomalies,
    blocking_issues
FROM core_data_readiness
WHERE partition_key LIKE '2026-01-09%';

-- If false positive, manually mark ready
UPDATE core_data_readiness
SET is_ready = 1,
    blocking_issues = NULL,
    updated_at = datetime('now')
WHERE partition_key = '2026-01-09|NMS_TIER_1';
```

---

## Resolution Steps

### Step 1: Fix Root Cause

Use appropriate fix from above based on root cause.

### Step 2: Verify Data Present

```sql
-- Check manifest
SELECT COUNT(*) FROM core_manifest
WHERE partition_key LIKE '2026-01-09%'
  AND domain = 'finra.otc_transparency';
-- Expect: 3 (one per tier) or more

-- Check actual data
SELECT COUNT(*) FROM finra_otc_transparency_venue_volume
WHERE week_ending = '2026-01-09';
-- Expect: > 0
```

### Step 3: Mark Anomaly Resolved

```sql
UPDATE core_anomalies
SET resolved_at = datetime('now'),
    resolution_note = 'Re-ran ingestion, data now present'
WHERE partition_key LIKE '2026-01-09%'
  AND resolved_at IS NULL;
```

### Step 4: Verify Downstream

```bash
# Re-run calculations to propagate fix
python scripts/run_finra_weekly_schedule.py \
  --weeks 2026-01-09 \
  --only-stage calc
```

---

## Verification

```sql
-- Final check: all green
SELECT 
    partition_key,
    is_ready,
    updated_at
FROM core_data_readiness
WHERE partition_key LIKE '2026-01-09%';
-- Expect: All rows is_ready = 1
```

---

## Post-Incident

1. **Document:** Update incident log with root cause
2. **Prevent:** Add monitoring for this failure mode
3. **Alert:** Set up alert if pattern repeats

---

## References

- **Weekly Update:** `workflows/operational/WEEKLY_DATA_UPDATE.md`
- **Backfill:** `workflows/operational/BACKFILL_HISTORICAL.md`
- **Revision Handling:** `docs/FINRA_REVISION_HANDLING.md`
