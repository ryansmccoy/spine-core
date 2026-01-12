# Checkpointing and Resumption

> **Document**: Resume failed workflows from last successful step

## Overview

Checkpointing enables:

- **Resume from failure**: Continue from last successful step after fixing issues
- **Long-running workflows**: Save progress for workflows that span hours/days
- **Fault tolerance**: Survive process crashes, deploys, restarts
- **Debugging**: Inspect state at any point in workflow history

---

## How Checkpointing Works

### Checkpoint Creation

After each successful step, the runner serializes and stores:

```python
@dataclass
class Checkpoint:
    run_id: str                    # Unique run identifier
    workflow_name: str             # Name of workflow
    step_name: str                 # Last completed step
    context_snapshot: dict         # Serialized WorkflowContext
    step_outputs: dict[str, Any]   # Outputs from all completed steps
    created_at: datetime           # Checkpoint timestamp
```

### Storage

Checkpoints are stored in `core_workflow_checkpoints`:

```sql
CREATE TABLE core_workflow_checkpoints (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    context_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_run_step UNIQUE (run_id, step_name)
);
```

---

## Basic Resume

### Scenario: Workflow Fails Mid-Execution

```python
from spine.orchestration import WorkflowRunner, Workflow, Step

workflow = Workflow(
    name="my.workflow",
    steps=[
        Step.pipeline("step1", "my.step1"),  # ✅ Completes
        Step.pipeline("step2", "my.step2"),  # ✅ Completes
        Step.pipeline("step3", "my.step3"),  # ❌ Fails (external API down)
        Step.pipeline("step4", "my.step4"),  # ⏸️ Not reached
    ],
)

runner = WorkflowRunner()
result = runner.execute(workflow, params={"key": "value"})

# Result:
# - status: "failed"
# - error_step: "step3"
# - error: "External API timeout"
# - run_id: "abc-123"
# - completed_steps: ["step1", "step2"]
```

### Fix Issue and Resume

```python
# External API is back up, resume the run
result = runner.resume("abc-123")

# Result:
# - Loads checkpoint from step2
# - Continues from step3
# - status: "completed"
# - completed_steps: ["step3", "step4"]
```

---

## Resume with Modified Parameters

Sometimes you need to change parameters before resuming:

```python
# Original run
result = runner.execute(workflow, params={
    "api_url": "https://api.example.com",
    "timeout": 30,
})
# Failed due to timeout

# Resume with higher timeout
result = runner.resume(
    "abc-123",
    params_override={
        "timeout": 120,  # Increase timeout
    },
)
```

---

## Checkpoint Strategies

### Checkpoint Every Step (Default)

```python
runner = WorkflowRunner(
    checkpoint_strategy="every_step",
)
```

Pros:
- Maximum granularity
- Resume from exact failure point

Cons:
- Higher storage/IO overhead

### Checkpoint at Key Steps

```python
workflow = Workflow(
    steps=[
        Step.pipeline("fetch", "my.fetch", checkpoint=True),
        Step.pipeline("transform1", "my.transform1"),  # No checkpoint
        Step.pipeline("transform2", "my.transform2"),  # No checkpoint
        Step.pipeline("load", "my.load", checkpoint=True),  # Checkpoint here
    ],
)
```

### Checkpoint on Expensive Steps

```python
def expensive_step(ctx: WorkflowContext, config: dict) -> StepResult:
    # This step takes 30 minutes
    result = run_expensive_computation()
    
    return StepResult.ok(
        output=result,
        checkpoint=True,  # Force checkpoint after this step
    )
```

---

## Checkpoint Context

### What Gets Saved

```python
checkpoint_data = {
    "run_id": "abc-123",
    "workflow_name": "my.workflow",
    "step_name": "step2",
    
    "context": {
        "params": {
            "key": "value",
            "derived_key": "computed_value",
        },
        "outputs": {
            "step1": {"records": 1000},
            "step2": {"processed": 950},
        },
        "quality_metrics": {
            "step1": {"passed": True, "record_count": 1000},
        },
        "partition": {"date": "2026-01-10"},
    },
    
    "metadata": {
        "created_at": "2026-01-10T12:00:00Z",
        "python_version": "3.12",
        "spine_version": "0.1.0",
    },
}
```

### Large Output Handling

For steps with large outputs:

```python
def large_output_step(ctx: WorkflowContext, config: dict) -> StepResult:
    # Process 1M records
    records = process_large_dataset()
    
    # Don't store all records in output - store reference
    return StepResult.ok(
        output={
            "record_count": len(records),
            "storage_path": "s3://bucket/run-abc-123/step1.parquet",
        },
        # Actual data stored externally
    )
```

---

## Manual Checkpoint Operations

### List Checkpoints for a Run

```python
checkpoints = runner.list_checkpoints("abc-123")

for cp in checkpoints:
    print(f"{cp.step_name}: {cp.created_at}")

# Output:
# step1: 2026-01-10 12:00:00
# step2: 2026-01-10 12:00:05
```

### Inspect Checkpoint State

```python
checkpoint = runner.get_checkpoint("abc-123", step="step2")

print(checkpoint.context.params)
print(checkpoint.context.outputs)
```

### Delete Checkpoints

```python
# Delete all checkpoints for a run (after successful completion)
runner.delete_checkpoints("abc-123")

# Or rely on automatic cleanup (retention policy)
```

---

## Resume Scenarios

### Resume from Specific Step

```python
# Skip re-running step3, start from step4
result = runner.execute(
    workflow,
    run_id="abc-123",
    start_from="step4",  # Skip to this step
)
```

### Re-run from Beginning with Same Params

```python
# Get params from failed run
failed_run = runner.get_run("abc-123")
params = failed_run.context.params

# Start fresh with same params
result = runner.execute(workflow, params=params)
# New run_id generated
```

### Resume with Context Override

```python
# Load checkpoint
checkpoint = runner.get_checkpoint("abc-123", step="step2")
context = checkpoint.context

# Modify context
context = context.with_params({
    "force_refresh": True,  # Add new param
})

# Resume with modified context
result = runner.execute(
    workflow,
    context=context,
    start_from="step3",
)
```

---

## Idempotency Considerations

### Why Idempotency Matters

When resuming, the failed step may have:
- Partially completed
- Written some records
- Made some API calls

Steps should be designed to handle re-execution safely.

### Idempotency Patterns

```python
def idempotent_step(ctx: WorkflowContext, config: dict) -> StepResult:
    partition = ctx.partition  # e.g., {"date": "2026-01-10"}
    
    # Check if already processed
    existing = query_manifest(partition)
    if existing and existing.status == "complete":
        return StepResult.ok(
            output={"skipped": True, "reason": "already processed"},
        )
    
    # Use INSERT ... ON CONFLICT DO UPDATE
    # or DELETE + INSERT for the partition
    upsert_records(partition, data)
    
    return StepResult.ok(output={"processed": len(data)})
```

### Cleanup on Resume

```python
def resumable_step(ctx: WorkflowContext, config: dict) -> StepResult:
    partition = ctx.partition
    
    # Clean up any partial data from failed run
    delete_partial_data(partition)
    
    # Fresh insert
    insert_records(partition, data)
    
    return StepResult.ok(output={"processed": len(data)})
```

---

## Checkpoint Retention

### Automatic Cleanup

```python
runner = WorkflowRunner(
    checkpoint_retention_days=7,  # Keep for 7 days
)
```

### Retention Policy

```sql
-- Delete old checkpoints (run daily)
DELETE FROM core_workflow_checkpoints
WHERE created_at < NOW() - INTERVAL '7 days'
  AND run_id NOT IN (
      -- Keep checkpoints for failed runs that might resume
      SELECT run_id FROM core_workflow_runs 
      WHERE status = 'failed' 
        AND created_at > NOW() - INTERVAL '7 days'
  );
```

---

## Best Practices

### 1. Design for Resume

```python
# ❌ Bad: Step depends on external state that may change
def bad_step(ctx, config):
    data = fetch_current_prices()  # Different on resume!
    return StepResult.ok(output={"data": data})

# ✅ Good: Step uses deterministic inputs
def good_step(ctx, config):
    date = ctx.params["price_date"]  # Saved in checkpoint
    data = fetch_prices_for_date(date)  # Same on resume
    return StepResult.ok(output={"data": data})
```

### 2. Small, Focused Steps

```python
# ❌ Bad: One giant step that's hard to resume
workflow = Workflow(steps=[
    Step.lambda_("do_everything", massive_function),
])

# ✅ Good: Small steps with clear boundaries
workflow = Workflow(steps=[
    Step.pipeline("fetch", "my.fetch"),
    Step.lambda_("validate", validate_fn),
    Step.pipeline("transform", "my.transform"),
    Step.pipeline("load", "my.load"),
])
```

### 3. Store References, Not Data

```python
# ❌ Bad: Store large data in checkpoint
return StepResult.ok(output={"all_records": million_records})

# ✅ Good: Store reference to data
return StepResult.ok(output={
    "record_count": len(million_records),
    "table": "staging_records",
    "partition": "2026-01-10",
})
```

### 4. Handle Resume in Notifications

```python
def notify_step(ctx: WorkflowContext, config: dict) -> StepResult:
    is_resume = ctx.params.get("__resumed__", False)
    
    if is_resume:
        message = "Workflow RESUMED and completed successfully"
    else:
        message = "Workflow completed successfully"
    
    send_notification(message)
    return StepResult.ok(output={"sent": True})
```
