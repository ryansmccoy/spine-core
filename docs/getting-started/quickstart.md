# Quick Start

This guide walks through the core building blocks of spine-core in 5 minutes.

## 1. Result Pattern — Explicit Error Handling

The `Result[T]` type replaces exceptions with explicit success/failure values:

```python
from spine.core.result import Ok, Err, Result

def parse_amount(raw: str) -> Result[float]:
    try:
        return Ok(float(raw.replace(",", "")))
    except ValueError as e:
        return Err(f"Bad amount: {raw}", error=e)

result = parse_amount("1,234.56")
value = result.unwrap_or(0.0)  # 1234.56

# Chain operations
final = (
    parse_amount("100")
    .map(lambda x: x * 1.1)       # Ok(110.0)
    .flat_map(lambda x: Ok(round(x, 2)))  # Ok(110.0)
)
```

## 2. Retry with Backoff

Wrap unreliable operations with automatic retry:

```python
from spine.execution.retry import RetryStrategy, ExponentialBackoff

strategy = RetryStrategy(
    max_retries=3,
    backoff=ExponentialBackoff(base_seconds=1.0),
)
result = strategy.execute(lambda: fetch_data())
```

## 3. Circuit Breaker

Prevent cascading failures when calling external services:

```python
from spine.execution.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

with breaker:
    response = call_external_api()

# After 5 failures, the breaker opens and calls fail immediately
# After 30s, it enters half-open state and allows a probe request
```

## 4. Rate Limiting

Throttle requests to respect API limits:

```python
from spine.execution.rate_limit import TokenBucketLimiter

limiter = TokenBucketLimiter(rate=10.0, capacity=20)

if limiter.acquire():
    make_api_call()
```

## 5. Workflow Orchestration

Build multi-step data pipelines:

```python
from spine.orchestration.workflow import Workflow
from spine.orchestration.step_types import lambda_step
from spine.orchestration.workflow_runner import WorkflowRunner

wf = Workflow(name="etl")
wf.add_step(lambda_step("extract", fn=extract_data))
wf.add_step(lambda_step("transform", fn=transform_data))
wf.add_step(lambda_step("load", fn=load_data))

runner = WorkflowRunner()
result = runner.run(wf)
```

## 6. Quality Gates

Validate data at checkpoints:

```python
from spine.core.quality import QualityRunner, QualityCheck

checks = [
    QualityCheck(
        name="row_count",
        check_fn=lambda data: len(data) > 0,
        severity="ERROR",
    ),
    QualityCheck(
        name="no_nulls",
        check_fn=lambda data: all(r.get("id") for r in data),
        severity="WARN",
    ),
]

runner = QualityRunner(checks)
report = runner.run(my_data)

if report.passed:
    print("All quality gates passed")
```

## 7. Structured Logging

JSON-formatted logs with context propagation:

```python
from spine.observability.logging import get_logger

logger = get_logger("my_module")
logger.info("processing_started", batch_id="batch-001", record_count=42)
# {"event": "processing_started", "batch_id": "batch-001", "record_count": 42, ...}
```

## Next Steps

- Browse the [49 runnable examples](https://github.com/mccoy-lab/py-sec-edgar/tree/main/spine-core/examples)
- Read the [Core Concepts](../concepts/overview.md) for deeper understanding
- Explore the [API Reference](../api/core.md) for full module documentation
- Review the [Architecture](../architecture/CORE_PRIMITIVES.md) docs for design details
