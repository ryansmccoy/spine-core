# Orchestration v2

This document covers the new workflow orchestration system that enables context-passing between steps.

---

## Overview

**Orchestration v2** introduces:
- `Workflow`: Named collection of steps
- `WorkflowContext`: Immutable context passed step-to-step
- `StepResult`: Universal return envelope for steps
- `Step` types: Lambda, Pipeline, Choice (and Map/Wait in Advanced)
- `WorkflowRunner`: Executes workflows with error handling

### Why a New Orchestration?

The original `PipelineGroup` is great for simple DAGs of registered pipelines. But it lacks:
- **Data passing**: Outputs from one step can't flow to the next
- **Inline logic**: Can't add validation, routing, or notification logic
- **Conditional branching**: No if/then/else support

Workflow v2 addresses all of these while maintaining compatibility with existing pipelines.

---

## Core Concepts

### Workflow

A workflow is a named sequence of steps:

```python
from spine.orchestration import Workflow, Step

workflow = Workflow(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        Step.pipeline("ingest", "finra.otc.ingest_week"),
        Step.lambda_("validate", validate_fn),
        Step.pipeline("normalize", "finra.otc.normalize"),
    ],
)
```

### WorkflowContext

The context flows through every step:

```python
from spine.orchestration import WorkflowContext

ctx = WorkflowContext.create(
    workflow_name="finra.weekly_refresh",
    params={"week_ending": "2026-01-10", "tier": "NMS_TIER_1"},
    partition={"tier": "NMS_TIER_1"},
)

# Context is immutable - methods return new instances
ctx2 = ctx.with_output("ingest", {"record_count": 5000})
ctx3 = ctx2.with_params({"validated": True})
```

**Key Properties**:
| Property | Description |
|----------|-------------|
| `run_id` | Unique identifier for this execution |
| `workflow_name` | Name of the workflow |
| `params` | Input parameters + accumulated state |
| `outputs` | Step outputs keyed by step name |
| `partition` | Partition key for tracking |
| `execution` | ExecutionContext for lineage |

**Reading from Context**:
```python
def my_step(ctx: WorkflowContext, config: dict) -> StepResult:
    # Get input parameter
    tier = ctx.get_param("tier")
    
    # Get output from previous step
    count = ctx.get_output("ingest", "record_count", default=0)
    
    # Check if step ran
    if ctx.has_output("ingest"):
        ...
```

### StepResult

Every step returns a `StepResult`:

```python
from spine.orchestration import StepResult

def my_step(ctx, config) -> StepResult:
    # Success with output
    return StepResult.ok(
        output={"processed": 100},
        context_updates={"last_step": "my_step"},
    )

def failing_step(ctx, config) -> StepResult:
    # Failure
    return StepResult.fail(
        error="Validation failed: too few records",
        category="DATA_QUALITY",
    )

def skip_step(ctx, config) -> StepResult:
    # Skip (success, but no work done)
    return StepResult.skip(reason="Already processed today")
```

---

## Step Types

### Lambda Steps

Inline functions for validation, routing, or custom logic:

```python
def validate_records(ctx: WorkflowContext, config: dict) -> StepResult:
    count = ctx.get_output("ingest", "record_count", 0)
    threshold = config.get("min_records", 100)
    
    if count < threshold:
        return StepResult.fail(
            error=f"Only {count} records, need at least {threshold}",
            category="DATA_QUALITY",
        )
    
    return StepResult.ok(output={"validated": True})

Step.lambda_("validate", validate_records, config={"min_records": 100})
```

### Pipeline Steps

Wrap registered pipelines:

```python
Step.pipeline("ingest", "finra.otc.ingest_week", params={"force": True})
```

The runner:
1. Merges `context.params` with step's `params`
2. Calls the pipeline via `Dispatcher`
3. Converts `PipelineResult` to `StepResult`

### Choice Steps (Intermediate Tier)

Conditional branching:

```python
Step.choice(
    "route",
    condition=lambda ctx: ctx.get_output("validate", "validated", False),
    then_step="process",    # Jump here if True
    else_step="reject",     # Jump here if False
)
```

**Example Workflow with Choice**:
```python
workflow = Workflow(
    name="conditional.example",
    steps=[
        Step.pipeline("ingest", "data.ingest"),
        Step.lambda_("validate", validate_fn),
        Step.choice("route",
            condition=lambda ctx: ctx.get_output("validate", "valid"),
            then_step="process",
            else_step="alert_and_skip",
        ),
        Step.pipeline("process", "data.process"),
        Step.lambda_("alert_and_skip", send_alert_fn),
    ],
)
```

### Wait Steps (Advanced Tier)

Pause execution:

```python
Step.wait("cooldown", duration_seconds=300)  # Wait 5 minutes
```

In Basic tier, this uses `time.sleep()`. In Advanced tier, it would schedule a timer and checkpoint.

### Map Steps (Advanced Tier)

Fan-out/fan-in parallel execution:

```python
Step.map(
    "process_items",
    items_path="items",  # ctx.params["items"]
    iterator_workflow=item_workflow,
    max_concurrency=4,
)
```

---

## WorkflowRunner

Executes workflows:

```python
from spine.orchestration import WorkflowRunner, Workflow

runner = WorkflowRunner()
result = runner.execute(
    workflow=workflow,
    params={"week_ending": "2026-01-10"},
    partition={"tier": "NMS_TIER_1"},
)

if result.status == WorkflowStatus.COMPLETED:
    print(f"Success! Duration: {result.duration_seconds}s")
    print(f"Steps completed: {result.completed_steps}")
else:
    print(f"Failed at step '{result.error_step}': {result.error}")
```

### WorkflowResult

```python
@dataclass
class WorkflowResult:
    workflow_name: str
    run_id: str
    status: WorkflowStatus  # COMPLETED, FAILED, PARTIAL
    context: WorkflowContext
    started_at: datetime
    completed_at: datetime | None
    step_executions: list[StepExecution]
    error_step: str | None
    error: str | None
```

### Dry Run Mode

Test workflows without side effects:

```python
runner = WorkflowRunner(dry_run=True)
result = runner.execute(workflow, params={...})
# Pipeline steps return mock success
```

### Resume from Checkpoint

Resume a failed workflow:

```python
# Save context after failure
saved_context = result.context.to_dict()

# Later: resume from checkpoint
context = WorkflowContext.from_dict(saved_context)
result = runner.execute(
    workflow,
    context=context,
    start_from="failed_step",  # Skip completed steps
)
```

---

## Error Handling

### Error Policy Per Step

```python
from spine.orchestration import ErrorPolicy

# Stop on error (default)
Step.pipeline("critical", "important.pipeline", on_error=ErrorPolicy.STOP)

# Continue to next step
Step.pipeline("optional", "nice.to.have", on_error=ErrorPolicy.CONTINUE)
```

### Workflow Status

| Status | Meaning |
|--------|---------|
| `COMPLETED` | All steps succeeded |
| `FAILED` | A step failed with `ErrorPolicy.STOP` |
| `PARTIAL` | Some steps failed with `ErrorPolicy.CONTINUE` |

---

## Quality Metrics

Steps can report quality metrics:

```python
from spine.orchestration import StepResult, QualityMetrics

def validate_data(ctx, config) -> StepResult:
    records = ctx.get_output("ingest", "data", [])
    valid = [r for r in records if is_valid(r)]
    
    quality = QualityMetrics(
        record_count=len(records),
        valid_count=len(valid),
        invalid_count=len(records) - len(valid),
        passed=len(valid) / len(records) > 0.95,
    )
    
    if not quality.passed:
        return StepResult.fail(
            error=f"Quality gate failed: {quality.valid_rate:.1%} valid",
            category="DATA_QUALITY",
            quality=quality,
        )
    
    return StepResult.ok(
        output={"valid_count": len(valid)},
        quality=quality,
    )
```

---

## Complete Example

```python
from spine.orchestration import (
    Workflow,
    Step,
    StepResult,
    WorkflowRunner,
    WorkflowContext,
    QualityMetrics,
)
from spine.framework.alerts import send_alert, AlertSeverity

# Step 1: Validation lambda
def validate_fn(ctx: WorkflowContext, config: dict) -> StepResult:
    count = ctx.get_output("ingest", "row_count", 0)
    min_count = config.get("min_records", 100)
    
    quality = QualityMetrics(
        record_count=count,
        valid_count=count if count >= min_count else 0,
        passed=count >= min_count,
    )
    
    if not quality.passed:
        return StepResult.fail(
            error=f"Only {count} records, need {min_count}",
            category="DATA_QUALITY",
            quality=quality,
        )
    
    return StepResult.ok(output={"validated": True}, quality=quality)

# Step 2: Alert lambda (for failures)
def alert_fn(ctx: WorkflowContext, config: dict) -> StepResult:
    send_alert(
        severity=AlertSeverity.WARNING,
        title=f"Workflow {ctx.workflow_name} skipped processing",
        message="Insufficient records to process",
        source=ctx.workflow_name,
        run_id=ctx.run_id,
    )
    return StepResult.ok(output={"alerted": True})

# Define workflow
workflow = Workflow(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    description="Weekly FINRA OTC data refresh with validation",
    steps=[
        Step.pipeline("ingest", "finra.otc.ingest_week"),
        Step.lambda_("validate", validate_fn, config={"min_records": 100}),
        Step.choice("route",
            condition=lambda ctx: ctx.get_output("validate", "validated", False),
            then_step="normalize",
            else_step="alert",
        ),
        Step.pipeline("normalize", "finra.otc.normalize"),
        Step.lambda_("alert", alert_fn),
    ],
)

# Execute
runner = WorkflowRunner()
result = runner.execute(
    workflow,
    params={"week_ending": "2026-01-10"},
    partition={"tier": "NMS_TIER_1"},
)

print(f"Status: {result.status}")
print(f"Duration: {result.duration_seconds}s")
print(f"Completed: {result.completed_steps}")
```

---

## SQL Schema

Workflow execution is tracked in the database:

### `core_workflow_runs`

```sql
CREATE TABLE core_workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    status TEXT NOT NULL,  -- PENDING, RUNNING, COMPLETED, FAILED
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    params TEXT,           -- JSON
    outputs TEXT,          -- JSON
    error TEXT,
    error_category TEXT,
    total_steps INTEGER,
    completed_steps INTEGER,
    failed_steps INTEGER,
    triggered_by TEXT,     -- manual, schedule, api
    parent_run_id TEXT,
    schedule_id TEXT
);
```

### `core_workflow_steps`

```sql
CREATE TABLE core_workflow_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_type TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    params TEXT,
    outputs TEXT,
    error TEXT,
    error_category TEXT,
    row_count INTEGER,
    attempt INTEGER NOT NULL DEFAULT 1
);
```

---

## Tier Comparison

| Feature | Basic | Intermediate | Advanced |
|---------|-------|--------------|----------|
| Lambda steps | ✅ | ✅ | ✅ |
| Pipeline steps | ✅ | ✅ | ✅ |
| WorkflowContext | ✅ | ✅ | ✅ |
| StepResult | ✅ | ✅ | ✅ |
| Choice steps | ❌ | ✅ | ✅ |
| SQL history | ❌ | ✅ | ✅ |
| Wait steps | ❌ | ❌ | ✅ |
| Map steps | ❌ | ❌ | ✅ |
| Retry policies | ❌ | ❌ | ✅ |
| Checkpointing | ❌ | ❌ | ✅ |

---

## Best Practices

### 1. Use Lambda Steps for Logic

```python
# ❌ Creating a pipeline just for validation
@pipeline("my.validate")
def validate_pipeline(params):
    ...

# ✅ Use inline lambda
def validate_fn(ctx, config):
    ...
    return StepResult.ok(...)

Step.lambda_("validate", validate_fn)
```

### 2. Read from Previous Steps

```python
# ❌ Re-fetching data
def step2(ctx, config):
    data = fetch_data_again()

# ✅ Use context outputs
def step2(ctx, config):
    data = ctx.get_output("step1", "data")
```

### 3. Use Context Updates Sparingly

```python
# ❌ Storing large data in context
return StepResult.ok(context_updates={"all_rows": huge_list})

# ✅ Store summary/references
return StepResult.ok(
    context_updates={"row_count": len(rows)},
    output={"data": rows},  # Output goes to ctx.outputs
)
```

### 4. Handle Errors Appropriately

```python
# ❌ Using exceptions for flow control
def my_step(ctx, config):
    if not valid:
        raise ValueError("Invalid data")

# ✅ Return failure result
def my_step(ctx, config):
    if not valid:
        return StepResult.fail("Invalid data", category="VALIDATION")
```
