# spine-core

**Platform primitives for temporal data pipelines in Python.**

[![CI](https://github.com/ryansmccoy/spine-core/actions/workflows/ci.yml/badge.svg)](https://github.com/ryansmccoy/spine-core/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ryansmccoy/spine-core/graph/badge.svg)](https://codecov.io/gh/ryansmccoy/spine-core)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

spine-core provides the foundational building blocks for reliable data pipelines: a `Result` monad for explicit error handling, retry strategies, circuit breakers, rate limiters, workflow orchestration, and a quality-gate framework — all with zero heavy dependencies.

## Install

```bash
pip install spine-core
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add spine-core
```

**Optional extras:**

```bash
pip install spine-core[settings]   # pydantic-settings support
pip install spine-core[mcp]        # Model Context Protocol support
pip install spine-core[postgresql] # PostgreSQL (psycopg2)
pip install spine-core[mysql]      # MySQL (mysql-connector-python)
pip install spine-core[db2]        # IBM DB2 (ibm-db)
pip install spine-core[oracle]     # Oracle (oracledb)
pip install spine-core[all]        # everything
```

## Quick Start

### Result Monad

```python
from spine.core.result import Ok, Err, Result

def parse_amount(raw: str) -> Result[float]:
    try:
        return Ok(float(raw.replace(",", "")))
    except ValueError as e:
        return Err(f"Bad amount: {raw}", error=e)

result = parse_amount("1,234.56")
value = result.unwrap_or(0.0)  # 1234.56
```

### Retry with Backoff

```python
from spine.execution.retry import RetryStrategy, ExponentialBackoff

strategy = RetryStrategy(
    max_retries=3,
    backoff=ExponentialBackoff(base_seconds=1.0),
)
result = strategy.execute(lambda: fetch_data())
```

### Circuit Breaker

```python
from spine.execution.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
with breaker:
    response = call_external_api()
```

### Workflow Orchestration

```python
from spine.orchestration.workflow import Workflow
from spine.orchestration.step_types import lambda_step
from spine.orchestration.workflow_runner import WorkflowRunner

wf = Workflow(name="etl")
wf.add_step(lambda_step("extract", fn=extract))
wf.add_step(lambda_step("transform", fn=transform))
wf.add_step(lambda_step("load", fn=load))

runner = WorkflowRunner()
result = runner.run(wf)
```

## Features

| Module | What it does |
|---|---|
| **`spine.core.result`** | `Result[T]` / `Ok` / `Err` with `map`, `flat_map`, `or_else`, `collect_results` |
| **`spine.core.errors`** | `SpineError` hierarchy with error categories and retry semantics |
| **`spine.core.temporal`** | `WeekEnding` Friday-aligned date type for financial calendars |
| **`spine.core.manifest`** | `WorkManifest` for multi-stage workflow progress tracking |
| **`spine.core.quality`** | Quality-gate runner for data validation checkpoints |
| **`spine.core.dialect`** | Portable SQL generation for SQLite, PostgreSQL, MySQL, DB2, Oracle |
| **`spine.core.repository`** | `BaseRepository` with dialect-aware query helpers |
| **`spine.core.adapters`** | Connection pooling and lifecycle for 5 database backends |
| **`spine.core.timestamps`** | `generate_ulid`, `utc_now`, ISO-8601 helpers |
| **`spine.execution`** | `Dispatcher`, `Executor`, `WorkSpec`, `RetryStrategy`, `CircuitBreaker`, `RateLimiter`, `BatchBuilder`, `ConcurrencyGuard` |
| **`spine.orchestration`** | `Workflow`, `Step`, `WorkflowRunner`, `TrackedWorkflowRunner`, YAML workflow loading |
| **`spine.framework`** | Pipeline ABC, `@register_pipeline`, source connectors, alert routing |
| **`spine.observability`** | Structured JSON logging, `LogContext`, context propagation |

## Project Structure

```
src/spine/
├── core/           # Primitives: Result, errors, temporal, quality, manifest
├── execution/      # Dispatcher, executors, retry, circuit breaker, rate limiter
├── orchestration/  # Workflow engine, steps, runners, YAML loader
├── framework/      # Pipeline framework, sources, alerts, registry
└── observability/  # Structured logging, context propagation
```

## Examples

49 runnable examples organized by topic:

```
examples/
├── 01_core/          # Result, errors, temporal, quality gates
├── 02_execution/     # Dispatcher, executors, retry
├── 03_resilience/    # Circuit breaker, rate limiter, concurrency
├── 04_orchestration/ # Workflows, steps, YAML loading
├── 05_infrastructure/# Full pipeline demos
├── 06_observability/ # Logging, context propagation
├── 07_real_world/    # SEC filing, feed ingestion, market data
└── 08_framework/     # Pipeline framework, registry
```

Run any example:

```bash
uv run python examples/01_core/01_result_basics.py
```

## Development

```bash
git clone https://github.com/mccoy-lab/py-sec-edgar.git
cd py-sec-edgar/spine-core
uv sync --dev
```

```bash
make test          # run tests (excludes slow)
make test-all      # run all tests including slow/integration
make test-cov      # run tests with coverage
make lint          # ruff check
make format        # ruff format
make build         # build wheel
```

### Requirements

- Python 3.12+
- Runtime: `structlog`, `pydantic`
- Dev: `pytest`, `ruff`, `uv`

## License

[MIT](LICENSE)
