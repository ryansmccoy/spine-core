# spine.observability

Structured logging and metrics for operational visibility.

## Modules

| Module | Purpose |
|--------|---------|
| `logging` | `get_logger()`, `configure_logging()`, `LogContext` |
| `metrics` | `Counter`, `Gauge`, `Histogram`, `MetricsRegistry` |

## Structured Logging

spine-core uses [structlog](https://www.structlog.org/) for JSON-formatted, context-rich logging:

```python
from spine.observability.logging import get_logger

logger = get_logger("my_module")

# Structured key-value logging
logger.info("processing_started", batch_id="batch-001", record_count=42)
# Output: {"event": "processing_started", "batch_id": "batch-001", "record_count": 42, "timestamp": "..."}

# Context binding for a scope
bound = logger.bind(workflow="etl", run_id="run-123")
bound.info("step_started", step="extract")
bound.info("step_completed", step="extract", duration_ms=150)
```

### Log Context Propagation

```python
from spine.observability.logging import LogContext

with LogContext(batch_id="batch-001", source="api"):
    logger.info("inside context")  # batch_id and source auto-attached
```

## Metrics

Prometheus-style metrics for monitoring:

```python
from spine.observability.metrics import Counter, Gauge, Histogram, MetricsRegistry

registry = MetricsRegistry()

# Count events
requests = registry.counter("requests_total", "Total requests")
requests.inc()

# Track current values
active = registry.gauge("active_connections", "Active connections")
active.set(5)

# Measure distributions
latency = registry.histogram("request_duration_seconds", "Request latency")
latency.observe(0.25)
```

## API Reference

The observability module is lightweight — see the source directly:

- `src/spine/observability/logging.py` — Logger factory and context
- `src/spine/observability/metrics.py` — Counter, Gauge, Histogram, MetricsRegistry
