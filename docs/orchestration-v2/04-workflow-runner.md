# Workflow Runner

> **Document**: WorkflowRunner implementation and execution model

## Overview

The `WorkflowRunner` is the execution engine for Orchestration v2. It:

- Executes workflow steps in sequence
- Manages context propagation between steps
- Handles errors according to configured policies
- Records execution history for observability
- Supports checkpointing for resume

## Basic Usage

```python
from spine.orchestration import WorkflowRunner, Workflow, Step

# Define workflow
my_workflow = Workflow(
    name="my.workflow",
    steps=[
        Step.pipeline("step1", "my.pipeline"),
        Step.lambda_("step2", my_lambda_fn),
    ],
)

# Execute
runner = WorkflowRunner()
result = runner.execute(my_workflow, params={"key": "value"})

# Check result
if result.status == "completed":
    print("Success!")
else:
    print(f"Failed at {result.error_step}: {result.error}")
```

---

## WorkflowRunner API

### Constructor

```python
class WorkflowRunner:
    def __init__(
        self,
        db_engine: Engine | None = None,     # For checkpointing and history
        dispatcher: Dispatcher | None = None, # For pipeline execution
        checkpoint_enabled: bool = True,       # Enable checkpointing
        dry_run: bool = False,                 # Run without side effects
    ):
        ...
```

### Execute Method

```python
def execute(
    self,
    workflow: Workflow,
    *,
    params: dict[str, Any] | None = None,      # Initial parameters
    partition: dict[str, Any] | None = None,   # Partition for tracking
    context: WorkflowContext | None = None,    # Resume from context
    start_from: str | None = None,             # Start from specific step
    run_id: str | None = None,                 # Resume specific run
) -> WorkflowResult:
    """
    Execute a workflow.
    
    Returns WorkflowResult with:
    - status: "completed" | "failed" | "stopped"
    - context: Final WorkflowContext
    - completed_steps: List of completed step names
    - total_steps: Total step count
    - error_step: Step that failed (if any)
    - error: Error message (if any)
    - run_id: Unique run identifier
    """
```

### Resume Method

```python
def resume(
    self,
    run_id: str,
    *,
    params_override: dict[str, Any] | None = None,
) -> WorkflowResult:
    """
    Resume a failed or stopped workflow run.
    
    Loads checkpoint and continues from last successful step.
    """
```

---

## Execution Model

### Step Execution Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WorkflowRunner.execute()                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   1. Create/Load WorkflowContext                                     │
│      └─ Initialize with params, partition                            │
│                                                                      │
│   2. For each step in workflow.steps:                                │
│      ┌──────────────────────────────────────────────────────────┐   │
│      │ a. Check if step should run (not skipped by choice)      │   │
│      │ b. Execute step based on type:                            │   │
│      │    - Lambda: call function with (context, config)         │   │
│      │    - Pipeline: dispatch via Dispatcher                    │   │
│      │    - Choice: evaluate condition, set next step            │   │
│      │    - Map: fan out to iterator workflow                    │   │
│      │    - Wait: pause execution                                │   │
│      │ c. Process StepResult:                                    │   │
│      │    - Merge context_updates into context                   │   │
│      │    - Store step output                                    │   │
│      │    - Record quality metrics                               │   │
│      │ d. Save checkpoint (if enabled)                           │   │
│      │ e. Handle errors per ErrorPolicy                          │   │
│      └──────────────────────────────────────────────────────────┘   │
│                                                                      │
│   3. Return WorkflowResult                                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Context Mutation

After each step, context is updated:

```python
# Inside runner
def _execute_step(self, step: Step, context: WorkflowContext) -> WorkflowContext:
    # Execute step
    result: StepResult = self._call_step(step, context)
    
    if result.success:
        # Store output under step name
        new_context = context.with_output(step.name, result.output)
        
        # Merge context updates into params
        if result.context_updates:
            new_context = new_context.with_params(result.context_updates)
        
        # Store quality metrics
        if result.quality:
            new_context = new_context.with_quality(step.name, result.quality)
        
        return new_context
    else:
        # Handle based on error policy
        return self._handle_error(step, context, result)
```

---

## Error Handling

### Error Policies

```python
from spine.orchestration import ErrorPolicy

Step.lambda_("my_step", my_fn, on_error=ErrorPolicy.STOP)      # Default: stop workflow
Step.lambda_("my_step", my_fn, on_error=ErrorPolicy.CONTINUE)  # Skip and continue
Step.lambda_("my_step", my_fn, on_error=ErrorPolicy.RETRY)     # Retry with backoff
```

### Retry Configuration

```python
Step.lambda_(
    "my_step", 
    my_fn,
    on_error=ErrorPolicy.RETRY,
    retry=RetryPolicy(
        max_attempts=3,
        backoff="exponential",   # or "linear", "constant"
        initial_delay=1.0,       # seconds
        max_delay=60.0,          # seconds
        retryable_errors=["TRANSIENT", "TIMEOUT"],
    ),
)
```

### Error Categories

```python
class ErrorCategory:
    TRANSIENT = "TRANSIENT"      # Network timeout, temporary failure
    DATA_QUALITY = "DATA_QUALITY" # Data validation failure
    CONFIGURATION = "CONFIGURATION"  # Missing config
    DEPENDENCY = "DEPENDENCY"    # External service failure
    INTERNAL = "INTERNAL"        # Bug in code
    TIMEOUT = "TIMEOUT"          # Step timeout exceeded
```

---

## Checkpointing

### How Checkpoints Work

After each successful step, runner saves:

```python
{
    "run_id": "uuid",
    "workflow_name": "my.workflow",
    "checkpoint_step": "step2",
    "context_snapshot": { ... },  # Serialized WorkflowContext
    "created_at": "2026-01-10T12:00:00Z",
}
```

### Resume from Checkpoint

```python
runner = WorkflowRunner()

# Original run fails
result = runner.execute(my_workflow, params={"key": "value"})
# result.status == "failed"
# result.error_step == "step3"
# result.run_id == "abc-123"

# Fix the issue, then resume
resumed_result = runner.resume("abc-123")
# Continues from step3 with saved context
```

### Checkpoint Storage

Checkpoints are stored in `core_workflow_checkpoints` table:

```sql
SELECT * FROM core_workflow_checkpoints WHERE run_id = 'abc-123';

-- Returns:
-- run_id | step_name | context_snapshot | created_at
-- abc-123 | step1 | {...} | 2026-01-10 12:00:00
-- abc-123 | step2 | {...} | 2026-01-10 12:00:01
```

---

## Dry Run Mode

Run workflow without side effects:

```python
runner = WorkflowRunner(dry_run=True)

result = runner.execute(my_workflow, params={...})

# In dry run mode:
# - Lambda steps execute normally (should be idempotent)
# - Pipeline steps return mock success
# - No database writes
# - No external API calls (if using dry_run flag in context)

# Check what would happen
for step_name in result.completed_steps:
    output = result.context.get_output(step_name)
    print(f"{step_name}: {output}")
```

Lambda steps can check dry run mode:

```python
def my_lambda(ctx: WorkflowContext, config: dict) -> StepResult:
    if ctx.params.get("__dry_run__"):
        return StepResult.ok(
            output={"dry_run": True, "would_do": "insert 100 records"}
        )
    
    # Actual implementation
    ...
```

---

## Observability

### Execution Events

The runner emits events for observability:

```python
# Events stored in core_workflow_events (if enabled)
{
    "run_id": "abc-123",
    "event_type": "step_started",
    "step_name": "ingest",
    "timestamp": "2026-01-10T12:00:00Z",
    "metadata": {}
}

{
    "run_id": "abc-123", 
    "event_type": "step_completed",
    "step_name": "ingest",
    "timestamp": "2026-01-10T12:00:05Z",
    "metadata": {
        "duration_ms": 5000,
        "output_size": 1024
    }
}
```

### Metrics

```python
# Access run metrics
result = runner.execute(...)

print(f"Total duration: {result.duration_ms}ms")
print(f"Steps completed: {result.completed_steps}")

# Per-step durations
for step in result.step_metrics:
    print(f"  {step.name}: {step.duration_ms}ms")
```

---

## Advanced Usage

### Custom Step Executor

```python
class CustomRunner(WorkflowRunner):
    def _execute_lambda(
        self, 
        step: LambdaStep, 
        context: WorkflowContext
    ) -> StepResult:
        # Add custom behavior
        with self.tracer.start_span(f"step:{step.name}"):
            result = super()._execute_lambda(step, context)
            self.metrics.record_step(step.name, result)
            return result
```

### Workflow Middleware

```python
@runner.middleware
def logging_middleware(step, context, next_fn):
    """Log all step executions."""
    logger.info(f"Starting step: {step.name}")
    start = time.time()
    
    result = next_fn(step, context)
    
    logger.info(f"Completed step: {step.name} in {time.time() - start:.2f}s")
    return result

@runner.middleware
def timeout_middleware(step, context, next_fn):
    """Enforce step timeout."""
    timeout = step.config.get("timeout", 300)
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(next_fn, step, context)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            return StepResult.fail(
                error=f"Step {step.name} timed out after {timeout}s",
                category="TIMEOUT"
            )
```

### Parallel Step Execution

For independent steps:

```python
# Map step for parallel execution
Step.map("process_all",
    items=["item1", "item2", "item3"],
    item_param="current_item",
    iterator=per_item_workflow,
    max_concurrency=10,  # Process 10 at a time
)
```

---

## Configuration Options

```python
from spine.orchestration import WorkflowRunnerConfig

config = WorkflowRunnerConfig(
    # Checkpointing
    checkpoint_enabled=True,
    checkpoint_every_step=True,
    checkpoint_storage="database",  # or "file", "redis"
    
    # Timeouts
    default_step_timeout=300,  # seconds
    workflow_timeout=3600,     # seconds
    
    # Retries
    default_retry_policy=RetryPolicy(max_attempts=3),
    
    # Observability
    emit_events=True,
    trace_enabled=True,
    
    # Execution
    max_concurrent_steps=10,
    dry_run=False,
)

runner = WorkflowRunner(config=config)
```
