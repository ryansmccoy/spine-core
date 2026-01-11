# CLI → API Boundary — Architecture Review

> **Review Focus**: Identify the clean boundary where an API layer could live. Propose a command/service architecture that allows CLI and API to share behavior without sharing presentation.

---

## SWOT Validation

### Strengths — Confirmed ✅

1. **CLI commands model real user intent** — Reading `run.py`, `query.py`, and `list_.py` confirms this. Each command represents a clear use case: run a pipeline, query data, list pipelines. These map directly to API operations.

2. **Parameter resolution is explicit** — The `ParamParser` class in `params.py` is well-documented and handles precedence clearly (friendly options > positional args > -p flags). This is extractable.

3. **Rich UX layer is cleanly separated** — `ui.py` and `console.py` handle all presentation. Commands call `render_*_panel()` functions that produce Rich output. This is already separated.

### Strengths — Challenged 🔶

**"CLI parameter resolution is explicit and well-documented"** — True, but it's not *complete*. The `ParamParser` handles merging, but tier normalization happens via a separate call to `normalize_tier()`. These should be unified in the extracted service.

---

### Weaknesses — Confirmed ✅

1. **CLI currently performs orchestration decisions** — In `run.py`, the CLI:
   - Parses parameters (application logic)
   - Resolves ingest source (business logic)
   - Creates and calls `Dispatcher` (framework integration)
   - Handles exceptions and renders output (presentation)
   
   This is too much responsibility. Lines 1-170 of `run.py` are a single function doing four jobs.

2. **Hard to reuse without importing CLI modules** — Anyone wanting programmatic access today would need to:
   ```python
   from market_spine.cli.params import ParamParser
   from market_spine.cli.console import normalize_tier
   ```
   This couples consumers to CLI internals.

3. **No explicit "API contract"** — The inputs and outputs are scattered across Typer annotations and Rich rendering. There's no `RunPipelineRequest` or `RunPipelineResult` that defines what the operation accepts and returns.

### Weaknesses — Additional ⚠️

4. **Exception handling is presentation-heavy** — In `run.py`, `BadParamsError` is caught and immediately rendered with Rich. The error details (missing params, invalid params) are formatted into strings. An API would need the raw data.

5. **Side effects in validation** — `ParamParser.merge_params` both merges *and* normalizes tier. This makes testing harder and prevents API from getting raw + normalized values.

---

### Opportunities — Validated ✅

1. **Treat CLI as thin adapter** — Yes. The target state is:
   ```
   CLI Command → Command Layer → Framework/Domain
   API Route   → Command Layer → Framework/Domain
   ```

2. **Command objects beneath CLI** — Yes. Each CLI command should call a corresponding command class.

3. **Shared semantics, not shared UX** — Yes. Both CLI and API should use the same `RunPipelineCommand`, but CLI renders Rich panels while API returns JSON.

### Opportunities — Expanded

4. **Testability** — Extracted commands can be unit tested without Typer or Rich. Currently, testing the run logic requires invoking the CLI.

5. **Error introspection** — Commands should return structured errors (not exceptions), allowing adapters to choose how to present them.

---

### Threats — Confirmed ✅

1. **Designing API to mimic CLI flags** — Risk confirmed. The CLI has `--explain-source` and `--help-params` which are CLI-specific affordances. API shouldn't have `/run?help_params=true`.

2. **Tight coupling to Typer/Rich** — The current `run.py` is 277 lines, deeply intertwined with Typer's `Context`, `typer.Exit()`, and Rich panels. Extraction requires careful untangling.

3. **API harder to version than CLI** — Once API is public, changes are breaking. CLI can evolve more freely (deprecated flags, changed output).

### Threats — Additional

4. **Over-extraction risk** — Moving *everything* to commands could produce 15 files where 5 would suffice. Start with high-value extractions (run, list, query).

---

## Current CLI Implementation Analysis

### Anatomy of `run.py`

```python
# Lines 26-70: Typer command definition with 13 options
@app.command("run", context_settings={...})
def run_pipeline(
    ctx: typer.Context,
    pipeline: str,
    param: Optional[list[str]],  # -p flags
    week_ending: Optional[str],  # --week-ending
    tier: Optional[str],         # --tier
    file_path: Optional[str],    # --file
    lane: Lane,                  # --lane
    dry_run: bool,               # --dry-run
    help_params: bool,           # --help-params (CLI-only)
    explain_source: bool,        # --explain-source (CLI-only)
    quiet: bool,                 # --quiet (CLI-only)
) -> None:
```

**Observations:**
- `help_params`, `explain_source`, `quiet` are pure UX—should stay CLI-only
- `lane` is passed to Dispatcher but has no effect in Basic tier (informational only)
- `dry_run` could be API-relevant (preview execution)

### Responsibility Breakdown

| Lines | Responsibility | Should Be |
|-------|----------------|-----------|
| 71-77 | Show help if `--help-params` | CLI-only |
| 79-100 | Parse and merge parameters | **Command layer** |
| 102-106 | Show ingest resolution | CLI-only (but resolution logic is shared) |
| 108-112 | Dry run rendering | CLI-only (but dry run data is shared) |
| 114-140 | Execute pipeline via Dispatcher | **Command layer** |
| 141-165 | Render success/failure panels | CLI-only |

### Extraction Candidates

1. **`merge_and_validate_params()`** — Move to `ParameterResolver` service
2. **`resolve_ingest_source()`** — Move to `IngestResolver` service
3. **`run_pipeline_sync()`** — Move to `RunPipelineCommand`

---

## Proposed Boundary: Command Layer

### What CLI Keeps

```python
# market_spine/cli/commands/run.py — AFTER extraction

@app.command("run")
def run_pipeline_cmd(
    ctx: typer.Context,
    pipeline: str,
    param: Optional[list[str]],
    # ... other options
    help_params: bool,      # CLI-only
    explain_source: bool,   # CLI-only
    quiet: bool,            # CLI-only
) -> None:
    """Run a pipeline with parameters."""
    
    # CLI-only: Show parameter help
    if help_params:
        show_pipeline_params(pipeline)  # CLI-only function
        return
    
    # Build request (translate CLI args to command input)
    request = RunPipelineRequest(
        pipeline=pipeline,
        params=collect_params(param, ctx.args, week_ending, tier, file_path),
        lane=lane,
        dry_run=dry_run,
    )
    
    # Execute command
    result = RunPipelineCommand().execute(request)
    
    # CLI-only: Show ingest resolution if requested
    if explain_source and result.ingest_resolution:
        render_ingest_resolution(result.ingest_resolution)
    
    # CLI-only: Handle result presentation
    if result.dry_run:
        render_dry_run_panel(result)
    elif result.success:
        render_summary_panel(result)
    else:
        render_error_panel(result.error)
        raise typer.Exit(1)
```

### What Command Layer Owns

```python
# market_spine/app/commands/executions.py

@dataclass
class RunPipelineRequest:
    pipeline: str
    params: dict[str, Any]
    lane: str = "normal"
    dry_run: bool = False

@dataclass
class IngestResolution:
    source_type: str  # "explicit" | "derived"
    file_path: str
    derivation_logic: str | None  # explanation if derived

@dataclass
class RunPipelineResult:
    success: bool
    execution_id: str | None
    status: str  # "completed" | "failed" | "dry_run"
    duration_seconds: float | None
    metrics: dict[str, Any] | None
    error: PipelineError | None
    ingest_resolution: IngestResolution | None
    dry_run: bool

@dataclass
class PipelineError:
    code: str  # "PIPELINE_NOT_FOUND" | "INVALID_PARAMS" | "EXECUTION_FAILED"
    message: str
    details: dict[str, Any]  # e.g., {"missing_params": ["tier"]}


class RunPipelineCommand:
    def __init__(
        self,
        tier_normalizer: TierNormalizer | None = None,
        param_resolver: ParameterResolver | None = None,
        ingest_resolver: IngestResolver | None = None,
    ):
        self.tier_normalizer = tier_normalizer or TierNormalizer()
        self.param_resolver = param_resolver or ParameterResolver()
        self.ingest_resolver = ingest_resolver or IngestResolver()
    
    def execute(self, request: RunPipelineRequest) -> RunPipelineResult:
        # 1. Normalize parameters
        normalized_params = self.param_resolver.resolve(
            raw_params=request.params,
            tier_normalizer=self.tier_normalizer,
        )
        
        # 2. Resolve ingest source (if applicable)
        ingest_resolution = None
        if self._is_ingest_pipeline(request.pipeline):
            ingest_resolution = self.ingest_resolver.resolve(
                pipeline=request.pipeline,
                params=normalized_params,
            )
        
        # 3. Dry run check
        if request.dry_run:
            return RunPipelineResult(
                success=True,
                execution_id=None,
                status="dry_run",
                duration_seconds=None,
                metrics=None,
                error=None,
                ingest_resolution=ingest_resolution,
                dry_run=True,
            )
        
        # 4. Execute via Dispatcher
        try:
            dispatcher = Dispatcher()
            execution = dispatcher.submit(
                pipeline=request.pipeline,
                params=normalized_params,
                lane=Lane(request.lane),
                trigger_source=TriggerSource.CLI,  # or API
            )
            # ... build and return result
        except PipelineNotFoundError:
            return RunPipelineResult(
                success=False,
                error=PipelineError(
                    code="PIPELINE_NOT_FOUND",
                    message=f"Pipeline '{request.pipeline}' not found.",
                    details={},
                ),
                # ...
            )
```

---

## API Adapter (Future)

```python
# market_spine/api/routes/executions.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class RunPipelineBody(BaseModel):
    pipeline: str
    params: dict[str, Any] = {}
    lane: str = "normal"
    dry_run: bool = False

class RunPipelineResponse(BaseModel):
    execution_id: str | None
    status: str
    duration_seconds: float | None
    metrics: dict[str, Any] | None
    ingest_resolution: dict[str, Any] | None

@router.post("/v1/executions")
def run_pipeline(body: RunPipelineBody) -> RunPipelineResponse:
    request = RunPipelineRequest(
        pipeline=body.pipeline,
        params=body.params,
        lane=body.lane,
        dry_run=body.dry_run,
    )
    
    result = RunPipelineCommand().execute(request)
    
    if not result.success:
        raise HTTPException(
            status_code=400 if result.error.code == "INVALID_PARAMS" else 500,
            detail=result.error.__dict__,
        )
    
    return RunPipelineResponse(
        execution_id=result.execution_id,
        status=result.status,
        duration_seconds=result.duration_seconds,
        metrics=result.metrics,
        ingest_resolution=asdict(result.ingest_resolution) if result.ingest_resolution else None,
    )
```

---

## Services Layer

### TierNormalizer

```python
# market_spine/app/services/tier.py

from spine.domains.finra.otc_transparency.constants import TIER_ALIASES, Tier

class TierNormalizer:
    """Normalize tier strings to canonical values."""
    
    def normalize(self, tier: str | None) -> str | None:
        if tier is None:
            return None
        canonical = TIER_ALIASES.get(tier.lower(), tier.upper())
        if canonical not in [t.value for t in Tier]:
            raise ValueError(f"Invalid tier: {tier}")
        return canonical
```

### ParameterResolver

```python
# market_spine/app/services/params.py

class ParameterResolver:
    """Resolve and validate pipeline parameters."""
    
    def resolve(
        self,
        raw_params: dict[str, Any],
        tier_normalizer: TierNormalizer,
    ) -> dict[str, Any]:
        resolved = dict(raw_params)
        
        # Normalize tier if present
        if "tier" in resolved:
            resolved["tier"] = tier_normalizer.normalize(resolved["tier"])
        
        return resolved
```

### IngestResolver

```python
# market_spine/app/services/ingest.py

@dataclass
class IngestResolution:
    source_type: str  # "explicit" | "derived"
    file_path: str
    derivation_logic: str | None

class IngestResolver:
    """Resolve ingest file paths."""
    
    def resolve(self, pipeline: str, params: dict[str, Any]) -> IngestResolution:
        if "file_path" in params and params["file_path"]:
            return IngestResolution(
                source_type="explicit",
                file_path=params["file_path"],
                derivation_logic=None,
            )
        
        # Derive from week_ending and tier
        week = params.get("week_ending")
        tier = params.get("tier")
        
        if not week or not tier:
            raise ValueError("Cannot derive file path: week_ending and tier required")
        
        derived_path = f"data/finra/finra_otc_weekly_{tier.lower()}_{week}.csv"
        
        return IngestResolution(
            source_type="derived",
            file_path=derived_path,
            derivation_logic=f"Pattern: data/finra/finra_otc_weekly_{{tier}}_{{week}}.csv",
        )
```

---

## What Should NOT Be Extracted

### CLI-Only Affordances

| Feature | Why CLI-Only |
|---------|--------------|
| `--help-params` | Interactive help is CLI-specific |
| `--quiet` | Suppresses terminal output; irrelevant for API |
| Rich progress bars | Terminal animation; API uses polling |
| `typer.Exit()` | CLI exit codes; API uses HTTP status |
| `console.print()` | Terminal output; API returns JSON |
| Keyboard interrupt handling | Ctrl+C is terminal-specific |

### CLI-Specific Validation

```python
# This stays in CLI only
def validate_file_exists(file_path: str) -> bool:
    """Validate file path exists."""
    return Path(file_path).exists()
```

The API might receive file paths that don't exist yet (e.g., pre-signed URLs, remote paths). This validation is CLI-specific.

---

## Recommendations

### Do Now ✅

1. **Create `market_spine/app/` directory** with:
   - `commands/` — Start with `executions.py`, `pipelines.py`, `queries.py`
   - `services/` — `tier.py`, `params.py`, `ingest.py`
   - `models.py` — Shared request/response dataclasses

2. **Extract `TierNormalizer` first** — It's pure logic with no dependencies. Easy win.

3. **Extract `IngestResolver` second** — The `show_ingest_resolution()` logic in `run.py` lines 174-230 can become a service.

4. **Add tests for extracted services** — These become the contract for CLI and API.

### Defer ⏸️

5. **Full command extraction** — Do this incrementally. Extract `RunPipelineCommand` when building API.

6. **Generic `Command` base class** — Start with concrete implementations. Abstract later if patterns emerge.

7. **Dependency injection framework** — Manual constructor injection is fine for Basic tier.

### Never Do ❌

8. **Expose `--help-params` as API endpoint** — This is CLI affordance. API consumers read OpenAPI docs.

9. **Return Rich markup in API responses** — API responses are JSON, never styled text.

10. **Raise `typer.Exit()` from command layer** — Commands return results; adapters decide how to exit.

---

## Migration Path

### Phase 1: Extract Services (No CLI Changes)

```
market_spine/
├── app/
│   ├── __init__.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── tier.py        # TierNormalizer
│   │   ├── params.py      # ParameterResolver
│   │   └── ingest.py      # IngestResolver
```

CLI still works as-is. Services are importable but not yet called.

### Phase 2: CLI Calls Services

Update `console.py`:
```python
# Before
from .console import normalize_tier

# After
from ..app.services.tier import TierNormalizer
normalizer = TierNormalizer()
tier = normalizer.normalize(tier)
```

All CLI tests must pass.

### Phase 3: Extract Commands (When Building API)

Create `RunPipelineCommand`. CLI calls it. Verify CLI tests. Then add API routes.

---

## Summary

The CLI → API boundary is **well-defined but not yet implemented**. The key insight is:

> The CLI currently does orchestration, validation, and presentation in one place. Extract orchestration and validation to a command layer; leave presentation in CLI.

Start with services (pure logic), then commands (orchestration), then API (new adapter).
