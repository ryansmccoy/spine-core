# Scheduler Operations Guide

## Overview

This document covers operational scheduling for Market Spine data pipelines.
Schedulers are designed to be **automation-ready** for:

- Local cron jobs
- Kubernetes CronJobs
- OpenShift scheduled tasks
- Docker-based batch jobs
- CI/CD pipelines (GitHub Actions, GitLab CI)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Wrapper Scripts                              │
│  scripts/schedule_finra.py    scripts/schedule_prices.py        │
│  (CLI parsing, logging setup, exit code handling)               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Domain Schedulers                              │
│  spine.domains.finra.otc_transparency.scheduler                 │
│  spine.domains.market_data.scheduler                            │
│  (Business logic, revision detection, pipeline orchestration)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Result Contract                                │
│  market_spine.app.scheduling.SchedulerResult                    │
│  (Standardized JSON output, exit codes, stats)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Scheduler Result Contract

All schedulers return a standardized `SchedulerResult` object:

```python
from market_spine.app.scheduling import SchedulerResult, SchedulerStatus

result = run_finra_schedule(mode="dry-run")

# Exit code for shell scripts
sys.exit(result.exit_code)

# JSON output for automation
print(result.to_json())
```

### Exit Codes

| Code | Status | Meaning |
|------|--------|---------|
| 0 | SUCCESS / DRY_RUN | All partitions processed successfully |
| 1 | FAILURE | All partitions failed or critical error |
| 2 | PARTIAL | Some partitions succeeded, some failed |

### JSON Schema

```json
{
  "schema_version": "1.0.0",
  "domain": "finra.otc_transparency",
  "scheduler": "weekly_ingest",
  "started_at": "2025-01-01T00:00:00Z",
  "finished_at": "2025-01-01T00:01:30Z",
  "status": "success",
  "stats": {
    "attempted": 12,
    "succeeded": 12,
    "failed": 0,
    "skipped": 0
  },
  "runs": [
    {
      "pipeline": "finra.otc_transparency.ingest_week",
      "partition_key": "2025-01-03|NMS_TIER_1",
      "status": "completed",
      "duration_ms": 1500,
      "capture_id": "finra.otc_transparency:NMS_TIER_1:2025-01-03:20250106",
      "row_count": 5432,
      "is_revision": true,
      "revision_summary": {
        "rows_added": 15,
        "rows_removed": 3,
        "rows_changed": 12
      }
    }
  ],
  "anomalies": [],
  "warnings": [],
  "config": {
    "lookback_weeks": 4,
    "mode": "run"
  }
}
```

## FINRA OTC Scheduler

### Usage

```bash
# Standard weekly run (last 4 weeks, all tiers)
python scripts/schedule_finra.py --lookback-weeks 4

# Dry-run (no database writes)
python scripts/schedule_finra.py --mode dry-run --lookback-weeks 4

# Backfill specific weeks
python scripts/schedule_finra.py --weeks 2025-12-15,2025-12-22

# Force restatement (ignore revision detection)
python scripts/schedule_finra.py --force --lookback-weeks 4

# CI/CD mode (stop on first failure)
python scripts/schedule_finra.py --fail-fast

# JSON output for automation
python scripts/schedule_finra.py --json --mode dry-run
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--lookback-weeks` | 4 | Number of weeks to process |
| `--weeks` | - | Specific week_ending dates (comma-separated) |
| `--tiers` | all | Tier names (comma-separated) |
| `--source` | file | Data source: `api` or `file` |
| `--mode` | run | `run` or `dry-run` |
| `--force` | false | Ignore revision detection and max lookback |
| `--only-stage` | all | `ingest`, `normalize`, `calc`, or `all` |
| `--fail-fast` | false | Stop on first failure |
| `--db` | DATABASE_URL or default | Database path |
| `--log-level` | INFO | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--json` | false | Output result as JSON |

### Safe Lookback Semantics

- Maximum lookback is **12 weeks** by default
- Exceeding 12 weeks triggers a warning and clamps to 12
- Use `--force` to override the limit (e.g., for backfill)

```bash
# This will clamp to 12 weeks with a warning
python scripts/schedule_finra.py --lookback-weeks 20

# Use --force to override
python scripts/schedule_finra.py --lookback-weeks 20 --force
```

### Revision Detection

The scheduler automatically detects content changes via SHA256 hash comparison:

1. Fetches source data
2. Computes content hash
3. Compares with latest capture in `core_manifest`
4. Skips if hash matches (no changes)
5. Proceeds with restatement if hash differs

Use `--force` to always restate regardless of hash.

## Price Data Scheduler

### Usage

```bash
# Standard run with symbols
python scripts/schedule_prices.py --symbols AAPL,MSFT,GOOGL

# Load symbols from file
python scripts/schedule_prices.py --symbols-file symbols.txt

# Dry-run
python scripts/schedule_prices.py --symbols AAPL --mode dry-run

# JSON output
python scripts/schedule_prices.py --symbols AAPL --json
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--symbols` | required | Comma-separated stock symbols |
| `--symbols-file` | - | File with symbols (one per line) |
| `--source` | PRICE_SOURCE env | `alpha_vantage`, `polygon`, `mock` |
| `--outputsize` | compact | `compact` (~100 days) or `full` (20 years) |
| `--sleep` | 12.0 | Seconds between API calls |
| `--max-symbols` | 25 | Maximum symbols per batch |
| `--mode` | run | `run` or `dry-run` |
| `--fail-fast` | false | Stop on first failure |
| `--db` | DATABASE_URL or default | Database path |
| `--log-level` | INFO | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--json` | false | Output result as JSON |

## Kubernetes CronJob Example

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: finra-weekly-ingest
spec:
  schedule: "0 6 * * 1"  # Monday 6 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: scheduler
            image: market-spine:latest
            command:
              - python
              - scripts/schedule_finra.py
              - --lookback-weeks=4
              - --mode=run
              - --json
              - --fail-fast
            env:
              - name: DATABASE_URL
                valueFrom:
                  secretKeyRef:
                    name: db-credentials
                    key: url
          restartPolicy: OnFailure
```

## Docker Compose Example

```yaml
services:
  finra-scheduler:
    image: market-spine:latest
    command: >
      python scripts/schedule_finra.py
        --lookback-weeks 4
        --mode run
        --json
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/market_spine
    depends_on:
      - db
```

## GitHub Actions Example

```yaml
name: Weekly FINRA Ingest

on:
  schedule:
    - cron: '0 6 * * 1'  # Monday 6 AM UTC
  workflow_dispatch:

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -e packages/spine-domains -e market-spine-basic
      
      - name: Run FINRA scheduler
        run: |
          python scripts/schedule_finra.py \
            --lookback-weeks 4 \
            --mode run \
            --json \
            --fail-fast
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## Testing Schedulers

```bash
# Run smoke tests
pytest market-spine-basic/tests/test_scheduler_smoke.py -v

# Test dry-run JSON output
python scripts/schedule_finra.py --mode dry-run --json | jq .

# Test help output
python scripts/schedule_finra.py --help
python scripts/schedule_prices.py --help
```

## Troubleshooting

### Exit Code 1 (FAILURE)

All partitions failed. Check:
- Database connectivity (`--db` or `DATABASE_URL`)
- Source data availability (files or API)
- Schema migrations applied

### Exit Code 2 (PARTIAL)

Some partitions failed. Check:
- JSON output for specific failures: `--json | jq '.runs[] | select(.status == "failed")'`
- Anomalies recorded in `core_anomalies` table

### Lookback Clamped Warning

```
WARNING: Lookback 20 exceeds max 12, clamped. Use --force to override.
```

The scheduler limits lookback to 12 weeks for safety. Use `--force` for backfills.

### ImportError

```
Failed to import scheduler module
```

Ensure packages are installed:
```bash
pip install -e packages/spine-domains -e market-spine-basic
```
