# Shared Command Architecture — Architecture Review

> **Review Focus**: Design a shared command architecture that supports CLI and API. Keep it minimal for Basic tier, but extensible for async, auth, and remote execution later. Call out unnecessary abstractions.

---

## SWOT Validation

### Strengths — Confirmed ✅

1. **Commands are well-defined semantically** — The CLI already expresses clear user intents: list pipelines, run pipeline, query weeks, query symbols, verify table, check health. These map 1:1 to command objects.

2. **Natural HTTP verb mapping exists**:
   | CLI | HTTP | Command |
   |-----|------|---------|
   | `spine pipelines list` | `GET /v1/pipelines` | `ListPipelinesCommand` |
   | `spine run run` | `POST /v1/executions` | `RunPipelineCommand` |
   | `spine query weeks` | `GET /v1/query/weeks` | `QueryWeeksCommand` |

3. **Phase-based execution maps to async** — The `Dispatcher` already tracks `Execution` objects with status. This is the hook for async polling later.

### Strengths — Challenged 🔶

**"Commands already well-defined"** — Semantically yes, but not as code artifacts. The current CLI has *functions*, not *command objects*. The mapping exists in our heads, not in the codebase.

---

### Weaknesses — Confirmed ✅

1. **Command logic scattered** — Each CLI command file (`run.py`, `list_.py`, `query.py`) contains orchestration mixed with Typer decorators and Rich rendering.

2. **No command objects yet** — There's no `ListPipelinesCommand` class. There's just a `list_pipelines_cmd` function.

3. **Hard to test independently** — To test list logic, you'd have to mock `typer.Context`, capture Rich output, or invoke via CLI runner. Unit tests should call a simple class method.

### Weaknesses — Additional ⚠️

4. **No structured output** — Commands print to console. There's no return value to capture. API would have nothing to serialize.

5. **Error handling via exceptions** — `BadParamsError` is raised and caught in the same function. Commands should return error results, not throw.

---

### Opportunities — Validated ✅

1. **Command DTOs** — Yes, introduce request/response dataclasses. These become the API contract.

2. **API versioning** — Yes, but versioning is in the route layer (`/v1/...`), not the command layer. Commands are version-agnostic.

3. **Background execution readiness** — Yes. If commands return results (not void), the Intermediate tier can wrap them in async tasks.

### Opportunities — Refined

**"Enable background execution with no refactor"** — Partially true. The command interface (`execute(request) -> result`) works for both sync and async. But the *caller* (API route) will need to change from direct call to task submission. The command itself stays the same.

---

### Threats — Confirmed ✅

1. **Over-engineering for Basic** — Real risk. A 6-layer architecture with base classes, factories, and middleware is overkill.

2. **Unnecessary abstraction layers** — Each layer must justify its existence. If a layer just forwards calls, delete it.

3. **Losing clarity** — "What runs what?" should remain obvious. A developer should trace from `spine run foo` to execution in <3 hops.

### Threats — Identified

4. **Generic command pattern** — The proposal shows:
   ```python
   class Command(ABC, Generic[TInput, TOutput]):
       @abstractmethod
       def execute(self, request: TInput) -> TOutput: ...
   ```
   
   This is unnecessary for Basic tier. Start with concrete classes:
   ```python
   class ListPipelinesCommand:
       def execute(self, request: ListPipelinesRequest) -> ListPipelinesResult: ...
   ```
   
   Add the ABC only if you need to treat commands polymorphically (which Basic doesn't).

---

## Existing Architecture Document Critique

The existing `SHARED_COMMAND_ARCHITECTURE.md` is **directionally correct** but has issues:

### Over-Engineered Elements

1. **Generic `Command[TInput, TOutput]` base class**
   
   ```python
   class Command(ABC, Generic[TInput, TOutput]):
       @abstractmethod
       def execute(self, request: TInput) -> TOutput: ...
   ```
   
   **Problem**: This adds no value in Basic. You never write code like:
   ```python
   def process(cmd: Command[Any, Any]):
       cmd.execute(...)
   ```
   
   **Fix**: Skip the ABC. Define concrete classes directly.

2. **Service injection in constructor**
   
   ```python
   class RunPipelineCommand:
       def __init__(
           self,
           tier_normalizer: TierNormalizer | None = None,
           param_resolver: ParameterResolver | None = None,
           ingest_resolver: IngestResolver | None = None,
       ):
   ```
   
   **Problem**: This looks like DI but isn't. It's just optional args with defaults. If you're not using a DI container, this is ceremony.
   
   **Fix for Basic**: Use module-level singletons or just instantiate services inside methods.

### Missing Elements

1. **Error handling pattern**
   
   The doc mentions "returns typed output" but doesn't show how errors work. Commands should return success *or* failure in the result type:
   
   ```python
   @dataclass
   class RunPipelineResult:
       success: bool
       execution_id: str | None = None
       error: PipelineError | None = None
   ```
   
   Or use a union:
   ```python
   RunPipelineResult = Success[ExecutionData] | Failure[PipelineError]
   ```

2. **Logging/observability**
   
   Commands should log structured events. The doc doesn't address this.

3. **Idempotency**
   
   If a command is called twice with the same inputs, what happens? For `RunPipelineCommand`, probably two executions. But this should be documented.

---

## Revised Minimal Architecture

### Principle: Start Concrete, Abstract Later

```
Week 1: Concrete classes, no base classes
Week 4: If patterns emerge, consider ABC
Week 8: If polymorphism needed, add generics
```

### Command Structure (Basic Tier)

```
market_spine/app/
├── __init__.py
├── commands/
│   ├── __init__.py
│   ├── pipelines.py      # ListPipelines, DescribePipeline
│   ├── executions.py     # RunPipeline, GetExecution
│   ├── queries.py        # QueryWeeks, QuerySymbols
│   ├── verify.py         # VerifyTable, VerifyData
│   └── health.py         # HealthCheck
├── services/
│   ├── __init__.py
│   ├── tier.py           # TierNormalizer
│   ├── params.py         # ParameterResolver
│   └── ingest.py         # IngestResolver
└── models.py             # Shared dataclasses (errors, etc.)
```

### Minimal Command Implementation

```python
# market_spine/app/commands/pipelines.py

from dataclasses import dataclass
from spine.framework.registry import list_pipelines, get_pipeline


@dataclass
class ListPipelinesRequest:
    prefix: str | None = None


@dataclass
class PipelineSummary:
    name: str
    description: str


@dataclass
class ListPipelinesResult:
    pipelines: list[PipelineSummary]


class ListPipelinesCommand:
    """List available pipelines."""
    
    def execute(self, request: ListPipelinesRequest) -> ListPipelinesResult:
        names = list_pipelines()
        
        if request.prefix:
            names = [n for n in names if n.startswith(request.prefix)]
        
        pipelines = []
        for name in names:
            cls = get_pipeline(name)
            pipelines.append(PipelineSummary(
                name=name,
                description=getattr(cls, 'description', '') or '',
            ))
        
        return ListPipelinesResult(pipelines=pipelines)
```

**Note**: No ABC, no generics, no DI. Just a class with a method.

### Error Handling Pattern

```python
# market_spine/app/models.py

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandError:
    """Structured error from a command."""
    code: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class Result:
    """Base result with optional error."""
    success: bool = True
    error: CommandError | None = None
```

```python
# market_spine/app/commands/executions.py

@dataclass
class RunPipelineResult(Result):
    execution_id: str | None = None
    status: str | None = None
    duration_seconds: float | None = None
    metrics: dict[str, Any] | None = None
    ingest_resolution: IngestResolution | None = None


class RunPipelineCommand:
    def execute(self, request: RunPipelineRequest) -> RunPipelineResult:
        # Validation
        try:
            pipeline_cls = get_pipeline(request.pipeline)
        except KeyError:
            return RunPipelineResult(
                success=False,
                error=CommandError(
                    code="PIPELINE_NOT_FOUND",
                    message=f"Pipeline '{request.pipeline}' not found.",
                ),
            )
        
        # ... execution logic ...
        
        return RunPipelineResult(
            success=True,
            execution_id=execution.id,
            status=execution.status.value,
            duration_seconds=duration,
            metrics=result.metrics,
        )
```

### CLI Adapter Pattern

```python
# market_spine/cli/commands/list_.py

@app.command("list")
def list_pipelines_cmd(
    prefix: Annotated[Optional[str], typer.Option("--prefix")] = None,
) -> None:
    """List available pipelines."""
    
    # Call command
    result = ListPipelinesCommand().execute(
        ListPipelinesRequest(prefix=prefix)
    )
    
    # Render
    if not result.pipelines:
        console.print("[yellow]No pipelines found[/yellow]")
        return
    
    table = create_pipeline_table(result.pipelines)
    console.print(table)
```

### API Adapter Pattern

```python
# market_spine/api/routes/pipelines.py

@router.get("/v1/pipelines")
def list_pipelines(prefix: str | None = None) -> dict:
    result = ListPipelinesCommand().execute(
        ListPipelinesRequest(prefix=prefix)
    )
    
    return {
        "pipelines": [
            {"name": p.name, "description": p.description}
            for p in result.pipelines
        ],
        "count": len(result.pipelines),
    }
```

---

## Command Catalog (Basic Tier)

### Required Commands

| Command | CLI Equivalent | API Endpoint | Priority |
|---------|----------------|--------------|----------|
| `ListPipelinesCommand` | `spine pipelines list` | `GET /v1/pipelines` | High |
| `DescribePipelineCommand` | `spine pipelines describe` | `GET /v1/pipelines/{name}` | High |
| `RunPipelineCommand` | `spine run run` | `POST /v1/executions` | High |
| `QueryWeeksCommand` | `spine query weeks` | `GET /v1/query/weeks` | Medium |
| `QuerySymbolsCommand` | `spine query symbols` | `GET /v1/query/symbols` | Medium |
| `HealthCheckCommand` | `spine doctor doctor` | `GET /v1/health` | Low |

### Optional Commands (Defer)

| Command | Notes |
|---------|-------|
| `VerifyTableCommand` | Lower priority; CLI-heavy use case |
| `GetExecutionCommand` | Useful but Basic has no persistence |
| `ResolveIngestCommand` | Could be part of `RunPipelineCommand` |

---

## Unnecessary Abstractions (Avoid)

### 1. Command Registry

**Proposal** (from elsewhere):
```python
class CommandRegistry:
    _commands: dict[str, type[Command]] = {}
    
    @classmethod
    def register(cls, name: str, command: type[Command]):
        cls._commands[name] = command
```

**Verdict**: NEVER DO. We already have a pipeline registry. Adding a command registry for 6 commands is pure ceremony. Just import the classes.

### 2. Middleware Chain

**Proposal**:
```python
class LoggingMiddleware:
    def wrap(self, command: Command) -> Command: ...

class ValidationMiddleware:
    def wrap(self, command: Command) -> Command: ...
```

**Verdict**: DEFER UNTIL ADVANCED. Middleware is useful for auth, rate limiting, and audit logging—none of which exist in Basic.

### 3. Command Bus

**Proposal**:
```python
class CommandBus:
    def dispatch(self, command: Command) -> Any:
        handler = self._handlers[type(command)]
        return handler.handle(command)
```

**Verdict**: NEVER DO. This adds indirection without value. Just call `command.execute()` directly.

### 4. Unit of Work Pattern

**Proposal**:
```python
class UnitOfWork:
    def __enter__(self):
        self.connection = get_connection()
        self.connection.execute("BEGIN")
    
    def __exit__(self, ...):
        self.connection.execute("COMMIT")
```

**Verdict**: DEFER. `market_spine.db.transaction()` already exists as a context manager. Don't add another abstraction layer.

---

## Extensibility Hooks (Future-Proof)

### For Intermediate Tier (Async)

```python
# Future: RunPipelineCommand could become async-aware
class RunPipelineCommand:
    def execute(self, request: RunPipelineRequest) -> RunPipelineResult:
        # Basic: synchronous
        return self._execute_sync(request)
    
    async def execute_async(self, request: RunPipelineRequest) -> RunPipelineResult:
        # Intermediate: async
        return await self._execute_async(request)
```

The command interface doesn't change; we add a new method.

### For Advanced Tier (Auth)

```python
# Future: Commands could accept a context
@dataclass
class ExecutionContext:
    user_id: str | None = None
    tenant_id: str | None = None
    request_id: str | None = None

class RunPipelineCommand:
    def execute(
        self,
        request: RunPipelineRequest,
        context: ExecutionContext | None = None,  # Optional for Basic
    ) -> RunPipelineResult:
        ...
```

This is backward-compatible. Basic tier passes `None`; Advanced tier passes auth context.

---

## Recommendations

### Do Now ✅

1. **Create `market_spine/app/commands/pipelines.py`** with `ListPipelinesCommand` and `DescribePipelineCommand`. No ABC, no generics.

2. **Create `market_spine/app/models.py`** with `CommandError` and `Result` base class.

3. **Create `market_spine/app/services/tier.py`** with `TierNormalizer`.

4. **Write unit tests** for commands and services. These become the behavioral contract.

### Defer ⏸️

5. **Generic `Command[I, O]` base class** — Add only if polymorphism is needed.

6. **Dependency injection** — Use manual instantiation for now.

7. **`RunPipelineCommand`** — This is the most complex. Extract services first, then tackle this when building API.

8. **Middleware/interceptors** — Wait for auth and rate limiting requirements.

### Never Do ❌

9. **Command registry** — Just import classes directly.

10. **Command bus pattern** — Adds indirection without value.

11. **Abstract factory for commands** — We don't have command families.

12. **Event sourcing** — Way beyond Basic tier scope.

---

## Testing Strategy

### Command Unit Tests

```python
# tests/unit/app/commands/test_pipelines.py

def test_list_pipelines_returns_all():
    result = ListPipelinesCommand().execute(ListPipelinesRequest())
    assert len(result.pipelines) > 0

def test_list_pipelines_filters_by_prefix():
    result = ListPipelinesCommand().execute(
        ListPipelinesRequest(prefix="finra.otc")
    )
    assert all(p.name.startswith("finra.otc") for p in result.pipelines)

def test_list_pipelines_empty_prefix_returns_empty():
    result = ListPipelinesCommand().execute(
        ListPipelinesRequest(prefix="nonexistent.prefix")
    )
    assert result.pipelines == []
```

### Service Unit Tests

```python
# tests/unit/app/services/test_tier.py

def test_normalize_tier_aliases():
    normalizer = TierNormalizer()
    assert normalizer.normalize("tier1") == "NMS_TIER_1"
    assert normalizer.normalize("OTC") == "OTC"
    assert normalizer.normalize("Tier2") == "NMS_TIER_2"

def test_normalize_tier_invalid_raises():
    normalizer = TierNormalizer()
    with pytest.raises(ValueError):
        normalizer.normalize("INVALID")
```

---

## Summary

The shared command architecture should be **minimal and concrete** for Basic tier:

| Element | Include | Reason |
|---------|---------|--------|
| Concrete command classes | ✅ | Required for reuse |
| Request/Result dataclasses | ✅ | Required for type safety |
| Shared services | ✅ | Required for logic reuse |
| ABC base class | ❌ | No polymorphism needed |
| Command registry | ❌ | Just import directly |
| Middleware chain | ❌ | No auth in Basic |
| DI container | ❌ | Manual instantiation is fine |

Start simple. Add abstraction only when patterns repeat or requirements demand it.
