# Step Types Reference

> **Document**: All step types in Orchestration v2

## Overview

Steps are the building blocks of workflows. Each step type serves a specific purpose:

| Type | Purpose | When to Use |
|------|---------|-------------|
| `LambdaStep` | Inline function | Validation, transformation, lightweight logic |
| `PipelineStep` | Registered pipeline | Heavy operations (DB, API, file I/O) |
| `ChoiceStep` | Conditional branch | Route based on prior results |
| `WaitStep` | Delay | Rate limiting, scheduling |
| `MapStep` | Fan-out/fan-in | Process collections in parallel |

## StepResult (Common Return Type)

All steps return a `StepResult`:

```python
@dataclass
class StepResult:
    """Universal result envelope for all step types."""
    
    success: bool                              # Did the step succeed?
    output: dict[str, Any] = field(default_factory=dict)  # Step output
    context_updates: dict[str, Any] = field(default_factory=dict)  # Params to merge
    error: str | None = None                   # Error message if failed
    error_category: str | None = None          # NETWORK, VALIDATION, etc.
    quality: QualityMetrics | None = None      # Data quality metrics
    events: list[dict] = field(default_factory=list)  # Structured logs
    next_step: str | None = None               # Override next step (for branching)
    
    @classmethod
    def ok(cls, output=None, context_updates=None, events=None, quality=None):
        """Factory for successful result."""
        return cls(
            success=True,
            output=output or {},
            context_updates=context_updates or {},
            events=events or [],
            quality=quality,
        )
    
    @classmethod
    def fail(cls, error: str, category: str = None, output=None):
        """Factory for failed result."""
        return cls(
            success=False,
            error=error,
            error_category=category,
            output=output or {},
        )
```

---

## LambdaStep

Inline functions that receive context and return results.

### Definition

```python
@dataclass
class LambdaStep:
    """A step that executes an inline function."""
    
    name: str                                  # Unique name in workflow
    handler: Callable[[WorkflowContext, dict], StepResult]  # The function
    config: dict = field(default_factory=dict) # Step-specific config
    on_error: ErrorPolicy = ErrorPolicy.STOP   # STOP or CONTINUE
    retry_policy: RetryPolicy | None = None    # Retry config
    description: str = ""
```

### Usage

```python
from spine.orchestration import Workflow, Step, WorkflowContext, StepResult

# Define a lambda step function
def validate_records(ctx: WorkflowContext, config: dict) -> StepResult:
    """Validate records from prior fetch step."""
    records = ctx.get_output("fetch", "records", [])
    
    if not records:
        return StepResult.fail("No records to validate")
    
    # Validate each record
    valid = []
    invalid = []
    for record in records:
        if record.get("symbol") and record.get("volume", 0) > 0:
            valid.append(record)
        else:
            invalid.append(record)
    
    # Quality metrics
    quality = QualityMetrics(
        record_count=len(records),
        valid_count=len(valid),
        null_rate=len(invalid) / len(records) if records else 0,
    )
    
    return StepResult.ok(
        output={
            "valid_records": valid,
            "invalid_count": len(invalid),
        },
        context_updates={"validation_passed": len(valid) > 0},
        quality=quality,
    )

# Use in workflow
workflow = Workflow(
    name="my_workflow",
    steps=[
        Step.pipeline("fetch", "my_domain.fetch_data"),
        Step.lambda_("validate", validate_records),  # Lambda step
    ],
)
```

### Best Practices for LambdaSteps

1. **Keep them lightweight** - No DB writes, API calls, or heavy I/O
2. **Pure functions** - Same inputs → same outputs
3. **Read from context** - Use `ctx.get_output()` for prior results
4. **Return quality metrics** - For data quality tracking

---

## PipelineStep

Wraps existing registered pipelines to participate in context flow.

### Definition

```python
@dataclass
class PipelineStep:
    """A step that executes a registered pipeline."""
    
    name: str                                  # Step name in workflow
    pipeline: str                              # Registry key (e.g., "finra.ingest_week")
    params: dict = field(default_factory=dict) # Extra params for this step
    on_error: ErrorPolicy = ErrorPolicy.STOP
```

### How It Works

The runner:
1. Looks up the pipeline in the registry
2. Merges `context.params` + `step.params` 
3. Submits to Dispatcher
4. Wraps `PipelineResult` as `StepResult`

```python
# Inside WorkflowRunner
def _execute_pipeline_step(self, step: PipelineStep, ctx: WorkflowContext) -> StepResult:
    # Merge params
    params = {**ctx.params, **step.params}
    
    # Also inject step_outputs for pipelines that want prior results
    params["__step_outputs"] = ctx.step_outputs
    
    # Execute via dispatcher
    execution = self.dispatcher.submit(step.pipeline, params)
    
    # Convert to StepResult
    if execution.status == "completed":
        return StepResult.ok(
            output={"pipeline_result": execution.result.to_dict()},
        )
    else:
        return StepResult.fail(execution.error or "Pipeline failed")
```

### Usage

```python
workflow = Workflow(
    name="finra_weekly",
    steps=[
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week",
            params={"tier": "NMS_TIER_1"}),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
    ],
)
```

### Context-Aware Pipelines

Pipelines can read prior step outputs via injected params:

```python
@register_pipeline("my_domain.load_data")
class LoadDataPipeline(Pipeline):
    def run(self) -> PipelineResult:
        # Access prior step outputs (injected by WorkflowRunner)
        step_outputs = self.params.get("__step_outputs", {})
        validation = step_outputs.get("validate", {})
        
        if not validation.get("validation_passed"):
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error="Validation did not pass",
            )
        
        # Proceed with load
        ...
```

---

## ChoiceStep

Conditional branching based on context.

### Definition

```python
@dataclass
class ChoiceStep:
    """A step that routes execution based on a condition."""
    
    name: str
    condition: Callable[[WorkflowContext], bool]  # Returns True/False
    then_step: str                                 # Step name if True
    else_step: str | None = None                   # Step name if False (or continue)
```

### Usage

```python
workflow = Workflow(
    name="conditional_etl",
    steps=[
        Step.pipeline("fetch", "data.fetch"),
        Step.lambda_("validate", validate_data),
        
        # Branch based on validation score
        Step.choice("route_by_quality",
            condition=lambda ctx: ctx.get_output("validate", "score", 0) > 0.95,
            then_step="fast_load",
            else_step="full_reprocess",
        ),
        
        # Fast path
        Step.pipeline("fast_load", "data.quick_load"),
        
        # Full reprocess path
        Step.pipeline("full_reprocess", "data.full_etl"),
        
        # Both paths join here
        Step.lambda_("notify", send_notification),
    ],
)
```

### Execution Model

The runner:
1. Evaluates `condition(context)`
2. If True, jumps to `then_step`
3. If False, jumps to `else_step` (or continues if None)
4. Skipped steps are marked as `SKIPPED`

---

## WaitStep

Introduce delays in workflow execution.

### Definition

```python
@dataclass
class WaitStep:
    """A step that waits before continuing."""
    
    name: str
    seconds: int | None = None                    # Fixed delay
    until: Callable[[WorkflowContext], datetime] | None = None  # Wait until time
```

### Usage

```python
workflow = Workflow(
    steps=[
        Step.pipeline("fetch_page_1", "api.fetch", params={"page": 1}),
        Step.wait("rate_limit", seconds=1),  # Rate limiting
        Step.pipeline("fetch_page_2", "api.fetch", params={"page": 2}),
        Step.wait("rate_limit_2", seconds=1),
        Step.pipeline("fetch_page_3", "api.fetch", params={"page": 3}),
    ],
)
```

---

## MapStep (Future)

Fan-out/fan-in for parallel processing.

### Definition

```python
@dataclass
class MapStep:
    """Process a collection in parallel."""
    
    name: str
    items_from: Callable[[WorkflowContext], list]  # Get items from context
    step: str                                       # Step to execute per item
    max_concurrency: int = 10
    on_error: MapErrorPolicy = MapErrorPolicy.PARTIAL  # Continue on item failure
```

### Usage (Future)

```python
workflow = Workflow(
    steps=[
        # Fetch list of symbols
        Step.pipeline("get_symbols", "data.list_symbols"),
        
        # Process each symbol in parallel
        Step.map("process_symbols",
            items_from=lambda ctx: ctx.get_output("get_symbols", "symbols"),
            step="process_one_symbol",
            max_concurrency=10,
        ),
        
        # Aggregate results
        Step.lambda_("aggregate", aggregate_results),
    ],
)
```

---

## Step Factory Methods

The `Step` class provides factory methods for convenience:

```python
class Step:
    @staticmethod
    def pipeline(name: str, pipeline: str, **kwargs) -> PipelineStep:
        return PipelineStep(name=name, pipeline=pipeline, **kwargs)
    
    @staticmethod
    def lambda_(name: str, handler: Callable, **kwargs) -> LambdaStep:
        return LambdaStep(name=name, handler=handler, **kwargs)
    
    @staticmethod
    def choice(name: str, condition: Callable, then_step: str, else_step: str = None) -> ChoiceStep:
        return ChoiceStep(name=name, condition=condition, then_step=then_step, else_step=else_step)
    
    @staticmethod
    def wait(name: str, seconds: int) -> WaitStep:
        return WaitStep(name=name, seconds=seconds)
```

### Usage

```python
# Fluent API
workflow = Workflow(
    name="my_workflow",
    steps=[
        Step.pipeline("fetch", "data.fetch"),
        Step.lambda_("validate", validate_func),
        Step.choice("route", condition=lambda ctx: ..., then_step="a", else_step="b"),
        Step.wait("delay", seconds=5),
    ],
)
```

---

## Error Policies

Each step can specify what happens on failure:

```python
class ErrorPolicy(str, Enum):
    STOP = "stop"          # Stop workflow execution
    CONTINUE = "continue"  # Skip to next step
    RETRY = "retry"        # Retry per RetryPolicy
```

```python
# Stop on failure (default)
Step.pipeline("critical", "data.load", on_error=ErrorPolicy.STOP)

# Continue on failure
Step.lambda_("optional", send_email, on_error=ErrorPolicy.CONTINUE)
```

---

## Retry Policies (Future)

```python
@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0
    retryable_categories: tuple[str, ...] = ("NETWORK", "TIMEOUT")
```

```python
Step.pipeline("api_call", "external.fetch",
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_seconds=5,
        retryable_categories=("NETWORK",),
    ),
)
```
