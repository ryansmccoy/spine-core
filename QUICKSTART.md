# spine-core — Quickstart

> From zero to production primitives in 5 minutes.

## Install

```bash
pip install spine-core              # Zero dependencies
pip install spine-core[cli]         # + CLI tools
# or
uv add spine-core
```

---

## 1. Result Monad — Explicit Success/Failure

```python
from spine import Result, Ok, Err

def divide(a: float, b: float) -> Result[float, str]:
    if b == 0:
        return Err("Division by zero")
    return Ok(a / b)

# Unwrap safely
result = divide(10, 3)
print(result.unwrap())  # 3.333...

# Chain with map/flat_map
total = (
    divide(100, 4)
    .map(lambda x: x * 2)       # 50.0
    .flat_map(lambda x: divide(x, 5))  # 10.0
)
print(total.unwrap())  # 10.0

# Pattern match
match divide(10, 0):
    case Ok(value):
        print(f"Got: {value}")
    case Err(error):
        print(f"Error: {error}")  # "Division by zero"
```

---

## 2. Retry with Backoff

```python
from spine import RetryPolicy
import httpx

policy = RetryPolicy(
    max_attempts=3,
    backoff_base=1.0,    # 1s, 2s, 4s
    jitter=True,
)

@policy
def fetch_filing(url: str) -> dict:
    resp = httpx.get(url)
    resp.raise_for_status()
    return resp.json()
```

---

## 3. Circuit Breaker

```python
from spine import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,    # Open after 5 failures
    recovery_timeout=30,    # Try again after 30s
)

@breaker
def call_sec_api(endpoint: str) -> dict:
    ...

# After 5 failures, subsequent calls fail fast (no network hit)
# After 30s, one probe call is allowed through
```

---

## 4. Workflow Composition

```python
from spine import Workflow, Step

# Define steps
extract = Step("extract", fn=extract_data)
transform = Step("transform", fn=transform_data, depends_on=["extract"])
load = Step("load", fn=load_data, depends_on=["transform"])

# Compose into workflow
pipeline = Workflow(
    name="etl_pipeline",
    steps=[extract, transform, load],
)

# Run
result = pipeline.run(input_data={"source": "sec_filings"})
```

---

## 5. Database (Tiered Storage)

```python
from spine import DatabaseManager

# Tier 0: In-memory (tests)
db = DatabaseManager("memory://")

# Tier 1: SQLite (development) — stdlib only
db = DatabaseManager("sqlite:///spine.db")

# Tier 2: DuckDB (analytics)
db = DatabaseManager("duckdb:///spine.duckdb")

# Tier 3: PostgreSQL (production)
db = DatabaseManager("postgresql://user:pass@localhost/spine")

# Same API regardless of backend
db.initialize()
db.execute("SELECT * FROM runs WHERE status = ?", ["completed"])
```

---

## 6. Observability

```python
from spine import get_logger, MetricsCollector

# Structured logging
log = get_logger("my_pipeline")
log.info("Processing filing", cik="0000320193", form_type="10-K")

# Metrics
metrics = MetricsCollector()
with metrics.timer("fetch_duration"):
    data = fetch_filing(url)
metrics.increment("filings_processed")
```

---

## 7. CLI

```bash
# See all commands
uv run spine-core --help

# Database management
uv run spine-core db init
uv run spine-core db status
uv run spine-core db migrate

# Run a workflow
uv run spine-core workflow run pipeline.py

# Scheduling
uv run spine-core scheduler start

# Quality checks
uv run spine-core quality check .
```

---

## Next Steps

| What | Where |
|------|-------|
| Core concepts glossary | [docs/CONCEPTS.md](docs/CONCEPTS.md) |
| All 142 examples | `examples/` directory |
| Examples tour | [docs/EXAMPLES_TOUR.md](docs/EXAMPLES_TOUR.md) |
| Full Spine ecosystem | [SPINE_ARCHITECTURE.md](../SPINE_ARCHITECTURE.md) |
