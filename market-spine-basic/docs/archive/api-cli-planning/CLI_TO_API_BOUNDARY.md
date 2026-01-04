# CLI to API Boundary

> **Purpose**: Define what logic stays in the CLI, what should be extracted to a shared layer, and what should never be shared.

---

## Current State Analysis

The CLI currently contains a mix of concerns:

```
market_spine/cli/
├── __init__.py          # App wiring, logging config
├── console.py           # Rich console, tier normalization
├── params.py            # Parameter parsing/merging
├── ui.py                # Rich panels, tables, formatting
├── logging_config.py    # Log format configuration
├── commands/
│   ├── run.py           # Pipeline execution + ingest resolution display
│   ├── list_.py         # Pipeline discovery + describe
│   ├── query.py         # Data queries (weeks, symbols)
│   ├── verify.py        # Table/data verification
│   ├── db.py            # Database init/reset
│   └── doctor.py        # Health checks
└── interactive/
    ├── menu.py          # Questionary interactive mode
    └── prompts.py       # Parameter prompts
```

### Classification of Current CLI Code

| File/Module | Type | Shareable? |
|-------------|------|------------|
| `console.py` (tier normalization) | **Business Logic** | ✅ Yes — extract |
| `console.py` (Rich console) | Presentation | ❌ CLI-only |
| `params.py` (merge logic) | **Business Logic** | ✅ Yes — extract |
| `ui.py` | Presentation | ❌ CLI-only |
| `commands/run.py` (dispatch call) | **Orchestration** | ✅ Yes — extract |
| `commands/run.py` (ingest resolution display) | Mixed | 🔶 Partial — split |
| `commands/list_.py` (list/describe) | **Orchestration** | ✅ Yes — extract |
| `commands/query.py` (SQL queries) | **Business Logic** | ✅ Yes — extract |
| `commands/verify.py` | **Business Logic** | ✅ Yes — extract |
| `commands/db.py` | **Infrastructure** | ⚠️ Maybe — review |
| `commands/doctor.py` | **Diagnostics** | ✅ Yes — extract |
| `interactive/` | Presentation | ❌ CLI-only |
| `logging_config.py` | CLI Config | ❌ CLI-only |

---

## What Logic Stays in CLI

These are **presentation concerns** that belong exclusively in the CLI:

### 1. Rich Console Formatting
```python
# CLI-only: Rich panels, tables, colors
console.print(Panel("Database Initialized", border_style="cyan"))
render_summary_panel(status="completed", duration=1.5)
```

**Why CLI-only**: The API returns structured data; clients format it themselves.

### 2. Interactive Prompts
```python
# CLI-only: Questionary-based prompts
selected = questionary.select("Choose a pipeline:", choices=pipelines).ask()
```

**Why CLI-only**: The API is non-interactive by definition.

### 3. Progress Indicators
```python
# CLI-only: Rich progress bars
with Progress() as progress:
    task = progress.add_task("Processing...", total=100)
```

**Why CLI-only**: The API uses polling or callbacks, not terminal animations.

### 4. Argument Parsing Mechanics
```python
# CLI-only: Typer decorators and options
@app.command()
def run_pipeline(
    pipeline: Annotated[str, typer.Argument(...)],
    param: Annotated[Optional[list[str]], typer.Option("-p", ...)],
):
```

**Why CLI-only**: API uses JSON/query params, not shell arguments.

### 5. Log Configuration for Terminal
```python
# CLI-only: Log format preferences for humans
configure_cli_logging(log_format=LogFormat.PRETTY)
```

**Why CLI-only**: API has its own logging strategy (structured JSON, trace IDs).

---

## What Logic Should Be Extracted

These concerns should move to a **shared command layer** that both CLI and API call:

### 1. Tier Normalization

**Current (CLI):**
```python
# market_spine/cli/console.py
def normalize_tier(tier: str) -> str:
    TIER_ALIASES = {
        "tier1": "NMS_TIER_1", "t1": "NMS_TIER_1", ...
    }
    return TIER_ALIASES.get(tier.lower(), tier.upper())
```

**Extracted (Shared):**
```python
# market_spine/app/services/tier.py
class TierNormalizer:
    ALIASES = {...}
    
    @classmethod
    def normalize(cls, tier: str) -> str:
        """Normalize tier to canonical form. Raises ValueError if invalid."""
        
    @classmethod
    def is_valid(cls, tier: str) -> bool:
        """Check if tier is valid (after normalization)."""
```

**Why extract**: Both CLI and API need identical normalization.

### 2. Parameter Merging

**Current (CLI):**
```python
# market_spine/cli/params.py
class ParamParser:
    @staticmethod
    def merge_params(param_flags, extra_args, week_ending, tier, file_path):
        ...
```

**Extracted (Shared):**
```python
# market_spine/app/services/params.py
class ParameterResolver:
    def resolve(
        self,
        pipeline_name: str,
        raw_params: dict[str, Any],
    ) -> ResolvedParams:
        """
        Normalize, validate, and resolve parameters.
        Returns typed result with validation status.
        """
```

**Why extract**: Validation and normalization must be consistent.

### 3. Pipeline Discovery

**Current (CLI):**
```python
# market_spine/cli/commands/list_.py
def list_pipelines_cmd(prefix: str | None):
    all_pipelines = list_pipelines()
    if prefix:
        pipelines = [p for p in all_pipelines if p.startswith(prefix)]
    ...
```

**Extracted (Shared):**
```python
# market_spine/app/commands/pipelines.py
class ListPipelinesCommand:
    def execute(self, prefix: str | None = None) -> ListPipelinesResult:
        """List pipelines with optional filtering."""
        
class DescribePipelineCommand:
    def execute(self, name: str) -> PipelineDescription:
        """Get full pipeline details including parameters."""
```

**Why extract**: Same filtering logic needed in API.

### 4. Pipeline Execution

**Current (CLI):**
```python
# market_spine/cli/commands/run.py
dispatcher = Dispatcher()
result = dispatcher.submit(pipeline=pipeline, params=params, ...)
```

**Extracted (Shared):**
```python
# market_spine/app/commands/executions.py
class RunPipelineCommand:
    def execute(
        self,
        pipeline: str,
        params: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Run pipeline and return structured result."""
```

**Why extract**: Execution semantics must be identical.

### 5. Ingest Resolution

**Current (CLI):**
```python
# market_spine/cli/commands/run.py
def show_ingest_resolution(pipeline: str, params: dict, is_ingest: bool):
    # Complex logic to explain how file_path is resolved
    ...
```

**Extracted (Shared):**
```python
# market_spine/app/commands/ingest.py
class IngestResolver:
    def resolve(
        self,
        pipeline: str,
        params: dict[str, Any],
    ) -> IngestResolution:
        """
        Returns:
            IngestResolution(
                mode="explicit" | "derived",
                file_path="...",
                derivation_logic="..." if derived,
            )
        """
```

**Why extract**: API needs to return this information; CLI displays it.

### 6. Data Queries

**Current (CLI):**
```python
# market_spine/cli/commands/query.py
def query_weeks(tier: str, limit: int):
    cursor.execute("""SELECT week_ending, COUNT(*) FROM ...""")
```

**Extracted (Shared):**
```python
# market_spine/app/commands/queries.py
class QueryWeeksCommand:
    def execute(self, tier: str, limit: int = 10) -> QueryWeeksResult:
        """Query available weeks. Returns structured data."""
        
class QuerySymbolsCommand:
    def execute(self, week: str, tier: str, top: int = 10) -> QuerySymbolsResult:
        """Query top symbols for a week."""
```

**Why extract**: Query logic is pure business logic.

### 7. Health Checks

**Current (CLI):**
```python
# market_spine/cli/commands/doctor.py
def check_health():
    # Check DB connection, tables exist, etc.
```

**Extracted (Shared):**
```python
# market_spine/app/commands/doctor.py
class HealthCheckCommand:
    def execute(self) -> HealthCheckResult:
        """
        Returns:
            HealthCheckResult(
                overall_status="healthy" | "degraded" | "unhealthy",
                checks=[
                    Check(name="database", status="ok"),
                    Check(name="table:raw", status="ok"),
                    ...
                ]
            )
        """
```

**Why extract**: API needs structured health responses.

---

## What Should Never Be Shared

These are fundamentally **CLI-specific** and should not pollute the shared layer:

### 1. Terminal Detection
```python
# Never share: Is the output a TTY?
if sys.stdout.isatty():
    use_colors = True
```

### 2. Exit Code Management
```python
# Never share: CLI exit codes
raise typer.Exit(1)
```

### 3. Keyboard Interrupt Handling
```python
# Never share: Ctrl+C handling
except KeyboardInterrupt:
    console.print("\n[yellow]Cancelled[/yellow]")
```

### 4. Shell Completion
```python
# Never share: Tab completion for shells
app.add_completion = True
```

### 5. Environment Variable Shortcuts
```python
# Never share: SPINE_LOG_LEVEL, etc.
# API uses its own configuration
```

---

## Extraction Strategy

### Phase 1: Create Command Layer (No Breaking Changes)

```
market_spine/
├── app/                    # NEW: Shared command layer
│   ├── __init__.py
│   ├── commands/
│   │   ├── pipelines.py    # List, Describe
│   │   ├── executions.py   # Run, DryRun, Status
│   │   ├── queries.py      # Weeks, Symbols
│   │   ├── verify.py       # Tables, Data
│   │   └── doctor.py       # Health checks
│   ├── services/
│   │   ├── tier.py         # Tier normalization
│   │   ├── params.py       # Parameter resolution
│   │   └── ingest.py       # Ingest resolution
│   └── models.py           # Pydantic response models
│
├── cli/                    # REFACTORED: Thin adapter
│   ├── commands/
│   │   ├── run.py          # Calls app.commands.executions
│   │   ├── list_.py        # Calls app.commands.pipelines
│   │   └── ...
│   └── ...
│
└── api/                    # FUTURE: Thin adapter
    └── ...
```

### Phase 2: Refactor CLI to Use Command Layer

Before:
```python
# cli/commands/query.py
def query_weeks(tier: str, limit: int):
    normalized_tier = normalize_tier(tier)
    conn = get_connection()
    cursor.execute(...)
    weeks = cursor.fetchall()
    table = Table(...)
    console.print(table)
```

After:
```python
# cli/commands/query.py
def query_weeks(tier: str, limit: int):
    from market_spine.app.commands.queries import QueryWeeksCommand
    
    result = QueryWeeksCommand().execute(tier=tier, limit=limit)
    
    if result.error:
        render_error_panel("Query Error", result.error)
        raise typer.Exit(1)
    
    table = create_weeks_table(result.weeks)  # CLI presentation
    console.print(table)
```

### Phase 3: Add API Adapter

```python
# api/routes/queries.py
@router.get("/v1/query/weeks")
def query_weeks(tier: str, limit: int = 10) -> QueryWeeksResponse:
    from market_spine.app.commands.queries import QueryWeeksCommand
    
    result = QueryWeeksCommand().execute(tier=tier, limit=limit)
    
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    
    return QueryWeeksResponse(weeks=result.weeks)  # API serialization
```

---

## Boundary Rules Summary

| Category | Location | Shared? |
|----------|----------|---------|
| Business Logic | `app/commands/`, `app/services/` | ✅ Yes |
| Data Models | `app/models.py` | ✅ Yes |
| Terminal Formatting | `cli/ui.py`, `cli/console.py` | ❌ No |
| Argument Parsing | `cli/commands/*.py` | ❌ No |
| HTTP Routing | `api/routes/*.py` | ❌ No |
| Interactive Prompts | `cli/interactive/` | ❌ No |

**Golden Rule**: If it deals with *what* happens, it's shared. If it deals with *how* it's presented or invoked, it's adapter-specific.
