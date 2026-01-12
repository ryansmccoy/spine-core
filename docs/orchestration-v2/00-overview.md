# Orchestration v2: Context-First Architecture

> **Status**: Design Phase  
> **Version**: 2.0.0  
> **Last Updated**: 2026-01-11

## Executive Summary

Orchestration v2 introduces a **context-first architecture** that unifies pipeline orchestration and lambda-style step functions into a single, composable system. The core innovation is treating `WorkflowContext` as THE fundamental primitive that flows through every step, enabling:

- **Lambda steps**: Small functions that receive context and return results
- **Pipeline steps**: Existing pipelines wrapped to participate in context flow
- **Mixed workflows**: Combine lambdas and pipelines in one workflow
- **Step-to-step data passing**: Prior outputs available to subsequent steps
- **Branching and routing**: Conditional execution paths based on step results

## Why This Change?

### Current Architecture (v1)

```
PipelineGroup
  └── PipelineStep (references registered pipeline by name)
        └── GroupRunner executes via Dispatcher.submit()
              └── Each pipeline runs independently (no context sharing)
```

**Limitations:**
1. Steps cannot pass data to each other (beyond params)
2. No inline functions (must register every step as a pipeline)
3. No conditional branching (linear or DAG only)
4. Context is implicit (params dict, not structured)

### New Architecture (v2)

```
Workflow
  └── Step (PipelineStep | LambdaStep | ChoiceStep | ...)
        └── WorkflowRunner executes with WorkflowContext
              └── Context flows forward, outputs accumulate
```

**Benefits:**
1. Steps can read prior outputs from context
2. Lambda steps are just functions (no registration required)
3. Choice steps enable conditional routing
4. Context is explicit, typed, immutable-by-convention

## Core Concepts

### WorkflowContext

The context that flows through every step:

```python
@dataclass
class WorkflowContext:
    run_id: str                      # Unique run identifier
    trace_id: str                    # Distributed tracing
    batch_id: str | None             # Batch grouping
    params: dict[str, Any]           # User parameters
    step_outputs: dict[str, Any]     # Prior step results (keyed by step name)
    metadata: dict[str, Any]         # System metadata
    checkpoint: CheckpointState | None  # For resume
```

**Mutation Model: "Immutable + Merge"**
- Steps return `context_updates` in their result
- Runner creates NEW context with updates merged
- Original context is never mutated

### StepResult

Universal result envelope for all step types:

```python
@dataclass
class StepResult:
    success: bool
    output: dict[str, Any]           # Made available via context.step_outputs
    context_updates: dict[str, Any]  # Merged into context.params for next step
    error: str | None = None
    quality: QualityMetrics | None = None
    events: list[dict] = field(default_factory=list)
```

### Step Types

| Type | Description | Use Case |
|------|-------------|----------|
| `LambdaStep` | Inline function | Validation, transformation, notifications |
| `PipelineStep` | Registered pipeline | Heavy lifting (DB writes, API calls) |
| `ChoiceStep` | Conditional branch | Route based on prior results |
| `WaitStep` | Delay or schedule | Rate limiting, scheduling |
| `MapStep` | Fan-out/fan-in | Process collections in parallel |

## Migration Path

### Existing Code Continues to Work

```python
# v1 - Still works
from spine.orchestration import PipelineGroup, GroupRunner

group = PipelineGroup(
    name="my.group",
    steps=[PipelineStep("fetch", "my.fetch_pipeline")],
)
runner = GroupRunner()
result = runner.execute(plan)
```

### New Code Uses Workflows

```python
# v2 - New unified API
from spine.orchestration import Workflow, WorkflowRunner, Step

workflow = Workflow(
    name="my.workflow",
    steps=[
        Step.pipeline("fetch", "my.fetch_pipeline"),
        Step.lambda_("validate", my_validation_func),
        Step.choice("route",
            when=lambda ctx: ctx.get_output("validate", "score") > 0.9,
            then="fast_path",
            otherwise="full_path",
        ),
    ],
)
runner = WorkflowRunner()
result = runner.execute(workflow, params={...})
```

## Document Index

| Document | Description |
|----------|-------------|
| [01-architecture.md](01-architecture.md) | Detailed architecture and design decisions |
| [02-workflow-context.md](02-workflow-context.md) | WorkflowContext deep dive |
| [03-step-types.md](03-step-types.md) | All step types explained |
| [04-workflow-runner.md](04-workflow-runner.md) | WorkflowRunner implementation |
| [05-checkpointing.md](05-checkpointing.md) | Resume from failure |
| [06-quality-gates.md](06-quality-gates.md) | Data quality integration |
| [07-schema-changes.md](07-schema-changes.md) | Database schema updates |
| [08-examples-finra.md](08-examples-finra.md) | FINRA OTC examples |
| [09-examples-market-data.md](09-examples-market-data.md) | Market data examples |
| [10-migration-guide.md](10-migration-guide.md) | Migrating from v1 |

## Quick Start

```python
from spine.orchestration import (
    Workflow,
    WorkflowRunner,
    Step,
    LambdaStepResult,
    WorkflowContext,
)

# Define a lambda step
def validate_data(ctx: WorkflowContext, config: dict) -> LambdaStepResult:
    """Validate data from prior fetch step."""
    records = ctx.get_output("fetch", "records", [])
    
    if not records:
        return LambdaStepResult.fail("No records to validate")
    
    valid_count = sum(1 for r in records if r.get("is_valid"))
    
    return LambdaStepResult.ok(
        output={"valid_count": valid_count, "total": len(records)},
        context_updates={"validation_passed": valid_count > 0},
    )

# Build workflow
workflow = (Workflow.builder("my_etl")
    .add_pipeline("fetch", "my_domain.fetch_data")
    .add_lambda("validate", validate_data)
    .add_pipeline("load", "my_domain.load_data")
    .build())

# Execute
runner = WorkflowRunner()
result = runner.execute(workflow, params={"date": "2026-01-10"})

print(f"Status: {result.status}")
print(f"Steps completed: {result.completed_steps}/{result.total_steps}")
```
