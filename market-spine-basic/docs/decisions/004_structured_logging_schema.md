# ADR 004: Structured Logging Schema

**Status**: Accepted  
**Date**: January 2026  
**Context**: Observability for Market Spine pipelines

## Decision

All log events use a structured schema with:
1. **Stable event names** for filtering
2. **Consistent field names** for dashboards
3. **UTC ISO-8601 timestamps** with Z suffix
4. **Tracing fields** for correlation

This schema is a contract. Changes require a version bump.

## Context

Pipeline observability requires:
- Tracing execution flow
- Measuring performance
- Alerting on failures
- Building dashboards

Ad-hoc logging doesn't support this. We need a stable schema that tools can rely on.

## The Schema

### Core Fields

Always present on every log entry:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | `2026-01-03T10:15:32.123456Z` |
| `level` | string | `debug`, `info`, `warning`, `error` |
| `event` | string | Hierarchical event name |

### Tracing Fields

For correlating related logs:

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | string | UUID for pipeline execution |
| `span_id` | string | 8-hex-char operation identifier |
| `parent_span_id` | string | Parent span for nesting |

### Context Fields

Set by the Dispatcher and pipelines:

| Field | Type | Description |
|-------|------|-------------|
| `pipeline` | string | Pipeline name |
| `domain` | string | Domain name (e.g., "otc") |
| `step` | string | Current processing step |
| `backend` | string | Execution backend |

### Metric Fields

For performance tracking:

| Field | Type | Description |
|-------|------|-------------|
| `duration_ms` | float | Operation duration |
| `rows_in` | int | Input row count |
| `rows_out` | int | Output row count |
| `rows_rejected` | int | Rejected row count |
| `table` | string | Database table |

### Error Fields

For failure analysis:

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"failed"` |
| `error_type` | string | Exception class |
| `error_message` | string | Error description |
| `error_stack` | string | Full traceback |

## Key Events

### `execution.summary`

The primary event for dashboards. Emitted once per execution:

```
[info] execution.summary
    execution_id=abc-123
    pipeline=otc.ingest_week
    status=completed
    duration_ms=1234.56
    rows_out=50000
```

### Step Events

Every `log_step()` emits:

```
[debug] step_name.start span_id=xxx
[info]  step_name.end   span_id=xxx duration_ms=123.45
```

## Design Choices

### Why UTC?

Local time causes:
- Sorting issues
- Dashboard confusion
- Timezone bugs

UTC with Z suffix is unambiguous:
```
2026-01-03T10:15:32.123456Z
```

### Why Hierarchical Event Names?

Enables prefix filtering:
- `execution.*` — All execution events
- `ingest.*` — All ingest events
- `*.error` — All error events

Format: `{component}.{operation}[.{phase}]`

### Why Stable Field Names?

Dashboards break when field names change. We commit to:
- `duration_ms` (not `duration`, `elapsed`, `time`)
- `rows_in` / `rows_out` / `rows_rejected` (not `input_count`, `records`)
- `execution_id` (not `exec_id`, `id`)

### Why Omit Default Values?

The `attempt` field defaults to 1. We omit it when 1:

```python
# attempt=1 → not logged (noise reduction)
# attempt=2 → logged (meaningful for retries)
```

## Implementation

### Logging Configuration

```python
# market_spine/logging/config.py
processors = [
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    add_context_processor,  # Adds execution_id, pipeline, etc.
    structlog.processors.format_exc_info,
]
```

### Context Management

```python
# Dispatcher sets context
set_context(
    execution_id=execution_id,
    pipeline=pipeline_name,
    backend="sync",
)

# Pipelines extend context
bind_context(domain="otc", step="ingest")

# log_step adds span tracing
with log_step("operation", rows_in=100) as timer:
    timer.add_metric("rows_out", 95)
```

## Consequences

### Positive

1. **Dashboard compatibility** — Stable field names work with Grafana, etc.
2. **Grep-friendly** — `grep 'execution.summary'` works
3. **Traceable** — Every log links to its execution
4. **Timing built-in** — `duration_ms` on every step

### Negative

1. **Rigidity** — Schema changes require coordination
2. **Verbosity** — Structured fields vs. simple messages
3. **Learning curve** — Developers must follow conventions

### Mitigation

- Document the schema (this ADR + logging-schema.md)
- Provide `log_step()` helper that does the right thing
- Code review for logging consistency

## Versioning

Schema version is implicit in documentation. Breaking changes:
1. Add to this ADR
2. Update logging-schema.md
3. Announce in release notes

Non-breaking changes (adding fields) don't require coordination.

## Related

- [Logging and Events](../architecture/04_logging_and_events.md) — Usage guide
- [logging-schema.md](../logging-schema.md) — Field reference
- `market_spine/logging/` — Implementation
