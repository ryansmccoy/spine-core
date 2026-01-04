# Running Pipelines

This guide covers everything you need to know about running pipelines: parameters, options, debugging, and batch operations.

## The `spine run` Command

The basic syntax is:

```bash
spine run <pipeline_name> [options] [-p key=value ...]
```

### Parameters

Pass parameters with `-p` or `--param`:

```bash
spine run otc.ingest_week \
  -p week_ending=2025-12-26 \
  -p tier=NMS_TIER_1 \
  -p file_path=data/finra/nms_tier1_2025-12-26.psv
```

### Execution Lanes

The `--lane` option categorizes executions (informational in Basic tier):

```bash
spine run otc.ingest_week -p ... --lane backfill
```

Lanes:
- `normal` — Regular execution (default)
- `backfill` — Historical data loading
- `slow` — Low-priority/resource-intensive work

### Force Re-execution

Most pipelines check idempotency and skip if already done. Use `force=true` to re-run:

```bash
spine run otc.normalize_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1 -p force=true
```

## Pipeline Dependency Order

Pipelines must run in order. For OTC:

```
1. otc.ingest_week     → Loads raw data from file
2. otc.normalize_week  → Validates and transforms
3. otc.aggregate_week  → Computes symbol summaries
4. otc.compute_rolling → Calculates rolling metrics
```

Running out of order will fail:

```bash
# This fails - no raw data yet
spine run otc.normalize_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1
# ✗ Pipeline failed: No raw data found for this week
```

## Batch Operations: Backfill

The `otc.backfill_range` pipeline runs ingest+normalize for multiple weeks:

```bash
spine run otc.backfill_range \
  -p start_week=2025-12-06 \
  -p end_week=2025-12-26 \
  -p tier=NMS_TIER_1 \
  -p data_dir=data/finra
```

This:
1. Generates all Fridays in range
2. Looks for matching files (`nms_tier1_2025-12-06.psv`, etc.)
3. Runs ingest → normalize for each week
4. Reports overall progress

## Understanding the Logs

Every pipeline execution produces structured logs. Key events:

### Execution Lifecycle

```
execution.submitted   → Pipeline queued (immediately executed in Basic)
execution.run.start   → Execution begins
execution.run.end     → Execution completes
execution.summary     → Final status with metrics
```

### Pipeline-Specific Events

```
ingest.parsed         → File parsing completed
ingest.bulk_insert.end → Data inserted
normalize.validated   → Validation completed with counts
normalize.no_raw_data → Error: nothing to normalize
```

### Sample Log Output

```
2025-12-26T10:15:32.123Z [info] execution.submitted
    execution_id=abc-123
    pipeline=otc.ingest_week
    lane=normal
    
2025-12-26T10:15:33.456Z [info] ingest.bulk_insert.end
    execution_id=abc-123
    span_id=e21aef49
    duration_ms=1234.56
    table=otc_raw
    rows=50000
    
2025-12-26T10:15:33.567Z [info] execution.summary
    execution_id=abc-123
    status=completed
    duration_ms=1444.12
    rows_out=50000
```

## Debugging Failed Pipelines

### Check the Error Message

```bash
spine run otc.normalize_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1
# ✗ Pipeline failed: No raw data found for this week
```

### Enable Debug Logging

Set the environment variable:

```bash
$env:SPINE_LOG_LEVEL = "DEBUG"
spine run otc.normalize_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1
```

Debug logs show:
- Parameter values
- SQL queries (indirectly via step timing)
- Intermediate row counts

### Check the Manifest

The manifest tracks what stage each week has reached:

```bash
spine shell
```

```python
>>> conn = get_connection()
>>> rows = conn.execute("""
...     SELECT partition_key, stage, stage_rank, row_count, updated_at 
...     FROM core_manifest 
...     WHERE domain = 'otc'
...     ORDER BY partition_key, stage_rank
... """).fetchall()
>>> for r in rows: print(dict(r))
{'partition_key': '{"tier": "NMS_TIER_1", "week_ending": "2025-12-26"}', 'stage': 'INGESTED', ...}
{'partition_key': '{"tier": "NMS_TIER_1", "week_ending": "2025-12-26"}', 'stage': 'NORMALIZED', ...}
```

### Check Rejects

Validation failures are recorded in `core_rejects`:

```python
>>> conn.execute("""
...     SELECT rule_name, COUNT(*) as count 
...     FROM core_rejects 
...     WHERE domain = 'otc' 
...     GROUP BY rule_name
... """).fetchall()
[('INVALID_SYMBOL', 250), ('NEGATIVE_VOLUME', 150), ('MISSING_MPID', 100)]
```

## Common Patterns

### Running All Stages for One Week

```bash
# Full pipeline for one week
spine run otc.ingest_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1 -p file_path=data/finra/nms_tier1_2025-12-26.psv
spine run otc.normalize_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1
spine run otc.aggregate_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1
spine run otc.compute_rolling -p week_ending=2025-12-26 -p tier=NMS_TIER_1
```

### Re-processing After Bug Fix

```bash
# Force re-run of normalize and downstream
spine run otc.normalize_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1 -p force=true
spine run otc.aggregate_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1 -p force=true
```

### Clean Start

```bash
# Nuclear option: reset everything
spine db reset --yes
spine db init
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SPINE_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SPINE_LOG_FORMAT` | `console` | `console` or `json` |
| `SPINE_DATABASE_PATH` | `spine.db` | SQLite database file |
| `SPINE_DATA_DIR` | `./data` | Default data directory |

## Next Steps

- [Execution Model](../architecture/02_execution_model.md) — How dispatch works under the hood
- [Pipeline Model](../architecture/03_pipeline_model.md) — Anatomy of a pipeline
- [Logging Schema](../logging-schema.md) — Parse logs for dashboards
