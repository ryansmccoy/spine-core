# Gap Detection ("Doctor" for Scheduled Pipelines)

## Overview

Market Spine's "doctor" commands detect missing or incomplete data partitions in scheduled pipelines. This is critical for production operations where data must arrive weekly without gaps.

## What the Doctor Checks

### 1. Expected vs Actual Partitions

For FINRA OTC weekly data:
- **Expected:** Last N weeks × 3 tiers = 3N partitions
- **Actual:** Count partitions at each stage (RAW, NORMALIZED, CALC)
- **Gap:** Expected - Actual

### 2. Pipeline Completeness

For each partition, check progression:
```
RAW → NORMALIZED → VENUE_VOLUME → VENUE_SHARE → HHI → TIER_SPLIT
```

Missing stages indicate incomplete pipeline runs.

### 3. Data Freshness

- When was each partition last updated?
- Are any partitions "stale" (older than expected)?

## Running the Doctor

### CLI Command

```bash
# Check last 4 weeks of FINRA OTC data
spine doctor finra.otc_transparency --weeks 4

# Check specific week range
spine doctor finra.otc_transparency --start 2025-11-01 --end 2025-12-22

# Verbose output with remediation commands
spine doctor finra.otc_transparency --weeks 4 --verbose

# JSON output for automation
spine doctor finra.otc_transparency --weeks 4 --format json
```

### API Endpoint

```bash
# GET /api/v1/doctor/{domain}
curl "http://localhost:8000/api/v1/doctor/finra.otc_transparency?weeks=4"
```

## Example Output

### Healthy System

```bash
$ spine doctor finra.otc_transparency --weeks 4

✓ Checking FINRA OTC Transparency (last 4 weeks)

Expected partitions: 12 (4 weeks × 3 tiers)
Found partitions:    12

┌─────────────┬─────────────┬─────┬────────────┬────────────┬──────────┬──────────────┬─────┬────────────┐
│ Week Ending │ Tier        │ RAW │ NORMALIZED │ VENUE_VOL  │ VENUE_SH │ HHI          │ T_S │ Last Update│
├─────────────┼─────────────┼─────┼────────────┼────────────┼──────────┼──────────────┼─────┼────────────┤
│ 2025-12-22  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-23 │
│ 2025-12-22  │ NMS_TIER_2  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-23 │
│ 2025-12-22  │ OTC         │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-23 │
│ 2025-12-15  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-16 │
│ 2025-12-15  │ NMS_TIER_2  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-16 │
│ 2025-12-15  │ OTC         │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-16 │
│ 2025-12-08  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-09 │
│ 2025-12-08  │ NMS_TIER_2  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-09 │
│ 2025-12-08  │ OTC         │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-09 │
│ 2025-12-01  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-02 │
│ 2025-12-01  │ NMS_TIER_2  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-02 │
│ 2025-12-01  │ OTC         │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-02 │
└─────────────┴─────────────┴─────┴────────────┴────────────┴──────────┴──────────────┴─────┴────────────┘

✓ All partitions complete
✓ All stages present
✓ No gaps detected
```

### System with Gaps

```bash
$ spine doctor finra.otc_transparency --weeks 4

⚠ Checking FINRA OTC Transparency (last 4 weeks)

Expected partitions: 12 (4 weeks × 3 tiers)
Found partitions:    9
MISSING: 3 partitions

┌─────────────┬─────────────┬─────┬────────────┬────────────┬──────────┬──────────────┬─────┬────────────┐
│ Week Ending │ Tier        │ RAW │ NORMALIZED │ VENUE_VOL  │ VENUE_SH │ HHI          │ T_S │ Last Update│
├─────────────┼─────────────┼─────┼────────────┼────────────┼──────────┼──────────────┼─────┼────────────┤
│ 2025-12-22  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-23 │
│ 2025-12-22  │ NMS_TIER_2  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-23 │
│ 2025-12-22  │ OTC         │  ✗  │     ✗      │     ✗      │    ✗     │      ✗       │  ✗  │ —          │
│ 2025-12-15  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✗     │      ✗       │  ✗  │ 2025-12-16 │
│ 2025-12-15  │ NMS_TIER_2  │  ✓  │     ✓      │     ✗      │    ✗     │      ✗       │  ✗  │ 2025-12-16 │
│ 2025-12-15  │ OTC         │  ✓  │     ✓      │     ✗      │    ✗     │      ✗       │  ✗  │ 2025-12-16 │
│ 2025-12-08  │ NMS_TIER_1  │  ✗  │     ✗      │     ✗      │    ✗     │      ✗       │  ✗  │ —          │
│ 2025-12-08  │ NMS_TIER_2  │  ✗  │     ✗      │     ✗      │    ✗     │      ✗       │  ✗  │ —          │
│ 2025-12-08  │ OTC         │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-09 │
│ 2025-12-01  │ NMS_TIER_1  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-02 │
│ 2025-12-01  │ NMS_TIER_2  │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-02 │
│ 2025-12-01  │ OTC         │  ✓  │     ✓      │     ✓      │    ✓     │      ✓       │  ✓  │ 2025-12-02 │
└─────────────┴─────────────┴─────┴────────────┴────────────┴──────────┴──────────────┴─────┴────────────┘

⚠ GAPS DETECTED:

1. Missing RAW data:
   - 2025-12-22 / OTC (entire partition missing)
   - 2025-12-08 / NMS_TIER_1 (entire partition missing)
   - 2025-12-08 / NMS_TIER_2 (entire partition missing)

2. Incomplete analytics:
   - 2025-12-15 / NMS_TIER_1 (missing: VENUE_SHARE, HHI, TIER_SPLIT)
   - 2025-12-15 / NMS_TIER_2 (missing: VENUE_VOLUME, VENUE_SHARE, HHI, TIER_SPLIT)
   - 2025-12-15 / OTC (missing: VENUE_VOLUME, VENUE_SHARE, HHI, TIER_SPLIT)

REMEDIATION COMMANDS:

# Re-run missing ingestion
spine run finra.otc_transparency.ingest_week --week-ending 2025-12-22 --tier OTC
spine run finra.otc_transparency.ingest_week --week-ending 2025-12-08 --tier NMS_TIER_1
spine run finra.otc_transparency.ingest_week --week-ending 2025-12-08 --tier NMS_TIER_2

# Re-run incomplete analytics
spine run finra.otc_transparency.compute_venue_share --week-ending 2025-12-15 --tier NMS_TIER_1
spine run finra.otc_transparency.compute_venue_volume --week-ending 2025-12-15 --tier NMS_TIER_2

# Or backfill entire range
spine backfill finra.otc_transparency --start 2025-12-08 --end 2025-12-22

Exit code: 1 (gaps detected)
```

## JSON Output (for Automation)

```bash
$ spine doctor finra.otc_transparency --weeks 4 --format json

{
  "domain": "finra.otc_transparency",
  "checked_at": "2025-12-23T15:30:00Z",
  "weeks_checked": 4,
  "expected_partitions": 12,
  "found_partitions": 9,
  "missing_partitions": 3,
  "status": "GAPS_DETECTED",
  "gaps": [
    {
      "week_ending": "2025-12-22",
      "tier": "OTC",
      "missing_stages": ["RAW", "NORMALIZED", "VENUE_VOLUME", "VENUE_SHARE", "HHI", "TIER_SPLIT"],
      "severity": "CRITICAL"
    },
    {
      "week_ending": "2025-12-08",
      "tier": "NMS_TIER_1",
      "missing_stages": ["RAW", "NORMALIZED", "VENUE_VOLUME", "VENUE_SHARE", "HHI", "TIER_SPLIT"],
      "severity": "CRITICAL"
    },
    {
      "week_ending": "2025-12-15",
      "tier": "NMS_TIER_1",
      "missing_stages": ["VENUE_SHARE", "HHI", "TIER_SPLIT"],
      "severity": "WARNING",
      "partial": true
    }
  ],
  "remediation": [
    {
      "command": "spine run finra.otc_transparency.ingest_week",
      "args": {"week_ending": "2025-12-22", "tier": "OTC"},
      "reason": "Missing RAW data"
    },
    {
      "command": "spine run finra.otc_transparency.compute_venue_share",
      "args": {"week_ending": "2025-12-15", "tier": "NMS_TIER_1"},
      "reason": "Incomplete analytics chain"
    }
  ]
}
```

## Integration with Monitoring

### Prometheus Metrics

```python
# metrics.py
from prometheus_client import Gauge

gap_count = Gauge(
    'market_spine_partition_gaps',
    'Number of missing partitions detected',
    ['domain']
)

stale_partitions = Gauge(
    'market_spine_stale_partitions',
    'Partitions not updated in expected timeframe',
    ['domain', 'stage']
)

# Update from doctor checks
doctor_result = run_doctor("finra.otc_transparency", weeks=4)
gap_count.labels(domain="finra.otc_transparency").set(doctor_result["missing_partitions"])
```

### Alert Rules

```yaml
# Prometheus alerts
groups:
- name: market_spine_completeness
  rules:
  - alert: MissingFINRAPartitions
    expr: market_spine_partition_gaps{domain="finra.otc_transparency"} > 0
    for: 6h
    labels:
      severity: warning
    annotations:
      summary: "FINRA OTC data has {{ $value }} missing partitions"
      description: "Run doctor command: spine doctor finra.otc_transparency --weeks 4"
  
  - alert: StaleFINRAData
    expr: |
      (time() - market_spine_partition_last_update{domain="finra.otc_transparency"}) > 604800
    labels:
      severity: critical
    annotations:
      summary: "FINRA OTC partition not updated in 7+ days"
      description: "Partition {{ $labels.partition_key }} is stale"
```

### Daily Health Checks

```bash
#!/bin/bash
# /opt/market-spine/cron/daily_health_check.sh
# Crontab: 0 9 * * * /opt/market-spine/cron/daily_health_check.sh

spine doctor finra.otc_transparency --weeks 12 --format json > /tmp/doctor_result.json

MISSING=$(jq -r '.missing_partitions' /tmp/doctor_result.json)

if [ "$MISSING" -gt 0 ]; then
  echo "⚠ FINRA OTC has $MISSING missing partitions" | mail -s "Market Spine Health Alert" ops@company.com
  
  # Auto-remediate if configured
  if [ "$AUTO_REMEDIATE" = "true" ]; then
    jq -r '.remediation[] | "spine run \(.command) \(.args | to_entries | map("--\(.key) \(.value)") | join(" "))"' /tmp/doctor_result.json | bash
  fi
fi
```

## How the Doctor Works

### 1. Expected Partition Calculation

```python
def calculate_expected_partitions(domain: str, weeks: int) -> list[dict]:
    """Calculate which week/tier partitions should exist."""
    expected = []
    
    # For FINRA OTC: every Friday for last N weeks, 3 tiers each
    end_date = get_last_friday()
    start_date = end_date - timedelta(weeks=weeks)
    
    current = start_date
    while current <= end_date:
        if current.weekday() == 4:  # Friday
            for tier in ["NMS_TIER_1", "NMS_TIER_2", "OTC"]:
                expected.append({
                    "week_ending": current.isoformat(),
                    "tier": tier
                })
        current += timedelta(days=1)
    
    return expected
```

### 2. Actual Partition Query

```sql
-- Query manifest to find what exists
SELECT DISTINCT
    json_extract(partition_key, '$.week_ending') AS week_ending,
    json_extract(partition_key, '$.tier') AS tier,
    GROUP_CONCAT(DISTINCT stage) AS stages_present
FROM core_manifest
WHERE domain = 'finra.otc_transparency'
  AND json_extract(partition_key, '$.week_ending') >= :start_date
  AND json_extract(partition_key, '$.week_ending') <= :end_date
GROUP BY week_ending, tier;
```

### 3. Gap Detection Logic

```python
def detect_gaps(expected: list, actual: list) -> list:
    """Find partitions in expected but not in actual."""
    actual_keys = {(a["week_ending"], a["tier"]) for a in actual}
    gaps = []
    
    for exp in expected:
        key = (exp["week_ending"], exp["tier"])
        if key not in actual_keys:
            gaps.append({
                **exp,
                "missing_stages": ["RAW", "NORMALIZED", "VENUE_VOLUME", "VENUE_SHARE", "HHI", "TIER_SPLIT"],
                "severity": "CRITICAL"
            })
        else:
            # Check stage completeness
            actual_partition = next(a for a in actual if (a["week_ending"], a["tier"]) == key)
            expected_stages = {"RAW", "NORMALIZED", "VENUE_VOLUME", "VENUE_SHARE", "HHI", "TIER_SPLIT"}
            actual_stages = set(actual_partition.get("stages_present", "").split(","))
            missing_stages = expected_stages - actual_stages
            
            if missing_stages:
                gaps.append({
                    **exp,
                    "missing_stages": list(missing_stages),
                    "severity": "WARNING",
                    "partial": True
                })
    
    return gaps
```

## Remediation Workflow

### Automated Remediation (Cautious)

```python
# scripts/auto_remediate.py
import subprocess
import json

result = subprocess.run(
    ["spine", "doctor", "finra.otc_transparency", "--weeks", "4", "--format", "json"],
    capture_output=True,
    text=True
)

doctor_output = json.loads(result.stdout)

# Only auto-remediate if < 5 missing partitions (safety check)
if doctor_output["missing_partitions"] <= 5:
    for remediation in doctor_output["remediation"]:
        cmd = [remediation["command"]]
        for key, value in remediation["args"].items():
            cmd.extend([f"--{key}", str(value)])
        
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd)
else:
    print(f"Too many gaps ({doctor_output['missing_partitions']}), manual intervention required")
```

### Manual Remediation (Recommended)

```bash
# 1. Review gaps
spine doctor finra.otc_transparency --weeks 4 --verbose

# 2. Understand root cause
# - Was source data missing from FINRA?
# - Did ingestion fail?
# - Did pipeline crash mid-run?

# 3. Backfill conservatively
spine backfill finra.otc_transparency --start 2025-12-08 --end 2025-12-15

# 4. Verify completion
spine doctor finra.otc_transparency --weeks 4
```

## Advanced Features

### Stage Dependency Checking

```bash
# Check if prerequisites exist before running a stage
spine doctor finra.otc_transparency --check-dependencies \
  --pipeline compute_venue_share \
  --week-ending 2025-12-22 \
  --tier NMS_TIER_1

# Output:
# ✓ NORMALIZED stage present (row_count: 48765)
# ✗ VENUE_VOLUME stage missing
# Recommendation: Run compute_venue_volume first
```

### Freshness Thresholds

```bash
# Alert if data is stale (> 7 days old)
spine doctor finra.otc_transparency --weeks 4 --max-age-days 7

# Output:
# ⚠ Stale partitions detected:
# - 2025-12-01 / NMS_TIER_1: last updated 10 days ago
```

### Compare Across Environments

```bash
# Check production vs staging consistency
spine doctor finra.otc_transparency --weeks 4 --env production > prod.json
spine doctor finra.otc_transparency --weeks 4 --env staging > staging.json

diff <(jq -S . prod.json) <(jq -S . staging.json)
```

## SQL Queries for Manual Investigation

### Find Missing Weeks

```sql
-- Expected: 12 weeks of data
WITH RECURSIVE weeks(week_ending) AS (
  SELECT date('2025-10-01')
  UNION ALL
  SELECT date(week_ending, '+7 days')
  FROM weeks
  WHERE week_ending < date('2025-12-22')
)
SELECT 
    w.week_ending,
    COUNT(DISTINCT m.partition_key) AS tier_count,
    CASE WHEN COUNT(DISTINCT m.partition_key) = 3 THEN '✓' ELSE '✗' END AS complete
FROM weeks w
LEFT JOIN core_manifest m 
    ON json_extract(m.partition_key, '$.week_ending') = w.week_ending
    AND m.domain = 'finra.otc_transparency'
    AND m.stage = 'RAW'
GROUP BY w.week_ending
ORDER BY w.week_ending DESC;
```

### Find Incomplete Stage Chains

```sql
-- Partitions with RAW but no NORMALIZED
SELECT 
    json_extract(partition_key, '$.week_ending') AS week_ending,
    json_extract(partition_key, '$.tier') AS tier
FROM core_manifest
WHERE domain = 'finra.otc_transparency'
  AND stage = 'RAW'
  AND NOT EXISTS (
      SELECT 1 FROM core_manifest m2
      WHERE m2.domain = core_manifest.domain
        AND m2.partition_key = core_manifest.partition_key
        AND m2.stage = 'NORMALIZED'
  );
```

## Next Steps

- [Scheduling Guide](scheduling.md) - Set up cron/K8s jobs
- [DBA Guidance](../architecture/dba-guidance.md) - Schema evolution
- [Scheduler Fitness Tests](../../tests/test_scheduler_fitness.py) - Automated testing
