# WorkflowContext Deep Dive

> **Document**: Complete reference for the WorkflowContext type

## Overview

`WorkflowContext` is the central data structure that flows through every step in a workflow. It carries:
- Run identification and tracing
- User-provided parameters
- Outputs from prior steps
- System metadata
- Checkpoint state for resume

## Type Definition

```python
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone, date
from typing import Any
import uuid


@dataclass
class WorkflowContext:
    """
    Context that flows through workflow execution.
    
    Mutation Model: "Immutable + Merge"
    - Steps return context_updates in StepResult
    - Runner creates NEW context with updates merged
    - Original context is never mutated
    """
    
    # === Identity ===
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str | None = None
    
    # === Timing ===
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # === Data ===
    params: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # === Resumption ===
    checkpoint: "CheckpointState | None" = None
    
    # === Financial Data Specific ===
    partition: "PartitionKey | None" = None
    as_of_date: date | None = None
    capture_id: str | None = None
    idempotency_key: str | None = None
```

## Field Reference

### Identity Fields

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | Unique ID for this workflow run. Auto-generated UUID. |
| `trace_id` | `str` | Distributed tracing ID. Can be set by caller for correlation. |
| `batch_id` | `str \| None` | Groups related runs (e.g., backfill batch). |

### Timing Fields

| Field | Type | Description |
|-------|------|-------------|
| `started_at` | `datetime` | When the workflow started. UTC timezone. |

### Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `params` | `dict` | User-provided parameters. Passed to steps. |
| `step_outputs` | `dict` | Outputs from completed steps. Keyed by step name. |
| `metadata` | `dict` | System metadata (runner version, config, etc.). |

### Resumption Fields

| Field | Type | Description |
|-------|------|-------------|
| `checkpoint` | `CheckpointState \| None` | State for resume-from-failure. |

### Financial Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `partition` | `PartitionKey \| None` | Partition coordinates (date, tier, venue). |
| `as_of_date` | `date \| None` | Business date for the workflow. |
| `capture_id` | `str \| None` | Idempotency key for outputs. |
| `idempotency_key` | `str \| None` | Deduplication key for the run. |

## Mutation Methods

### `with_step_output()`

Add output from a completed step:

```python
def with_step_output(self, step_name: str, output: dict[str, Any]) -> "WorkflowContext":
    """
    Create new context with step output added.
    
    Args:
        step_name: Name of the completed step
        output: The step's output dict
    
    Returns:
        New context with output in step_outputs[step_name]
    """
    new_outputs = {**self.step_outputs, step_name: output}
    return replace(self, step_outputs=new_outputs)
```

**Usage:**
```python
# Runner does this after each step
result = step.execute(context, config)
context = context.with_step_output(step.name, result.output)
```

### `with_updates()`

Merge updates into params:

```python
def with_updates(self, updates: dict[str, Any]) -> "WorkflowContext":
    """
    Create new context with params updates merged.
    
    Args:
        updates: Key-value pairs to merge into params
    
    Returns:
        New context with updates merged
    """
    if not updates:
        return self
    new_params = {**self.params, **updates}
    return replace(self, params=new_params)
```

**Usage:**
```python
# Runner does this after each step
if result.context_updates:
    context = context.with_updates(result.context_updates)
```

### `with_partition()`

Set partition key:

```python
def with_partition(self, **kwargs) -> "WorkflowContext":
    """Set partition coordinates."""
    partition = PartitionKey(**kwargs)
    return replace(self, partition=partition)
```

**Usage:**
```python
context = context.with_partition(
    date="2026-01-10",
    tier="NMS_TIER_1",
    venue="NYSE",
)
```

## Accessor Methods

### `get_output()`

Get output from a prior step:

```python
def get_output(
    self, 
    step_name: str, 
    key: str | None = None, 
    default: Any = None
) -> Any:
    """
    Get output from a prior step.
    
    Args:
        step_name: Name of the step
        key: Optional key within the output
        default: Default if not found
    
    Returns:
        The output, specific key, or default
    """
    step_out = self.step_outputs.get(step_name, {})
    if key is None:
        return step_out if step_out else default
    return step_out.get(key, default)
```

**Usage:**
```python
# In a step handler
def transform_step(ctx: WorkflowContext, config: dict) -> StepResult:
    # Get full output from fetch step
    fetch_result = ctx.get_output("fetch")
    
    # Get specific field with default
    record_count = ctx.get_output("fetch", "record_count", 0)
    
    # Check if prior step succeeded
    validation_passed = ctx.get_output("validate", "passed", False)
```

### `get_param()`

Get a parameter with default:

```python
def get_param(self, key: str, default: Any = None) -> Any:
    """Get a parameter value."""
    return self.params.get(key, default)
```

## Factory Methods

### `new()`

Create a fresh context:

```python
@classmethod
def new(
    cls,
    params: dict[str, Any] | None = None,
    batch_id: str | None = None,
    trace_id: str | None = None,
    partition: dict | None = None,
    as_of_date: date | None = None,
) -> "WorkflowContext":
    """Create a new workflow context."""
    ctx = cls(
        params=params or {},
        batch_id=batch_id,
        trace_id=trace_id or str(uuid.uuid4()),
    )
    if partition:
        ctx = ctx.with_partition(**partition)
    if as_of_date:
        ctx = replace(ctx, as_of_date=as_of_date)
    return ctx
```

**Usage:**
```python
# Basic
ctx = WorkflowContext.new(params={"symbol": "AAPL"})

# With partition
ctx = WorkflowContext.new(
    params={"symbol": "AAPL"},
    partition={"date": "2026-01-10", "tier": "NMS_TIER_1"},
    as_of_date=date(2026, 1, 10),
)

# With tracing
ctx = WorkflowContext.new(
    params={...},
    trace_id="external-trace-123",
    batch_id="backfill-2026-01",
)
```

## Serialization

### `to_dict()`

Serialize for persistence or logging:

```python
def to_dict(self) -> dict[str, Any]:
    """Serialize context to dictionary."""
    return {
        "run_id": self.run_id,
        "trace_id": self.trace_id,
        "batch_id": self.batch_id,
        "started_at": self.started_at.isoformat(),
        "params": self.params,
        "step_outputs": self.step_outputs,
        "metadata": self.metadata,
        "partition": self.partition.to_dict() if self.partition else None,
        "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
        "capture_id": self.capture_id,
    }
```

### `from_dict()`

Deserialize from storage:

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "WorkflowContext":
    """Deserialize from dictionary."""
    return cls(
        run_id=data["run_id"],
        trace_id=data["trace_id"],
        batch_id=data.get("batch_id"),
        started_at=datetime.fromisoformat(data["started_at"]),
        params=data.get("params", {}),
        step_outputs=data.get("step_outputs", {}),
        metadata=data.get("metadata", {}),
        # ... other fields
    )
```

## Best Practices

### 1. Read Prior Outputs, Don't Assume

```python
# ✓ Good: Check if output exists
records = ctx.get_output("fetch", "records", [])
if not records:
    return StepResult.fail("No records from fetch step")

# ✗ Bad: Assume output exists
records = ctx.step_outputs["fetch"]["records"]  # May KeyError
```

### 2. Use context_updates for Cross-Step State

```python
# ✓ Good: Use context_updates
return StepResult.ok(
    output={"valid_count": 100},
    context_updates={"validation_passed": True},  # Available to ALL subsequent steps
)

# ✗ Bad: Only use output
return StepResult.ok(
    output={"valid_count": 100, "validation_passed": True},  # Only in this step's output
)
```

### 3. Include capture_id for Idempotency

```python
# Generate capture_id for outputs
capture_id = f"{ctx.partition.date}|{ctx.partition.tier}|{ctx.run_id}"
context = replace(ctx, capture_id=capture_id)
```

### 4. Use partition for Financial Data

```python
# Set partition at workflow start
ctx = WorkflowContext.new(
    partition={"week_ending": "2026-01-10", "tier": "NMS_TIER_1"},
)

# Steps can read partition
def my_step(ctx: WorkflowContext, config: dict) -> StepResult:
    week = ctx.partition.week_ending  # Type-safe access
    tier = ctx.partition.tier
```

## Thread Safety

`WorkflowContext` is designed to be thread-safe through immutability:

- All mutation methods return NEW instances
- Original context is never modified
- Safe to share across threads (for future parallel execution)

```python
# This is safe
ctx1 = WorkflowContext.new(params={"a": 1})
ctx2 = ctx1.with_updates({"b": 2})  # ctx1 unchanged
ctx3 = ctx1.with_updates({"c": 3})  # ctx1 unchanged

assert ctx1.params == {"a": 1}
assert ctx2.params == {"a": 1, "b": 2}
assert ctx3.params == {"a": 1, "c": 3}
```
