# Quickstart: Your First Pipeline in 5 Minutes

This guide gets you from zero to running a real data pipeline.

## Prerequisites

- Python 3.11+
- A terminal (PowerShell, bash, zsh)

## Step 1: Install

```bash
# Clone or navigate to the repo
cd c:\projects\spine-core\market-spine-basic

# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate     # Windows PowerShell
# source .venv/bin/activate  # Linux/Mac

# Install the package
pip install -e .
```

Verify installation:

```bash
spine --version
# Market Spine Basic 0.1.0
```

## Step 2: Initialize the Database

```bash
spine db init
```

You should see:
```
Initializing database...
Database initialized successfully!
```

This creates `spine.db` with all required tables.

## Step 3: Check Available Pipelines

```bash
spine list
```

Output:
```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name               ┃ Description                                ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ otc.ingest_week    │ Ingest FINRA OTC file for one week         │
│ otc.normalize_week │ Normalize raw OTC data for one week        │
│ otc.aggregate_week │ Aggregate venue volumes to symbol level    │
│ otc.compute_rolling│ Compute rolling metrics for symbols        │
│ otc.backfill_range │ Backfill multiple weeks of OTC data        │
└────────────────────┴────────────────────────────────────────────┘
```

## Step 4: Run Your First Pipeline

Let's ingest some sample data. FINRA OTC files are located in the parent `data/finra/` directory.

**Smart Date Detection**: The pipeline automatically detects `week_ending` and `tier` from the file:

```bash
# Minimal invocation - dates and tier detected automatically
spine run otc.ingest_week -p file_path=../data/finra/finra_otc_weekly_tier1_20251222.csv
```

Output:
```
Running pipeline: otc.ingest_week
[info] ingest.tier_detected tier=NMS_TIER_1 source=filename
[info] ingest.dates_resolved file_date=2025-12-22 week_ending=2025-12-19 source=filename
[info] ingest.parsed rows=50889
[info] ingest.bulk_insert.end duration_ms=3704.07 rows=50889
Pipeline completed successfully!
  Metrics: {'records': 50889, 'inserted': 50889, 'capture_id': 'otc:NMS_TIER_1:2025-12-19:68f1ce'}
```

### FINRA Date Semantics

FINRA publishes OTC weekly data on **Mondays**. The data reflects the previous trading week (Mon-Fri):

| File Date (Monday) | Derived Week Ending (Friday) |
|--------------------|------------------------------|
| 2025-12-15         | 2025-12-12                   |
| 2025-12-22         | 2025-12-19                   |
| 2025-12-29         | 2025-12-26                   |

The pipeline handles this automatically. You can override if needed:

```bash
# Explicit override (for dev/backfill)
spine run otc.ingest_week \
  -p file_path=../data/finra/finra_otc_weekly_tier1_20251222.csv \
  -p week_ending=2025-12-19 \
  -p tier=NMS_TIER_1
```

## Step 5: Normalize the Data

```bash
spine run otc.normalize_week -p week_ending=2025-12-19 -p tier=NMS_TIER_1
```

Output:
```
Running pipeline: otc.normalize_week
[info] normalize.loaded_raw rows=50889
[info] normalize.validated rows_in=50889 rows_out=50889 rows_rejected=0
[info] execution.summary status=completed duration_ms=1666.34
Pipeline completed successfully!
  Metrics: {'accepted': 50889, 'rejected': 0}
```

## Step 6: Query the Results

Use the interactive shell:

```bash
spine shell
```

```python
>>> conn = get_connection()
>>> conn.execute("SELECT COUNT(*) FROM otc_venue_volume").fetchone()[0]
49500
>>> conn.execute("SELECT symbol, SUM(total_shares) as volume FROM otc_venue_volume GROUP BY symbol ORDER BY volume DESC LIMIT 5").fetchall()
[('AAPL', 12345678), ('MSFT', 9876543), ...]
```

## What Just Happened?

1. **Ingest** read a FINRA PSV file and loaded raw records into `otc_raw`
2. **Normalize** validated those records and wrote clean data to `otc_venue_volume`
3. Each row has full **lineage**: `execution_id`, `batch_id`, `capture_id`
4. The **manifest** tracks that this week is now `NORMALIZED`

## Next Steps

- [Running Pipelines](02_running_pipelines.md) — Learn all the options
- [System Overview](../architecture/01_system_overview.md) — Understand the architecture
- [Logging Schema](../logging-schema.md) — Parse the structured logs

## Troubleshooting

### "No module named 'market_spine'"

Make sure you've activated the virtual environment and installed the package:

```bash
.venv\Scripts\activate
pip install -e .
```

### "Pipeline failed: Pipeline not found"

Check that the pipeline name is correct:

```bash
spine list
```

### "No raw data found for this week"

You need to run `ingest_week` before `normalize_week`. The normalize pipeline reads from the raw table.
