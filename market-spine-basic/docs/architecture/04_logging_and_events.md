# Logging and Events

This document explains the structured logging system: how events are formatted, what fields are included, and how to use logs for debugging and dashboards.

## Design Goals

The logging system is designed for:

1. **Debuggability** — Trace any execution through all steps
2. **Dashboard ingestion** — Stable event schema for metrics/alerts
3. **Performance visibility** — Timing for every major operation
4. **Low noise** — DEBUG for details, INFO for summaries

## Log Format

All logs use structured key=value format:

```
2025-12-26T10:15:32.123Z [info] execution.summary
    execution_id=abc-123
    pipeline=otc.ingest_week
    status=completed
    duration_ms=1234.56
    rows_out=50000
```

### Timestamp Format

All timestamps are **UTC ISO-8601 with Z suffix**:

```
2025-12-26T10:15:32.123456Z
```

This ensures:
- Consistent timezone handling
- Sortable strings
- Dashboard compatibility

## Event Naming

Events follow a hierarchical naming convention:

```
{component}.{operation}[.{phase}]
```

Examples:
- `execution.submitted` — Execution lifecycle
- `ingest.parse_file.start` — Step start
- `ingest.parse_file.end` — Step end
- `normalize.validated` — Operation result
- `execution.summary` — Final summary

## Field Categories

### Core Fields (Always Present)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | UTC ISO-8601 with Z |
| `level` | string | `debug`, `info`, `warning`, `error` |
| `event` | string | Stable event identifier |

### Tracing Fields

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | string | Unique pipeline execution ID |
| `span_id` | string | Current operation span (8 hex chars) |
| `parent_span_id` | string | Parent span for nesting |

### Context Fields

| Field | Type | Description |
|-------|------|-------------|
| `pipeline` | string | Pipeline name |
| `domain` | string | Domain name (e.g., "otc") |
| `step` | string | Current processing step |
| `backend` | string | Execution backend ("sync") |

### Metric Fields

| Field | Type | Description |
|-------|------|-------------|
| `duration_ms` | float | Operation duration |
| `rows_in` | int | Input row count |
| `rows_out` | int | Output row count |
| `rows_rejected` | int | Rejected row count |
| `table` | string | Database table name |

### Error Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "failed" |
| `error_type` | string | Exception class name |
| `error_message` | string | Error description |
| `error_stack` | string | Full stack trace |

## Key Events

### `execution.submitted`

Logged when a pipeline is submitted for execution:

```
[info] execution.submitted
    execution_id=abc-123
    pipeline=otc.ingest_week
    lane=normal
    trigger_source=cli
```

### `execution.summary`

Logged once per execution with final status:

```
[info] execution.summary
    execution_id=abc-123
    pipeline=otc.ingest_week
    status=completed
    duration_ms=1234.56
    rows_out=50000
```

On failure:

```
[error] execution.summary
    execution_id=abc-123
    pipeline=otc.normalize_week
    status=failed
    error_type=PipelineError
    error_message='No raw data found for this week'
```

### Step Events

Every `log_step()` emits start and end events:

```
[debug] ingest.parse_file.start
    span_id=e21aef49
    file=data/file.psv

[info] ingest.parse_file.end
    span_id=e21aef49
    duration_ms=234.56
    rows_parsed=50000
```

## Using `log_step`

The `log_step` context manager provides timing and tracing:

```python
from market_spine.logging import log_step

with log_step("normalize.validate", rows_in=50000) as timer:
    result = validate_records(records)
    timer.add_metric("rows_out", result.accepted_count)
    timer.add_metric("rows_rejected", result.rejected_count)
```

This logs:
1. `normalize.validate.start` at DEBUG level (with `rows_in`)
2. `normalize.validate.end` at INFO level (with `duration_ms` + all metrics)

### Nested Steps

Steps can be nested, and parent/child spans are tracked:

```python
with log_step("outer") as outer:
    with log_step("inner") as inner:
        # inner.parent_span_id == outer.span_id
        pass
```

## Logging Context

The logging context automatically attaches fields to all logs:

```python
from market_spine.logging import set_context, bind_context, clear_context

# Set full context (replaces)
set_context(execution_id="abc-123", pipeline="otc.ingest_week")

# Add to existing context (merges)
bind_context(domain="otc", step="ingest")

# Clear after execution
clear_context()
```

The Dispatcher sets context at execution start and clears it at end.

## Log Levels

| Level | Use Case | Examples |
|-------|----------|----------|
| `DEBUG` | Internal details, step starts | param values, SQL details |
| `INFO` | Normal operations, step ends | row counts, durations |
| `WARNING` | Recoverable issues | skipped files, retry |
| `ERROR` | Failures | validation errors, crashes |

### Controlling Log Level

Set via environment variable:

```bash
$env:SPINE_LOG_LEVEL = "DEBUG"  # See all details
$env:SPINE_LOG_LEVEL = "INFO"   # Normal operation
$env:SPINE_LOG_LEVEL = "WARNING"  # Quiet mode
```

## Dashboard Integration

The stable event schema enables dashboard queries:

### Execution Summary Table

```sql
SELECT 
    timestamp,
    execution_id,
    pipeline,
    status,
    duration_ms,
    rows_out,
    error_message
FROM logs 
WHERE event = 'execution.summary'
ORDER BY timestamp DESC
```

### Pipeline Performance

```sql
SELECT 
    DATE(timestamp) as day,
    pipeline,
    COUNT(*) as executions,
    AVG(duration_ms) as avg_duration,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
FROM logs 
WHERE event = 'execution.summary'
GROUP BY day, pipeline
```

### Tracing an Execution

```sql
SELECT * FROM logs 
WHERE execution_id = 'abc-123'
ORDER BY timestamp
```

### Finding Slow Operations

```sql
SELECT event, AVG(duration_ms), MAX(duration_ms)
FROM logs
WHERE event LIKE '%.end'
GROUP BY event
ORDER BY AVG(duration_ms) DESC
```

## JSON Format

For production log aggregation, use JSON format:

```bash
$env:SPINE_LOG_FORMAT = "json"
```

Output:
```json
{
  "timestamp": "2025-12-26T10:15:32.123456Z",
  "level": "info",
  "event": "execution.summary",
  "execution_id": "abc-123",
  "pipeline": "otc.ingest_week",
  "status": "completed",
  "duration_ms": 1234.56
}
```

## Best Practices

### 1. Use Stable Event Names

Events are the primary filter key. Keep them stable:

```python
# Good - stable, hierarchical
log.info("normalize.validated", rows=100)

# Bad - dynamic values in event name
log.info(f"normalize_{tier}_validated", rows=100)
```

### 2. Metrics in Fields, Not Messages

```python
# Good - structured
log.info("ingest.completed", rows=50000, duration_ms=1234)

# Bad - buried in message
log.info(f"Ingest completed: 50000 rows in 1234ms")
```

### 3. Log Step Boundaries

Major operations should use `log_step`:

```python
with log_step("ingest.bulk_insert", table="otc_raw", rows=50000):
    conn.executemany(sql, data)
```

### 4. Include Context Keys

When logging errors, include keys for filtering:

```python
log.error("normalize.no_raw_data", 
    week_ending=str(week), 
    tier=tier.value)
```

## Next Steps

- [Logging Schema Reference](../logging-schema.md) — Full field reference
- [Structured Logging ADR](../decisions/004_structured_logging_schema.md) — Design decisions
