# Market Spine Logging Schema

This document describes the structured log event schema for dashboard and monitoring integration.

## Event Format

All log events are emitted in structured format (key=value) with consistent field naming.

### Timestamp Format

All timestamps use **UTC ISO-8601** with Z suffix:
```
2026-01-03T06:55:06.762172Z
```

## Field Categories

### Core Fields (Always Present)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `timestamp` | string | UTC ISO-8601 with Z | `2026-01-03T06:55:06.762Z` |
| `level` | string | Log level | `debug`, `info`, `warning`, `error` |
| `event` | string | Stable event identifier for filtering | `execution.summary`, `ingest.parse_file.end` |

### Tracing Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `execution_id` | string | Unique pipeline execution ID | `exec-001` |
| `span_id` | string | Current operation span (8 hex chars) | `e21aef49` |
| `parent_span_id` | string | Parent span for nested operations | `a3b4c5d6` |

### Context Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `pipeline` | string | Pipeline name | `otc.ingest_week` |
| `domain` | string | Domain name | `otc` |
| `step` | string | Current processing step | `normalize.validate` |
| `backend` | string | Execution backend | `sync`, `celery` |
| `attempt` | int | Retry attempt number (omitted if 1) | `2` |

### Data Context Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `week_ending` | string | Week ending date (ISO Friday) | `2025-12-20` |
| `tier` | string | Data tier | `NMS_TIER_1`, `NMS_TIER_2`, `OTC` |
| `capture_id` | string | Data capture identifier | `otc:NMS_TIER_1:2025-12-20:a3f5b2` |

### Metric Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `duration_ms` | float | Operation duration in milliseconds | `1234.56` |
| `rows_in` | int | Input row count | `50000` |
| `rows_out` | int | Output row count | `49500` |
| `rows_rejected` | int | Rejected row count | `500` |
| `table` | string | Database table name | `otc_raw`, `otc_venue_volume` |

### Error Fields (ERROR level only)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `status` | string | Execution status | `failed` |
| `error_type` | string | Exception type | `ValueError`, `PipelineError` |
| `error_message` | string | Human-readable error message | `No raw data found` |
| `error_stack` | string | Full stack trace (multi-line) | `Traceback...` |

## Key Events

### `execution.summary`

Emitted once per pipeline run. This is the primary event for dashboard aggregation.

**Success:**
```
2026-01-03T06:55:06.763Z [info] execution.summary
    execution_id=exec-001
    pipeline=otc.ingest_week
    status=completed
    duration_ms=1234.56
    rows_out=50000
    week_ending=2025-12-20
    tier=NMS_TIER_1
```

**Failure:**
```
2026-01-03T06:55:06.765Z [error] execution.summary
    execution_id=exec-003
    pipeline=otc.normalize_week
    status=failed
    error_type=PipelineError
    error_message='No raw data found for this week'
```

### Step Events

Each processing step emits `.start` (DEBUG) and `.end` (INFO) events:

```
2026-01-03T06:55:06.762Z [debug] ingest.parse_file.start
    execution_id=exec-001
    span_id=e21aef49
    file=otc_2025-12-20_NMS1.psv

2026-01-03T06:55:06.762Z [info] ingest.parse_file.end
    execution_id=exec-001
    span_id=e21aef49
    duration_ms=0.42
    rows_in=50000
```

### Common Step Events

| Event | Level | Description |
|-------|-------|-------------|
| `ingest.parse_file.end` | INFO | File parsing completed |
| `ingest.bulk_insert.end` | INFO | Raw data inserted |
| `normalize.load_raw.end` | INFO | Raw data loaded |
| `normalize.validate.end` | INFO | Validation completed |
| `normalize.bulk_insert.end` | INFO | Normalized data inserted |
| `aggregate.compute.end` | INFO | Aggregation completed |
| `execution.run.end` | INFO | Pipeline execution finished |
| `normalize.no_raw_data` | ERROR | No data to normalize |

## Dashboard Integration

### Filtering by Event

To get all pipeline execution summaries:
```sql
SELECT * FROM logs WHERE event = 'execution.summary'
```

### Aggregating Metrics

Daily pipeline performance:
```sql
SELECT 
    DATE(timestamp) as day,
    pipeline,
    COUNT(*) as executions,
    AVG(duration_ms) as avg_duration_ms,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
FROM logs 
WHERE event = 'execution.summary'
GROUP BY day, pipeline
```

### Tracing a Request

Follow an execution through all steps:
```sql
SELECT * FROM logs 
WHERE execution_id = 'exec-001'
ORDER BY timestamp
```

Track nested operations:
```sql
SELECT * FROM logs 
WHERE parent_span_id = 'e21aef49'
ORDER BY timestamp
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SPINE_LOG_LEVEL` | `INFO` | Minimum log level |
| `SPINE_LOG_FORMAT` | `console` | Output format: `console` or `json` |
| `SPINE_LOG_PIPELINE_DEBUG` | `otc.*` | Pipeline patterns for DEBUG logging |

## Version History

- **v1.1** (2026-01-03): Added span_id, parent_span_id, attempt, error_stack
- **v1.0** (2025-12-28): Initial logging implementation
