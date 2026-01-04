# Shared Command Architecture

> **Purpose**: Define the shared command/use-case layer that both CLI and API call, with clear patterns and examples.

---

## Architectural Pattern: Command Layer

The command layer implements **application use cases** as discrete, reusable units. This is a pragmatic blend of:

- **Command Pattern** — Encapsulates a request as an object
- **Use Case / Application Service** — Business logic orchestration
- **Ports & Adapters** — Clean separation of I/O from logic

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ADAPTERS (I/O Layer)                                │
├───────────────────────────────┬───────────────────────────────┬─────────────────┤
│           CLI                 │            API                │    Future       │
│         (Typer)               │         (FastAPI)             │   (SDK/gRPC)    │
│                               │                               │                 │
│  • Parse shell args           │  • Parse JSON/query params    │  • Deserialize  │
│  • Call command               │  • Call command               │  • Call command │
│  • Render Rich output         │  • Return JSON response       │  • Serialize    │
│  • Handle Ctrl+C              │  • Handle HTTP errors         │                 │
└───────────────┬───────────────┴───────────────┬───────────────┴───────────────┬─┘
                │                               │                               │
                ▼                               ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           COMMAND LAYER (Use Cases)                              │
│                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ ListPipelines   │  │ RunPipeline     │  │ QueryWeeks      │                  │
│  │   Command       │  │   Command       │  │   Command       │                  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘                  │
│           │                    │                    │                           │
│           ▼                    ▼                    ▼                           │
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                      SERVICES (Shared Logic)                         │        │
│  │                                                                      │        │
│  │  TierNormalizer │ ParameterResolver │ IngestResolver │ ...          │        │
│  └─────────────────────────────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                │
                ┌───────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         FRAMEWORK / DOMAIN LAYER                                 │
│                                                                                  │
│  spine.framework          │  spine.domains            │  market_spine.db        │
│  ──────────────────────   │  ─────────────────────    │  ────────────────       │
│  • Dispatcher             │  • FINRA OTC pipelines    │  • SQLite connection    │
│  • Runner                 │  • Domain validation      │  • Table operations     │
│  • Registry               │  • Calculations           │                         │
│  • Pipeline base          │                           │                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Command Pattern Definition

Each command:
1. **Receives typed input** (dataclass or Pydantic model)
2. **Orchestrates services** (tier normalization, parameter resolution, etc.)
3. **Calls framework** (dispatcher, registry, database)
4. **Returns typed output** (never prints, never raises HTTP exceptions)

### Command Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class Command(ABC, Generic[TInput, TOutput]):
    """Base class for all commands."""
    
    @abstractmethod
    def execute(self, request: TInput) -> TOutput:
        """Execute the command and return a result."""
        ...
```

### Example: ListPipelinesCommand

```python
# market_spine/app/commands/pipelines.py

from dataclasses import dataclass
from spine.framework.registry import list_pipelines, get_pipeline


@dataclass
class ListPipelinesRequest:
    """Input for listing pipelines."""
    prefix: str | None = None


@dataclass
class PipelineSummary:
    """Summary of a single pipeline."""
    name: str
    description: str


@dataclass
class ListPipelinesResult:
    """Output from listing pipelines."""
    pipelines: list[PipelineSummary]
    total_count: int
    filtered: bool


class ListPipelinesCommand:
    """List available pipelines with optional filtering."""
    
    def execute(self, request: ListPipelinesRequest) -> ListPipelinesResult:
        all_names = list_pipelines()
        
        # Apply prefix filter
        if request.prefix:
            filtered_names = [n for n in all_names if n.startswith(request.prefix)]
            filtered = True
        else:
            filtered_names = all_names
            filtered = False
        
        # Build summaries
        pipelines = []
        for name in filtered_names:
            pipeline_cls = get_pipeline(name)
            pipelines.append(PipelineSummary(
                name=name,
                description=pipeline_cls.description or "",
            ))
        
        return ListPipelinesResult(
            pipelines=pipelines,
            total_count=len(all_names),
            filtered=filtered,
        )
```

---

## How CLI and API Call Commands

### CLI Adapter

```python
# market_spine/cli/commands/list_.py

import typer
from market_spine.app.commands.pipelines import (
    ListPipelinesCommand,
    ListPipelinesRequest,
)
from ..ui import create_pipeline_table
from ..console import console


@app.command("list")
def list_pipelines_cmd(
    prefix: Annotated[Optional[str], typer.Option("--prefix")] = None,
) -> None:
    """List all available pipelines."""
    
    # 1. Build request
    request = ListPipelinesRequest(prefix=prefix)
    
    # 2. Execute command
    result = ListPipelinesCommand().execute(request)
    
    # 3. Render output (CLI-specific)
    if not result.pipelines:
        console.print("[yellow]No pipelines found[/yellow]")
        return
    
    table = create_pipeline_table(result.pipelines)
    console.print(table)
    console.print(f"\n[dim]Found {len(result.pipelines)} pipeline(s)[/dim]")
```

### API Adapter

```python
# market_spine/api/routes/pipelines.py

from fastapi import APIRouter, Query
from market_spine.app.commands.pipelines import (
    ListPipelinesCommand,
    ListPipelinesRequest,
)
from market_spine.api.models import PipelineListResponse


router = APIRouter()


@router.get("/v1/pipelines")
def list_pipelines(
    prefix: str | None = Query(None, description="Filter by prefix"),
) -> PipelineListResponse:
    """List available pipelines."""
    
    # 1. Build request
    request = ListPipelinesRequest(prefix=prefix)
    
    # 2. Execute command
    result = ListPipelinesCommand().execute(request)
    
    # 3. Return response (API-specific)
    return PipelineListResponse(
        pipelines=[
            {"name": p.name, "description": p.description}
            for p in result.pipelines
        ],
        count=len(result.pipelines),
    )
```

---

## Complete Command Catalog

### Pipeline Commands

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PIPELINE COMMANDS                                 │
├─────────────────────┬───────────────────────────────────────────────────┤
│ ListPipelinesCommand│ List pipelines with optional prefix filter        │
│                     │                                                   │
│   Input:            │   prefix: str | None                              │
│   Output:           │   pipelines: list[PipelineSummary]                │
├─────────────────────┼───────────────────────────────────────────────────┤
│ DescribePipeline    │ Get full pipeline details including params        │
│   Command           │                                                   │
│                     │                                                   │
│   Input:            │   name: str                                       │
│   Output:           │   name, description, required_params,             │
│                     │   optional_params, examples, ingest_info          │
└─────────────────────┴───────────────────────────────────────────────────┘
```

### Execution Commands

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        EXECUTION COMMANDS                                │
├─────────────────────┬───────────────────────────────────────────────────┤
│ RunPipelineCommand  │ Execute a pipeline with parameters                │
│                     │                                                   │
│   Input:            │   pipeline: str                                   │
│                     │   params: dict[str, Any]                          │
│                     │   dry_run: bool = False                           │
│                     │   lane: str = "normal"                            │
│   Output:           │   execution_id, status, metrics, duration,        │
│                     │   error (if failed)                               │
├─────────────────────┼───────────────────────────────────────────────────┤
│ GetExecutionCommand │ Get status of a specific execution                │
│                     │                                                   │
│   Input:            │   execution_id: str                               │
│   Output:           │   execution details + result                      │
├─────────────────────┼───────────────────────────────────────────────────┤
│ ResolveIngestCommand│ Show how ingest source would be resolved          │
│                     │                                                   │
│   Input:            │   pipeline: str, params: dict                     │
│   Output:           │   mode (explicit/derived), file_path,             │
│                     │   derivation_logic                                │
└─────────────────────┴───────────────────────────────────────────────────┘
```

### Query Commands

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          QUERY COMMANDS                                  │
├─────────────────────┬───────────────────────────────────────────────────┤
│ QueryWeeksCommand   │ Get available weeks for a tier                    │
│                     │                                                   │
│   Input:            │   tier: str                                       │
│                     │   limit: int = 10                                 │
│   Output:           │   weeks: list[WeekSummary]                        │
│                     │   (week_ending, symbol_count)                     │
├─────────────────────┼───────────────────────────────────────────────────┤
│ QuerySymbolsCommand │ Get top symbols for a week                        │
│                     │                                                   │
│   Input:            │   week: str, tier: str, top: int = 10             │
│   Output:           │   symbols: list[SymbolSummary]                    │
│                     │   (symbol, total_shares, total_trades)            │
└─────────────────────┴───────────────────────────────────────────────────┘
```

### Verification Commands

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       VERIFICATION COMMANDS                              │
├─────────────────────┬───────────────────────────────────────────────────┤
│ VerifyTableCommand  │ Check table existence and row count               │
│                     │                                                   │
│   Input:            │   table_name: str                                 │
│   Output:           │   exists: bool, row_count: int                    │
├─────────────────────┼───────────────────────────────────────────────────┤
│ VerifyDataCommand   │ Run data integrity checks                         │
│                     │                                                   │
│   Input:            │   tier: str, week: str | None                     │
│   Output:           │   checks: list[CheckResult]                       │
├─────────────────────┼───────────────────────────────────────────────────┤
│ HealthCheckCommand  │ Full system health check                          │
│                     │                                                   │
│   Input:            │   (none)                                          │
│   Output:           │   overall_status, checks: list[Check]             │
└─────────────────────┴───────────────────────────────────────────────────┘
```

---

## Shared Services

Commands use shared services for cross-cutting concerns:

### TierNormalizer

```python
# market_spine/app/services/tier.py

class TierNormalizer:
    """Normalize tier values to canonical form."""
    
    CANONICAL_TIERS = {"NMS_TIER_1", "NMS_TIER_2", "OTC"}
    
    ALIASES = {
        "tier1": "NMS_TIER_1", "t1": "NMS_TIER_1", "nms1": "NMS_TIER_1",
        "tier2": "NMS_TIER_2", "t2": "NMS_TIER_2", "nms2": "NMS_TIER_2",
        "otc": "OTC", "tier3": "OTC", "t3": "OTC",
    }
    
    @classmethod
    def normalize(cls, tier: str) -> str:
        """Normalize tier to canonical form. Raises ValueError if invalid."""
        normalized = cls.ALIASES.get(tier.lower(), tier.upper())
        if normalized not in cls.CANONICAL_TIERS:
            raise ValueError(f"Invalid tier: {tier}")
        return normalized
    
    @classmethod
    def list_valid(cls) -> list[str]:
        """List all valid canonical tiers."""
        return sorted(cls.CANONICAL_TIERS)
```

### ParameterResolver

```python
# market_spine/app/services/params.py

@dataclass
class ResolvedParams:
    """Result of parameter resolution."""
    params: dict[str, Any]
    normalized_tier: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    
    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0


class ParameterResolver:
    """Resolve and validate pipeline parameters."""
    
    def __init__(self, tier_normalizer: TierNormalizer = None):
        self.tier_normalizer = tier_normalizer or TierNormalizer()
    
    def resolve(
        self,
        raw_params: dict[str, Any],
        pipeline_spec: PipelineSpec | None = None,
    ) -> ResolvedParams:
        """
        Resolve parameters:
        1. Normalize tier if present
        2. Validate against spec if provided
        3. Return structured result
        """
        params = dict(raw_params)
        errors = []
        normalized_tier = None
        
        # Normalize tier
        if "tier" in params:
            try:
                normalized_tier = self.tier_normalizer.normalize(params["tier"])
                params["tier"] = normalized_tier
            except ValueError as e:
                errors.append(str(e))
        
        # Validate against spec
        if pipeline_spec:
            validation = pipeline_spec.validate(params)
            if not validation.valid:
                errors.extend([validation.get_error_message()])
        
        return ResolvedParams(
            params=params,
            normalized_tier=normalized_tier,
            validation_errors=errors,
        )
```

### IngestResolver

```python
# market_spine/app/services/ingest.py

@dataclass
class IngestResolution:
    """Result of ingest source resolution."""
    mode: Literal["explicit", "derived"]
    file_path: str | None
    derivation_pattern: str | None = None
    derivation_params: dict[str, str] | None = None
    error: str | None = None


class IngestResolver:
    """Resolve ingest source for ingest pipelines."""
    
    FILE_PATTERN = "data/finra/finra_otc_weekly_{tier}_{date}.csv"
    
    def resolve(
        self,
        params: dict[str, Any],
    ) -> IngestResolution:
        """
        Resolve ingest source:
        - If file_path provided: explicit mode
        - Otherwise: derive from tier + week_ending
        """
        if "file_path" in params and params["file_path"]:
            return IngestResolution(
                mode="explicit",
                file_path=params["file_path"],
            )
        
        tier = params.get("tier")
        week_ending = params.get("week_ending")
        
        if not tier or not week_ending:
            return IngestResolution(
                mode="derived",
                file_path=None,
                derivation_pattern=self.FILE_PATTERN,
                error="Cannot derive path: missing tier or week_ending",
            )
        
        file_path = self.FILE_PATTERN.format(
            tier=tier.lower(),
            date=week_ending,
        )
        
        return IngestResolution(
            mode="derived",
            file_path=file_path,
            derivation_pattern=self.FILE_PATTERN,
            derivation_params={"tier": tier, "date": week_ending},
        )
```

---

## Error Handling Pattern

Commands return **result objects**, not exceptions:

```python
@dataclass
class CommandResult:
    """Base result with optional error."""
    success: bool
    error: str | None = None
    error_code: str | None = None  # e.g., "PIPELINE_NOT_FOUND"


@dataclass
class RunPipelineResult(CommandResult):
    """Result of running a pipeline."""
    execution_id: str | None = None
    status: str | None = None
    metrics: dict[str, Any] | None = None
    duration_seconds: float | None = None
```

### Why Results Instead of Exceptions?

1. **Adapters decide presentation** — CLI can show Rich error panel; API returns 400 JSON
2. **Testability** — Assert on result fields, not try/except
3. **Composability** — Chain commands without nested try blocks
4. **Type safety** — Result shapes are explicit

### Adapter Error Handling

**CLI:**
```python
result = RunPipelineCommand().execute(request)
if not result.success:
    render_error_panel(result.error_code, result.error)
    raise typer.Exit(1)
```

**API:**
```python
result = RunPipelineCommand().execute(request)
if not result.success:
    raise HTTPException(
        status_code=400,
        detail={"code": result.error_code, "message": result.error}
    )
```

---

## Folder Structure

```
market_spine/
├── app/                           # Command layer (shared)
│   ├── __init__.py
│   │
│   ├── commands/                  # Use case implementations
│   │   ├── __init__.py
│   │   ├── pipelines.py           # ListPipelines, DescribePipeline
│   │   ├── executions.py          # RunPipeline, GetExecution
│   │   ├── queries.py             # QueryWeeks, QuerySymbols
│   │   ├── verify.py              # VerifyTable, VerifyData
│   │   └── doctor.py              # HealthCheck
│   │
│   ├── services/                  # Shared business logic
│   │   ├── __init__.py
│   │   ├── tier.py                # TierNormalizer
│   │   ├── params.py              # ParameterResolver
│   │   └── ingest.py              # IngestResolver
│   │
│   └── models.py                  # Shared data structures
│
├── cli/                           # CLI adapter (Typer)
│   └── ...
│
└── api/                           # API adapter (FastAPI) - Future
    └── ...
```

---

## Testing Strategy

### Test the Command Layer Directly

```python
# tests/app/test_commands_pipelines.py

def test_list_pipelines_no_filter():
    result = ListPipelinesCommand().execute(ListPipelinesRequest())
    
    assert len(result.pipelines) > 0
    assert not result.filtered
    assert "finra.otc_transparency.ingest_week" in [p.name for p in result.pipelines]


def test_list_pipelines_with_prefix():
    result = ListPipelinesCommand().execute(
        ListPipelinesRequest(prefix="finra.otc")
    )
    
    assert result.filtered
    assert all(p.name.startswith("finra.otc") for p in result.pipelines)
```

### Adapters Only Need Thin Tests

```python
# tests/cli/test_list_command.py

def test_list_command_outputs_table(cli_runner):
    result = cli_runner.invoke(app, ["pipelines", "list"])
    
    assert result.exit_code == 0
    assert "finra.otc_transparency" in result.output
```

```python
# tests/api/test_pipelines_route.py

def test_list_pipelines_endpoint(client):
    response = client.get("/v1/pipelines")
    
    assert response.status_code == 200
    assert "pipelines" in response.json()
```

---

## Summary

| Concept | Location | Responsibility |
|---------|----------|----------------|
| **Commands** | `app/commands/` | Orchestrate use cases, return results |
| **Services** | `app/services/` | Shared business logic (normalization, resolution) |
| **Models** | `app/models.py` | Request/result data structures |
| **CLI Adapter** | `cli/` | Parse args → call command → render Rich |
| **API Adapter** | `api/` | Parse JSON → call command → return JSON |
| **Framework** | `spine.framework` | Pipeline execution, registry, dispatcher |
| **Domains** | `spine.domains` | Pipeline implementations, business rules |
