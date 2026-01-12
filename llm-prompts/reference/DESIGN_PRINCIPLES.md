# Design Principles Reference

> **Purpose:** Comprehensive design principles for spine-core to ensure "write once, never rewrite"
> **Status:** Canonical Reference Document
> **Scope:** All tiers, all modules, all contributors (human and LLM)

---

## Quick Reference Table

| # | Principle | One-Liner | Key Practice |
|---|-----------|-----------|--------------|
| 1 | **Write Once** | Design for tomorrow's requirements today | Protocol + Registry = extensibility |
| 2 | **Protocol-First** | Define contracts before implementations | `Protocol` classes with `@runtime_checkable` |
| 3 | **Registry-Driven** | No branching factories, ever | `@REGISTRY.register("name")` |
| 4 | **Composition Over Inheritance** | Compose behaviors, don't inherit | Small protocols, dependency injection |
| 5 | **Immutability by Default** | Frozen dataclasses, no mutation | `@dataclass(frozen=True)` |
| 6 | **Fail Fast** | Validate early, surface errors immediately | Quality gates before compute |
| 7 | **Errors as Values** | Return structured results, don't just raise | `StepResult(ok=False, error=...)` |
| 8 | **Idempotency** | Same inputs → same outputs, always | DELETE + INSERT, deterministic IDs |
| 9 | **Explicit Over Implicit** | No magic, clear data flow | Named parameters, no monkey-patching |
| 10 | **Separation of Concerns** | Each module does one thing well | Layers: Core → Framework → Domains → App |
| 11 | **Progressive Enhancement** | Basic works first, advanced enhances | SQLite → PostgreSQL → DB2 |
| 12 | **Backward Compatibility** | v1 and v2 coexist peacefully | Deprecate, don't delete |
| 13 | **Observable by Default** | Everything traceable, nothing hidden | capture_id, execution_id, anomalies |
| 14 | **Test-Driven Contracts** | Tests define the contract | Fitness tests for multi-pipeline workflows |

---

## Detailed Principles

### 1. Write Once

> *"The best code is code you never have to touch again."*

**Philosophy:**
Every feature should be designed with future extensibility in mind. If adding a new database, source, or alert channel requires modifying existing code, the design is wrong.

**Key Practices:**

```python
# ❌ WRONG: Adding PostgreSQL requires modifying this function
def get_connection(db_type: str):
    if db_type == "sqlite":
        return sqlite3.connect("app.db")
    elif db_type == "postgres":  # <- New requirement = code change
        return psycopg2.connect(...)

# ✅ CORRECT: Adding PostgreSQL is just a new file
@DATABASE_ADAPTERS.register("sqlite")
class SQLiteAdapter(DatabaseAdapter):
    def connect(self) -> Connection: ...

@DATABASE_ADAPTERS.register("postgres")  # <- New file, no changes to existing code
class PostgresAdapter(DatabaseAdapter):
    def connect(self) -> Connection: ...
```

**Checklist:**
- [ ] Can I add a new implementation without touching existing files?
- [ ] Does my design use protocols + registries?
- [ ] Are all extension points documented?

---

### 2. Protocol-First

> *"Define the contract before you build the implementation."*

**Philosophy:**
Protocols define WHAT something does. Implementations define HOW. Design the protocol first, then build implementations.

**Key Practices:**

```python
from typing import Protocol, runtime_checkable

# Step 1: Define the contract
@runtime_checkable
class Source(Protocol):
    """All data sources MUST implement this contract."""
    
    def fetch(self, params: dict[str, Any]) -> SourceResult:
        """Fetch data from the source."""
        ...
    
    @property
    def source_type(self) -> str:
        """Unique identifier for this source type."""
        ...

# Step 2: Implementations fulfill the contract
class FileSource:
    def fetch(self, params: dict[str, Any]) -> SourceResult:
        path = Path(params["path"])
        return SourceResult(data=path.read_bytes(), metadata={...})
    
    @property
    def source_type(self) -> str:
        return "file"
```

**Benefits:**
- Type checkers enforce contracts at development time
- `isinstance(obj, Source)` works at runtime
- Implementations are decoupled from consumers

---

### 3. Registry-Driven

> *"No if/elif factories. Ever."*

**Philosophy:**
Factories with if/elif chains violate Open/Closed Principle. Registries allow adding new implementations without modifying existing code.

**Key Practices:**

```python
# ❌ FORBIDDEN
def get_source(name: str) -> Source:
    if name == "file":
        return FileSource()
    elif name == "http":
        return HttpSource()
    elif name == "database":  # <- Every new source = modify this
        return DatabaseSource()

# ✅ REQUIRED
SOURCES: Registry[Source] = Registry("sources")

@SOURCES.register("file")
class FileSource(Source): ...

@SOURCES.register("http")
class HttpSource(Source): ...

# Usage
source = SOURCES.get("file")
```

**Registry Pattern:**
```python
class Registry(Generic[T]):
    def __init__(self, name: str):
        self._name = name
        self._items: dict[str, type[T]] = {}
    
    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        def decorator(cls: type[T]) -> type[T]:
            self._items[name] = cls
            return cls
        return decorator
    
    def get(self, name: str, **kwargs) -> T:
        return self._items[name](**kwargs)
    
    def list(self) -> list[str]:
        return list(self._items.keys())
```

---

### 4. Composition Over Inheritance

> *"Prefer 'has-a' over 'is-a'."*

**Philosophy:**
Deep inheritance hierarchies are rigid and hard to test. Compose small, focused behaviors instead.

**Key Practices:**

```python
# ❌ FRAGILE: Deep inheritance
class BasePipeline:
    def run(self): ...

class ValidatedPipeline(BasePipeline):
    def run(self):
        self.validate()
        super().run()

class LoggedValidatedPipeline(ValidatedPipeline):
    def run(self):
        self.log_start()
        super().run()
        self.log_end()

# ✅ ROBUST: Composition
@dataclass
class PipelineConfig:
    validators: list[Validator]
    logger: Logger | None = None
    error_handler: ErrorHandler | None = None

class Pipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
    
    def run(self, context: Context) -> Result:
        for validator in self.config.validators:
            validator.validate(context)
        
        result = self._execute(context)
        
        if self.config.logger:
            self.config.logger.log(result)
        
        return result
```

**Guidelines:**
- Max inheritance depth: 2 (Base → Concrete)
- Prefer protocols over abstract base classes
- Inject dependencies, don't inherit them

---

### 5. Immutability by Default

> *"Once created, never changed."*

**Philosophy:**
Mutable state is the source of most bugs. Use frozen dataclasses by default. Explicit mutation through new instances.

**Key Practices:**

```python
from dataclasses import dataclass, replace

# ✅ CORRECT: Frozen by default
@dataclass(frozen=True)
class StepResult:
    step_id: str
    ok: bool
    output: dict[str, Any] | None = None
    error: SpineError | None = None

# To "modify", create new instance
result = StepResult(step_id="step-1", ok=True, output={"rows": 100})
updated = replace(result, ok=False, error=some_error)  # New instance

# ❌ WRONG: Mutable dataclass
@dataclass
class MutableResult:
    status: str  # Can be changed anywhere, hard to track

result.status = "failed"  # Who changed this? When? Why?
```

**When Mutability is OK:**
- Collections being built (then freeze before returning)
- Performance-critical inner loops (rare)
- External library requirements

---

### 6. Fail Fast

> *"Validate at the boundary, not in the middle."*

**Philosophy:**
Check preconditions immediately. Don't let invalid data propagate through the system.

**Key Practices:**

```python
# ✅ CORRECT: Validate at entry point
class Pipeline:
    def run(self, params: dict) -> Result:
        # 1. Validate FIRST
        self._validate_params(params)
        
        # 2. Quality gates BEFORE compute
        ok, issues = self._check_quality_gates(params)
        if not ok:
            return Result.failed(f"Quality gate failed: {issues}")
        
        # 3. Only then proceed
        return self._execute(params)
    
    def _validate_params(self, params: dict) -> None:
        if "week_ending" not in params:
            raise ValidationError("week_ending is required")
        
        week = params["week_ending"]
        if not is_valid_week_format(week):
            raise ValidationError(f"Invalid week format: {week}")

# ❌ WRONG: Validate deep in execution
def _compute_rolling(self, data):
    for row in data:
        if row["week"] is None:  # <- Too late! Already processing
            continue  # Silent skip = hidden bug
```

---

### 7. Errors as Values

> *"Don't just raise, return structured results."*

**Philosophy:**
Exceptions interrupt flow and are easy to miss. Return structured results that force callers to handle both success and failure.

**Key Practices:**

```python
from dataclasses import dataclass
from typing import TypeVar, Generic

T = TypeVar("T")

@dataclass(frozen=True)
class Result(Generic[T]):
    """Explicit success/failure container."""
    ok: bool
    value: T | None = None
    error: SpineError | None = None
    
    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(ok=True, value=value)
    
    @classmethod
    def failure(cls, error: SpineError) -> "Result[T]":
        return cls(ok=False, error=error)

# Usage
def fetch_data(url: str) -> Result[bytes]:
    try:
        response = requests.get(url)
        response.raise_for_status()
        return Result.success(response.content)
    except requests.HTTPError as e:
        return Result.failure(SpineError(
            category=ErrorCategory.NETWORK,
            message=f"HTTP {e.response.status_code}",
            retryable=True
        ))

# Caller MUST handle
result = fetch_data("https://api.example.com/data")
if result.ok:
    process(result.value)
else:
    handle_error(result.error)
```

**When to Raise Exceptions:**
- Programmer errors (assertion failures)
- Unrecoverable system errors
- Violation of invariants that should never happen

---

### 8. Idempotency

> *"Same inputs, same outputs. Every time."*

**Philosophy:**
Running the same operation twice should produce the same result, never duplicates or inconsistencies.

**Key Practices:**

```python
# ✅ CORRECT: Capture ID + DELETE-INSERT
def persist_results(conn, capture_id: str, rows: list[dict]) -> None:
    """Idempotent write: reruns produce same state."""
    # 1. Delete existing (if any)
    conn.execute(
        "DELETE FROM calculations WHERE capture_id = ?",
        (capture_id,)
    )
    
    # 2. Insert fresh
    conn.executemany(
        "INSERT INTO calculations (...) VALUES (...)",
        rows
    )
    
    # Re-running with same capture_id = same final state

# ✅ CORRECT: Deterministic IDs
def generate_capture_id(domain: str, stage: str, 
                        partition: str, timestamp: datetime) -> str:
    """Deterministic ID from inputs."""
    return f"{domain}.{stage}.{partition}.{timestamp.strftime('%Y%m%dT%H%M%SZ')}"
```

**Idempotency Tests:**
```python
def test_idempotency():
    # Run twice with same inputs
    result1 = pipeline.run(week="2025-01-10", tier="NMS_TIER_1")
    result2 = pipeline.run(week="2025-01-10", tier="NMS_TIER_1")
    
    # Results should be identical
    assert result1.row_count == result2.row_count
    
    # No duplicates in database
    count = conn.execute(
        "SELECT COUNT(*) FROM calculations WHERE capture_id = ?",
        (result1.capture_id,)
    ).fetchone()[0]
    assert count == result1.row_count
```

---

### 9. Explicit Over Implicit

> *"No magic. Clear data flow."*

**Philosophy:**
Code should be readable without deep knowledge of hidden behaviors. Named parameters over positional. No monkey-patching.

**Key Practices:**

```python
# ❌ IMPLICIT: What does True, False, 5 mean?
process_data("data.csv", True, False, 5)

# ✅ EXPLICIT: Self-documenting
process_data(
    source_path="data.csv",
    validate=True,
    skip_errors=False,
    max_retries=5
)

# ❌ IMPLICIT: Magic attribute injection
class Pipeline:
    def run(self):
        # Where did self.conn come from?
        self.conn.execute(...)

# ✅ EXPLICIT: Dependency injection
class Pipeline:
    def __init__(self, conn: Connection):
        self.conn = conn
    
    def run(self) -> Result:
        self.conn.execute(...)
```

---

### 10. Separation of Concerns

> *"Each module does one thing well."*

**Philosophy:**
Clear boundaries between layers. Each layer has a single responsibility.

**Layer Responsibilities:**

| Layer | Responsibility | NOT Responsible For |
|-------|----------------|---------------------|
| **Core** | Primitives, protocols | Business logic |
| **Framework** | Registries, execution | Domain specifics |
| **Domains** | Business calculations | HTTP, CLI |
| **App (API/CLI)** | Input/output adapters | Business logic |
| **Frontend** | User interface | Any data logic |

```python
# ✅ CORRECT: CLI is thin adapter
@app.command()
def run_pipeline(name: str, week: str):
    """CLI just dispatches, no logic."""
    pipeline = PIPELINES.get(name)
    result = pipeline.run(week_ending=week)
    typer.echo(f"Completed: {result.row_count} rows")

# ❌ WRONG: CLI contains business logic
@app.command()
def run_pipeline(name: str, week: str):
    """CLI doing too much."""
    conn = get_connection()
    data = fetch_from_api(...)  # <- Should be in domain
    transformed = apply_business_rules(data)  # <- Should be in domain
    conn.execute("INSERT INTO ...", transformed)  # <- Should be in domain
```

---

### 11. Progressive Enhancement

> *"Start simple, enhance incrementally."*

**Philosophy:**
Design features that work at the simplest tier and enhance for advanced tiers. Don't require PostgreSQL for what SQLite can do.

**Key Practices:**

```python
# ✅ CORRECT: Base works everywhere, enhanced where available
class WorkflowRunner:
    def __init__(self, 
                 scheduler: Scheduler | None = None,
                 alerter: AlertChannel | None = None):
        self.scheduler = scheduler
        self.alerter = alerter
    
    def run(self, workflow: Workflow) -> WorkflowRun:
        result = self._execute(workflow)
        
        # Progressive: Alerting only if configured
        if self.alerter and result.status == "failed":
            self.alerter.send(self._format_alert(result))
        
        return result

# Usage by tier
# Basic: No scheduler, no alerter
runner = WorkflowRunner()

# Intermediate: With scheduler and Slack
runner = WorkflowRunner(
    scheduler=APScheduler(),
    alerter=SlackChannel(webhook_url=...)
)

# Full: With Celery and PagerDuty
runner = WorkflowRunner(
    scheduler=CeleryScheduler(),
    alerter=PagerDutyChannel(api_key=...)
)
```

---

### 12. Backward Compatibility

> *"Deprecate, don't delete."*

**Philosophy:**
Old code should continue working. Introduce new patterns alongside old, deprecate gracefully.

**Key Practices:**

```python
import warnings

# ✅ CORRECT: Support both, warn about old
def connect(self, config: dict | str) -> Connection:
    """Connect to database.
    
    Args:
        config: Connection config dict, or legacy connection string (deprecated)
    """
    if isinstance(config, str):
        warnings.warn(
            "String connection config is deprecated. "
            "Use dict config instead. Will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2
        )
        config = self._parse_legacy_config(config)
    
    return self._connect_with_config(config)

# Version compatibility
class WorkflowRunner:
    def run(self, workflow: Workflow, *, 
            legacy_mode: bool = False) -> WorkflowRun:
        """Run workflow with v2 or legacy v1 semantics."""
        if legacy_mode:
            return self._run_v1(workflow)
        return self._run_v2(workflow)
```

**Deprecation Timeline:**
1. **Minor version**: Add deprecation warning
2. **Major version**: Make deprecated path error
3. **Major+1 version**: Remove deprecated code

---

### 13. Observable by Default

> *"If you can't see it, you can't fix it."*

**Philosophy:**
Every operation should be traceable. Capture IDs, execution IDs, anomaly records. No silent operations.

**Key Practices:**

```python
# ✅ CORRECT: Every output has lineage
@dataclass(frozen=True)
class CalculationRow:
    # Business data
    symbol: str
    value: Decimal
    
    # Observability (REQUIRED)
    capture_id: str      # Unique per pipeline run
    captured_at: str     # When captured
    execution_id: str    # Groups related runs
    batch_id: str        # Groups batch operations
    version: int         # Calculation version

# ✅ CORRECT: Errors are visible
def process(item: Item) -> Result:
    try:
        return Result.success(compute(item))
    except ValidationError as e:
        # Record in anomaly table (visible to operators)
        record_anomaly(
            domain="finra.otc_transparency",
            stage="COMPUTE",
            severity="ERROR",
            category="VALIDATION",
            partition_key=item.partition_key,
            message=str(e)
        )
        return Result.failure(e)
```

**Observability Queries:**
```sql
-- What happened in the last hour?
SELECT * FROM core_manifest 
WHERE captured_at > datetime('now', '-1 hour')
ORDER BY captured_at DESC;

-- What errors for this partition?
SELECT * FROM core_anomalies
WHERE partition_key = '2025-01-10|NMS_TIER_1'
  AND severity = 'ERROR'
  AND resolved_at IS NULL;
```

---

### 14. Test-Driven Contracts

> *"Tests define the contract. If it's not tested, it doesn't work."*

**Philosophy:**
Tests are the source of truth for how code should behave. Write tests that verify contracts, not implementation details.

**Required Test Types:**

| Test Type | Purpose | Example |
|-----------|---------|---------|
| **Unit** | Single function correctness | `test_calculate_rolling_average` |
| **Integration** | Full pipeline with real DB | `test_pipeline_end_to_end` |
| **Determinism** | Same inputs → same outputs | `test_determinism` |
| **Idempotency** | No duplicates on rerun | `test_idempotency` |
| **Fitness** | Multi-pipeline workflows | `test_ingest_then_compute` |

```python
# ✅ CORRECT: Contract test
def test_source_protocol_contract():
    """All sources must fulfill the protocol contract."""
    for name in SOURCES.list():
        source = SOURCES.get(name)
        
        # Contract: Must implement fetch
        assert hasattr(source, "fetch")
        assert callable(source.fetch)
        
        # Contract: Must have source_type
        assert hasattr(source, "source_type")
        assert isinstance(source.source_type, str)

# ✅ CORRECT: Fitness test
def test_full_workflow_fitness():
    """Multi-pipeline workflow produces correct results."""
    # 1. Ingest
    ingest_result = pipelines["finra.ingest"].run(week="2025-01-10")
    assert ingest_result.ok
    
    # 2. Validate
    validate_result = pipelines["finra.validate"].run(week="2025-01-10")
    assert validate_result.ok
    assert validate_result.anomaly_count == 0
    
    # 3. Compute
    compute_result = pipelines["finra.compute"].run(week="2025-01-10")
    assert compute_result.ok
    assert compute_result.row_count > 0
```

---

## Anti-Principle Mapping

| Principle | Anti-Pattern | Reference |
|-----------|-------------|-----------|
| Registry-Driven | Branching Factories | ANTI_PATTERNS.md #2 |
| Fail Fast | Silent Failures | ANTI_PATTERNS.md #4 |
| Observable | Global Anomaly Filtering | ANTI_PATTERNS.md #5 |
| Separation of Concerns | Standalone CLI Commands | ANTI_PATTERNS.md #1 |
| Idempotency | MAX(version) Queries | ANTI_PATTERNS.md #3 |

See [ANTI_PATTERNS.md](../ANTI_PATTERNS.md) for detailed examples of what NOT to do.

---

## Decision Framework

When facing a design decision, ask:

1. **Can I add new implementations without modifying existing code?**
   - No → Use Protocol + Registry
   
2. **Is this mutable?**
   - No good reason → Make it frozen

3. **Where does this logic belong?**
   - Business calculation → Domain
   - Generic capability → Framework
   - Primitive/contract → Core
   - User input/output → App

4. **How will I know if this breaks?**
   - Write the test first

5. **Can this run at the simplest tier?**
   - Yes → Default implementation
   - No → Progressive enhancement

6. **What happens when this fails?**
   - Define the error type
   - Return as value, not exception
   - Record in anomaly table

---

## See Also

- [ANTI_PATTERNS.md](../ANTI_PATTERNS.md) - What NOT to do
- [CONTEXT.md](../CONTEXT.md) - Repository structure and layer boundaries
- [DEFINITION_OF_DONE.md](../DEFINITION_OF_DONE.md) - Completion checklist
- [CAPTURE_SEMANTICS.md](./CAPTURE_SEMANTICS.md) - Capture ID contract
- [QUALITY_GATES.md](./QUALITY_GATES.md) - Validation patterns
- [docs/platform-roadmap/](../../platform-roadmap/) - Implementation designs
