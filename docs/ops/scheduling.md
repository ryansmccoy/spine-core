# Operational Scheduling Guide

## Overview

This document describes how to run Market Spine pipelines on a schedule (cron, Kubernetes CronJob, cloud scheduler) for production weekly data processing. No heavyweight orchestration framework (Airflow, Prefect) is required—Market Spine's built-in work queue and manifest tracking provide sufficient operational primitives.

## Architecture

```
┌─────────────────┐
│  Cron / K8s     │  Triggers API calls on schedule
│  CronJob        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Market Spine   │  POST /api/v1/work/enqueue
│  API            │  GET  /api/v1/work/pending
└────────┬────────┘  POST /api/v1/work/retry
         │
         ▼
┌─────────────────┐
│  core_work_     │  State: PENDING → RUNNING → COMPLETE
│  items          │  Failures → RETRY_WAIT → PENDING (with backoff)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Pipelines      │  ingest_week → normalize_week → compute_*
│  Execute        │
└─────────────────┘
```

## Weekly FINRA OTC Pipeline Flow

### Standard Weekly Cadence

FINRA publishes weekly OTC data every Monday morning. The standard flow:

1. **Monday 10:00 AM** - FINRA data available at finra.org
2. **Monday 10:30 AM** - Cron triggers ingestion for all 3 tiers
3. **Monday 10:35 AM** - Normalization runs (after ingest completes)
4. **Monday 10:40 AM** - Analytics calculations run
5. **Monday 10:45 AM** - Data available for trading desks via API/SQL

### Pipeline Execution Order

```bash
# Week ending 2025-12-22 processing (3 tiers in parallel)

# Phase 1: Ingest raw CSVs (can run in parallel)
POST /api/v1/work/enqueue {
  "domain": "finra.otc_transparency",
  "pipeline": "ingest_week",
  "partition_key": {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"},
  "params": {"file_url": "https://finra.org/.../tier1_20251222.csv"},
  "desired_at": "2025-12-23T10:30:00Z"
}

POST /api/v1/work/enqueue {
  "domain": "finra.otc_transparency",
  "pipeline": "ingest_week",
  "partition_key": {"week_ending": "2025-12-22", "tier": "NMS_TIER_2"},
  "params": {"file_url": "https://finra.org/.../tier2_20251222.csv"},
  "desired_at": "2025-12-23T10:30:00Z"
}

POST /api/v1/work/enqueue {
  "domain": "finra.otc_transparency",
  "pipeline": "ingest_week",
  "partition_key": {"week_ending": "2025-12-22", "tier": "OTC"},
  "params": {"file_url": "https://finra.org/.../otc_20251222.csv"},
  "desired_at": "2025-12-23T10:30:00Z"
}

# Phase 2: Normalize (depends on ingest, can run in parallel per tier)
POST /api/v1/work/enqueue {
  "domain": "finra.otc_transparency",
  "pipeline": "normalize_week",
  "partition_key": {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"},
  "desired_at": "2025-12-23T10:35:00Z"
}

# ... repeat for TIER_2, OTC

# Phase 3: Compute analytics (depends on normalize)
POST /api/v1/work/enqueue {
  "domain": "finra.otc_transparency",
  "pipeline": "compute_venue_volume",
  "partition_key": {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"},
  "desired_at": "2025-12-23T10:40:00Z"
}

POST /api/v1/work/enqueue {
  "domain": "finra.otc_transparency",
  "pipeline": "compute_venue_share",
  "partition_key": {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"},
  "desired_at": "2025-12-23T10:40:00Z"
}

# ... etc for HHI, tier_split
```

## Cron Schedule Examples

### Option 1: Simple Bash Script (Linux/macOS)

```bash
#!/bin/bash
# /opt/market-spine/cron/weekly_finra.sh

# Run every Monday at 10:30 AM
# Crontab: 30 10 * * 1 /opt/market-spine/cron/weekly_finra.sh

API_BASE="http://localhost:8000/api/v1"
WEEK_ENDING=$(date -d "last Friday" +%Y-%m-%d)

# Enqueue ingestion for all 3 tiers
for tier in NMS_TIER_1 NMS_TIER_2 OTC; do
  curl -X POST "$API_BASE/work/enqueue" \
    -H "Content-Type: application/json" \
    -d "{
      \"domain\": \"finra.otc_transparency\",
      \"pipeline\": \"ingest_week\",
      \"partition_key\": {\"week_ending\": \"$WEEK_ENDING\", \"tier\": \"$tier\"},
      \"params\": {\"tier\": \"$tier\"},
      \"desired_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }"
done

# Wait 5 minutes for ingestion
sleep 300

# Enqueue normalization
for tier in NMS_TIER_1 NMS_TIER_2 OTC; do
  curl -X POST "$API_BASE/work/enqueue" \
    -H "Content-Type: application/json" \
    -d "{
      \"domain\": \"finra.otc_transparency\",
      \"pipeline\": \"normalize_week\",
      \"partition_key\": {\"week_ending\": \"$WEEK_ENDING\", \"tier\": \"$tier\"},
      \"desired_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }"
done

# Wait 5 minutes for normalization
sleep 300

# Enqueue analytics
for calc in compute_venue_volume compute_venue_share compute_hhi compute_tier_split; do
  curl -X POST "$API_BASE/work/enqueue" \
    -H "Content-Type: application/json" \
    -d "{
      \"domain\": \"finra.otc_transparency\",
      \"pipeline\": \"$calc\",
      \"partition_key\": {\"week_ending\": \"$WEEK_ENDING\"},
      \"desired_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }"
done

echo "Enqueued FINRA OTC pipeline for week ending $WEEK_ENDING"
```

### Option 2: Kubernetes CronJob

```yaml
# k8s/cronjobs/finra-weekly.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: finra-otc-weekly-ingest
  namespace: market-spine
spec:
  schedule: "30 10 * * 1"  # Every Monday at 10:30 AM UTC
  timeZone: "America/New_York"
  successfulJobsHistoryLimit: 5
  failedJobsHistoryLimit: 3
  concurrencyPolicy: Forbid  # Don't overlap runs
  
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: enqueue-finra
            image: market-spine/scheduler:latest
            env:
            - name: API_BASE_URL
              value: "http://market-spine-api:8000/api/v1"
            - name: WEEK_OFFSET
              value: "-7"  # Previous week
            command:
            - /bin/bash
            - -c
            - |
              set -e
              WEEK_ENDING=$(date -d "last Friday" +%Y-%m-%d)
              
              # Enqueue all work items
              python /scripts/enqueue_weekly_finra.py \
                --week-ending "$WEEK_ENDING" \
                --api-base "$API_BASE_URL"
              
              echo "✓ Enqueued FINRA pipeline for $WEEK_ENDING"
```

### Option 3: PowerShell (Windows Task Scheduler)

```powershell
# scripts/Schedule-WeeklyFINRA.ps1

$ApiBase = "http://localhost:8000/api/v1"
$WeekEnding = (Get-Date).AddDays(-((Get-Date).DayOfWeek.value__ + 2)).ToString("yyyy-MM-dd")

$Tiers = @("NMS_TIER_1", "NMS_TIER_2", "OTC")

foreach ($Tier in $Tiers) {
    $Body = @{
        domain = "finra.otc_transparency"
        pipeline = "ingest_week"
        partition_key = @{
            week_ending = $WeekEnding
            tier = $Tier
        }
        params = @{ tier = $Tier }
        desired_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json -Depth 10

    Invoke-RestMethod -Uri "$ApiBase/work/enqueue" -Method POST -Body $Body -ContentType "application/json"
}

Write-Host "✓ Enqueued FINRA OTC pipeline for week ending $WeekEnding"
```

## Idempotency Guarantees

### Safe to Re-run

All pipelines are idempotent via capture_id:

```sql
-- Same capture_id → exact same results
capture_id = "{domain}:{tier}:{week_ending}:{YYYYMMDD}"

-- Example:
"finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223"
```

**What happens on re-run:**
1. Same `capture_id` is generated (based on date)
2. Existing rows with that `capture_id` are **replaced** (UPSERT)
3. Row counts remain identical
4. Latest views automatically point to most recent capture

**Safe operations:**
- Re-ingesting same week/tier with same source file → identical rows
- Re-normalizing → same capture_id, same output
- Re-computing calcs → deterministic results

**Restatements (intentional):**
- New capture on different date → new `capture_id`
- Both captures coexist in database
- Latest views show new capture
- As-of queries can retrieve old capture

## Backfilling

### Single Week

```bash
# Backfill week ending 2025-11-01
curl -X POST http://localhost:8000/api/v1/work/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "finra.otc_transparency",
    "pipeline": "ingest_week",
    "partition_key": {"week_ending": "2025-11-01", "tier": "NMS_TIER_1"},
    "desired_at": "2025-12-23T00:00:00Z",
    "priority": 50
  }'
```

### Week Range

```python
# scripts/backfill_range.py
import requests
from datetime import date, timedelta

api_base = "http://localhost:8000/api/v1"
start_date = date(2025, 10, 1)
end_date = date(2025, 12, 22)

current = start_date
while current <= end_date:
    # Only process Fridays (week endings)
    if current.weekday() == 4:
        for tier in ["NMS_TIER_1", "NMS_TIER_2", "OTC"]:
            work_item = {
                "domain": "finra.otc_transparency",
                "pipeline": "ingest_week",
                "partition_key": {
                    "week_ending": current.isoformat(),
                    "tier": tier
                },
                "desired_at": "2025-12-23T00:00:00Z",
                "priority": 25  # Lower priority than current week
            }
            
            response = requests.post(
                f"{api_base}/work/enqueue",
                json=work_item
            )
            print(f"✓ Enqueued {tier} for {current.isoformat()}: {response.status_code}")
    
    current += timedelta(days=1)

print("Backfill enqueued. Monitor with: GET /api/v1/work/pending")
```

## Failure Handling

### State Machine

```
PENDING ──┐
          │ Worker claims work
          ▼
       RUNNING ──┐
          │      │ Success
          │      ▼
          │   COMPLETE
          │
          │ Failure
          ▼
       FAILED ──┐
          │     │ Retry logic
          │     ▼
          │  RETRY_WAIT (exponential backoff)
          │     │
          │     │ next_attempt_at reached
          │     ▼
          └─ PENDING (attempt_count++)
```

### Exponential Backoff

Failures trigger automatic retry with increasing delays:

```
Attempt 1: immediate
Attempt 2: wait 5 minutes
Attempt 3: wait 15 minutes (3x)
Max attempts: 3 (configurable)
```

After max attempts, work remains in `FAILED` state for manual intervention.

### Monitoring Failed Work

```bash
# List all failed work items
curl http://localhost:8000/api/v1/work/pending?state=FAILED

# Example response:
{
  "failed": [
    {
      "id": 123,
      "domain": "finra.otc_transparency",
      "pipeline": "ingest_week",
      "partition_key": {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"},
      "state": "FAILED",
      "attempt_count": 3,
      "last_error": "HTTP 503: FINRA API unavailable",
      "last_error_at": "2025-12-23T10:45:00Z"
    }
  ]
}
```

### Manual Retry

```bash
# Retry specific work item
curl -X POST http://localhost:8000/api/v1/work/retry \
  -H "Content-Type: application/json" \
  -d '{"work_item_id": 123}'

# Retry all failed items for a domain
curl -X POST http://localhost:8000/api/v1/work/retry \
  -H "Content-Type: application/json" \
  -d '{"domain": "finra.otc_transparency"}'
```

### Alerting Integration

```yaml
# Prometheus AlertManager rule
- alert: MarketSpineWorkFailed
  expr: |
    count(core_work_items{state="FAILED", attempt_count >= max_attempts}) > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Market Spine work items stuck in FAILED state"
    description: "{{ $value }} work items have exhausted retry attempts"
    runbook_url: "https://docs.market-spine.io/ops/runbooks/failed-work"
```

## Work Queue Management

### Checking Pending Work

```bash
# All pending work
curl http://localhost:8000/api/v1/work/pending

# Filtered by domain
curl http://localhost:8000/api/v1/work/pending?domain=finra.otc_transparency

# Filtered by state
curl http://localhost:8000/api/v1/work/pending?state=RETRY_WAIT
```

### Cancelling Work

```bash
# Cancel a specific work item (before it runs)
curl -X POST http://localhost:8000/api/v1/work/cancel \
  -H "Content-Type: application/json" \
  -d '{"work_item_id": 123}'
```

## Dependencies Between Pipelines

Market Spine does **not** enforce DAG dependencies automatically. Scheduling must respect logical order:

1. **ingest_week** must complete before **normalize_week**
2. **normalize_week** must complete before **compute_*** calcs
3. Within calcs, order doesn't matter (can run in parallel)

**Recommended approach:**
- Use `desired_at` timestamps to stagger start times
- Check manifest before enqueueing downstream work
- Rely on idempotency: safe to enqueue too early (will fail-retry until dependencies met)

**Example dependency check:**

```python
# Before enqueueing normalize_week, check if ingest_week completed
response = requests.get(
    f"{api_base}/manifest",
    params={
        "domain": "finra.otc_transparency",
        "partition_key": json.dumps({"week_ending": "2025-12-22", "tier": "NMS_TIER_1"}),
        "stage": "RAW"
    }
)

if response.json().get("row_count", 0) > 0:
    # RAW stage has data, safe to enqueue NORMALIZED
    enqueue_normalize_work()
else:
    # Wait or fail
    print("RAW stage not ready, skipping normalize")
```

## Best Practices

### 1. Separate Enqueue from Execute

**Don't:** Run pipelines directly from cron
```bash
# ❌ BAD: Direct execution from cron
30 10 * * 1 spine run finra.otc_transparency.ingest_week --week 2025-12-22
```

**Do:** Enqueue work, let workers execute
```bash
# ✓ GOOD: Enqueue via API
30 10 * * 1 /scripts/enqueue_weekly_finra.sh
```

**Why:** Enqueue pattern enables:
- Retry on failure
- Monitoring via work queue
- Distributed execution (multiple workers)
- Audit trail in database

### 2. Set Realistic `desired_at` Times

```bash
# Current week: high priority, run ASAP
"desired_at": "2025-12-23T10:30:00Z"

# Backfill: lower priority, can delay
"desired_at": "2025-12-25T02:00:00Z"
```

### 3. Monitor Work Queue Health

```bash
# Daily: check for stuck items
curl http://localhost:8000/api/v1/work/pending?state=FAILED | jq '.failed | length'

# Alert if > 0 failed items for > 1 hour
```

### 4. Use Partitioning for Parallelism

```bash
# Good: 3 work items run in parallel
for tier in NMS_TIER_1 NMS_TIER_2 OTC; do
  enqueue ingest_week --tier $tier
done

# Bad: 1 work item does all tiers (slower)
enqueue ingest_all_tiers
```

### 5. Leverage Manifest for Status

```sql
-- Check pipeline progress
SELECT 
    partition_key,
    stage,
    row_count,
    updated_at
FROM core_manifest
WHERE domain = 'finra.otc_transparency'
    AND partition_key LIKE '%2025-12-22%'
ORDER BY stage_rank;
```

## Troubleshooting

### Work Stuck in RUNNING

**Symptom:** Work item shows `RUNNING` but no progress

**Cause:** Worker crashed or lock not released

**Fix:**
```sql
-- Reset stuck work (no activity in 30 minutes)
UPDATE core_work_items
SET state = 'PENDING',
    current_execution_id = NULL,
    locked_by = NULL,
    locked_at = NULL
WHERE state = 'RUNNING'
  AND locked_at < datetime('now', '-30 minutes');
```

### Duplicate Work Items

**Symptom:** Multiple work items for same week/tier

**Cause:** Enqueue called twice without checking UNIQUE constraint

**Prevention:** Schema enforces `UNIQUE(domain, pipeline, partition_key)`

**If it happens:** Duplicate attempts will be rejected by database

### Missing Dependencies

**Symptom:** `normalize_week` fails because `ingest_week` didn't run

**Cause:** Dependency not checked before enqueue

**Fix:** Check manifest or wait longer between phases

## Next Steps

- [Gap Detection](gap-detection.md) - Detect missing week/tier partitions
- [DBA Guidance](../architecture/dba-guidance.md) - Schema evolution best practices
- [Scheduler Fitness Tests](../../tests/test_scheduler_fitness.py) - Validate retry/idempotency
