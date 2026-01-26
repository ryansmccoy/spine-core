# Migration Guide: v1 to v2

> **Document**: Migrate from PipelineGroups to Workflows

## Overview

This guide covers migrating from Orchestration v1 (PipelineGroups) to Orchestration v2 (Workflows). The migration is **non-breaking** - v1 continues to work, and you can migrate incrementally.

---

## Migration Philosophy

### Coexistence, Not Replacement

```
┌─────────────────────────────────────────────────────────────────────┐
│                        spine.orchestration                          │
├───────────────────────────────┬─────────────────────────────────────┤
│         v1 (Stable)           │            v2 (New)                 │
│                               │                                     │
│  PipelineGroup                │  Workflow                           │
│  PipelineStep                 │  Step (lambda, pipeline, choice...) │
│  GroupRunner                  │  WorkflowRunner                     │
│                               │  WorkflowContext                    │
│                               │                                     │
│  ✅ Still works               │  ✅ New features                    │
│  ✅ Not deprecated            │  ✅ Context passing                 │
│                               │  ✅ Lambda steps                    │
│                               │  ✅ Quality gates                   │
└───────────────────────────────┴─────────────────────────────────────┘
```

---

## Quick Migration

### Before (v1)

```python
from spine.orchestration import PipelineGroup, PipelineStep

group = PipelineGroup(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
        PipelineStep("normalize", "finra.otc_transparency.normalize_week",
                     depends_on=["ingest"]),
        PipelineStep("aggregate", "finra.otc_transparency.aggregate_week",
                     depends_on=["normalize"]),
    ],
)

# Execute
from spine.orchestration import GroupRunner
runner = GroupRunner()
result = runner.run(group, params={"tier": "NMS_TIER_1"})
```

### After (v2)

```python
from spine.orchestration import Workflow, Step

workflow = Workflow(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
    ],
)

# Execute
from spine.orchestration import WorkflowRunner
runner = WorkflowRunner()
result = runner.execute(workflow, params={"tier": "NMS_TIER_1"})
```

---

## Step-by-Step Migration

### Step 1: Update Imports

```python
# Before
from spine.orchestration import PipelineGroup, PipelineStep, GroupRunner

# After
from spine.orchestration import Workflow, Step, WorkflowRunner
```

### Step 2: Convert PipelineGroup to Workflow

```python
# Before
group = PipelineGroup(
    name="my.group",
    domain="my_domain",
    description="My pipeline group",
    steps=[...],
)

# After
workflow = Workflow(
    name="my.group",  # Can keep same name
    domain="my_domain",
    description="My pipeline group (migrated to v2)",
    steps=[...],
)
```

### Step 3: Convert PipelineSteps

```python
# Before
PipelineStep("step_name", "pipeline.registry.key")

# After
Step.pipeline("step_name", "pipeline.registry.key")
```

### Step 4: Handle Dependencies

In v1, you specify `depends_on`. In v2, steps run sequentially by default.

```python
# Before (v1) - explicit dependencies
steps=[
    PipelineStep("ingest", "my.ingest"),
    PipelineStep("transform", "my.transform", depends_on=["ingest"]),
    PipelineStep("load", "my.load", depends_on=["transform"]),
]

# After (v2) - sequential by default
steps=[
    Step.pipeline("ingest", "my.ingest"),
    Step.pipeline("transform", "my.transform"),  # Runs after ingest
    Step.pipeline("load", "my.load"),            # Runs after transform
]
```

For parallel execution in v2, use Map:

```python
# v2 parallel execution
Step.map("parallel_steps",
    items=["step1", "step2", "step3"],
    item_param="current_step",
    iterator=per_step_workflow,
    max_concurrency=3,
)
```

### Step 5: Update Runner Usage

```python
# Before
runner = GroupRunner()
result = runner.run(group, params={...})

if result.success:
    print("Done")
else:
    print(f"Failed: {result.error}")

# After
runner = WorkflowRunner()
result = runner.execute(workflow, params={...})

if result.status == "completed":
    print("Done")
else:
    print(f"Failed at {result.error_step}: {result.error}")
```

---

## Feature Migration

### Adding Validation (New in v2)

v1 required a separate pipeline. v2 uses lambda steps:

```python
# Before (v1) - needed separate pipeline
steps=[
    PipelineStep("ingest", "my.ingest"),
    PipelineStep("validate", "my.validate_pipeline"),  # Whole pipeline just for validation
    PipelineStep("transform", "my.transform"),
]

# After (v2) - inline lambda
def validate_step(ctx: WorkflowContext, config: dict) -> StepResult:
    ingest_output = ctx.get_output("ingest")
    if ingest_output["record_count"] < 100:
        return StepResult.fail("Too few records")
    return StepResult.ok(output={"validated": True})

steps=[
    Step.pipeline("ingest", "my.ingest"),
    Step.lambda_("validate", validate_step),  # Inline validation
    Step.pipeline("transform", "my.transform"),
]
```

### Adding Conditional Logic (New in v2)

```python
# v2 only - conditional branching
steps=[
    Step.pipeline("fetch", "my.fetch"),
    Step.lambda_("check_condition", check_fn),
    Step.choice("route",
        condition=lambda ctx: ctx.params.get("should_process"),
        then_step="process",
        else_step="skip",
    ),
    Step.pipeline("process", "my.process"),
    Step.lambda_("skip", lambda ctx, cfg: StepResult.ok(output={"skipped": True})),
]
```

### Adding Context Passing (New in v2)

```python
# v2 only - output from one step available in next
def step_a(ctx: WorkflowContext, config: dict) -> StepResult:
    return StepResult.ok(
        output={"value": 42},
        context_updates={"computed_value": 42},
    )

def step_b(ctx: WorkflowContext, config: dict) -> StepResult:
    # Access output from step_a
    value = ctx.get_output("step_a", "value")
    
    # Or access via params
    computed = ctx.params["computed_value"]
    
    return StepResult.ok(output={"used_value": value})
```

---

## Migration Patterns

### Pattern 1: Gradual Migration

Keep v1 groups running, migrate one at a time:

```python
# Old groups still work
legacy_group = PipelineGroup(...)
legacy_runner = GroupRunner()
legacy_runner.run(legacy_group)

# New workflows alongside
new_workflow = Workflow(...)
new_runner = WorkflowRunner()
new_runner.execute(new_workflow)
```

### Pattern 2: Wrapper Migration

Wrap v1 group in v2 workflow:

```python
# Wrap entire v1 group as single step
def run_legacy_group(ctx: WorkflowContext, config: dict) -> StepResult:
    group = get_legacy_group(config["group_name"])
    runner = GroupRunner()
    result = runner.run(group, params=ctx.params)
    
    return StepResult.ok(output={"legacy_result": result})

workflow = Workflow(
    name="migration.wrapper",
    steps=[
        Step.lambda_("pre_validate", pre_validate_fn),
        Step.lambda_("run_legacy", run_legacy_group,
            config={"group_name": "old.group"}),
        Step.lambda_("post_validate", post_validate_fn),
    ],
)
```

### Pattern 3: Pipeline Adapter

Use existing registered pipelines directly:

```python
# Your existing pipelines continue to work
# Just reference them in Step.pipeline

workflow = Workflow(
    name="using.existing.pipelines",
    steps=[
        # These call the same pipelines as before
        Step.pipeline("step1", "existing.pipeline.one"),
        Step.pipeline("step2", "existing.pipeline.two"),
        
        # But now you can add new capabilities
        Step.lambda_("validate", validate_fn),
    ],
)
```

---

## Code Comparison

### Complete Before/After Example

**Before (v1):**

```python
from spine.orchestration import PipelineGroup, PipelineStep, GroupRunner

# Define group
finra_refresh = PipelineGroup(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
        PipelineStep("normalize", "finra.otc_transparency.normalize_week",
                     depends_on=["ingest"]),
        PipelineStep("aggregate", "finra.otc_transparency.aggregate_week",
                     depends_on=["normalize"]),
        PipelineStep("rolling", "finra.otc_transparency.compute_rolling",
                     depends_on=["aggregate"]),
    ],
)

# Run
def run_weekly_refresh(tier: str, week_ending: str):
    runner = GroupRunner()
    result = runner.run(
        finra_refresh,
        params={
            "tier": tier,
            "week_ending": week_ending,
        },
    )
    
    if not result.success:
        print(f"Failed: {result.error}")
        return None
    
    return result.outputs
```

**After (v2):**

```python
from spine.orchestration import (
    Workflow,
    Step,
    WorkflowRunner,
    WorkflowContext,
    StepResult,
    QualityMetrics,
    ErrorPolicy,
)


def validate_ingest(ctx: WorkflowContext, config: dict) -> StepResult:
    """Validate ingestion results."""
    result = ctx.get_output("ingest", {})
    count = result.get("record_count", 0)
    
    if count < 100:
        return StepResult.fail(
            error=f"Too few records: {count}",
            category="DATA_QUALITY",
        )
    
    return StepResult.ok(
        output={"validated": True, "count": count},
        quality=QualityMetrics(record_count=count, passed=True),
    )


def check_rolling_prereqs(ctx: WorkflowContext, config: dict) -> StepResult:
    """Check if we have enough history for rolling."""
    # Would check database for history
    has_history = True
    
    return StepResult.ok(
        output={"has_history": has_history},
        context_updates={"skip_rolling": not has_history},
    )


def send_notification(ctx: WorkflowContext, config: dict) -> StepResult:
    """Send completion notification."""
    tier = ctx.params["tier"]
    week = ctx.params["week_ending"]
    
    # Send notification (implementation)
    
    return StepResult.ok(output={"notified": True})


# Define workflow
finra_refresh = Workflow(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    description="Weekly FINRA OTC refresh with validation",
    steps=[
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        Step.lambda_("validate_ingest", validate_ingest),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
        Step.lambda_("check_rolling", check_rolling_prereqs),
        Step.choice("should_roll",
            condition=lambda ctx: not ctx.params.get("skip_rolling"),
            then_step="rolling",
            else_step="notify",
        ),
        Step.pipeline("rolling", "finra.otc_transparency.compute_rolling"),
        Step.lambda_("notify", send_notification,
            on_error=ErrorPolicy.CONTINUE),
    ],
)


# Run
def run_weekly_refresh(tier: str, week_ending: str):
    runner = WorkflowRunner()
    result = runner.execute(
        finra_refresh,
        params={
            "tier": tier,
            "week_ending": week_ending,
        },
        partition={"tier": tier, "week_ending": week_ending},
    )
    
    if result.status == "failed":
        print(f"Failed at {result.error_step}: {result.error}")
        # Can resume later
        print(f"Run ID: {result.run_id}")
        return None
    
    # Access rich output
    validate_result = result.context.get_output("validate_ingest")
    print(f"Processed {validate_result['count']} records")
    
    return result.context
```

---

## Checklist

### Pre-Migration
- [ ] Identify all PipelineGroups to migrate
- [ ] Review existing pipeline dependencies
- [ ] Identify validation/conditional logic to add

### Per-Group Migration
- [ ] Create new Workflow definition
- [ ] Convert PipelineSteps to Step.pipeline()
- [ ] Add lambda steps for validation
- [ ] Add choice steps for conditional logic
- [ ] Update runner code
- [ ] Test with same parameters

### Post-Migration
- [ ] Verify outputs match
- [ ] Set up checkpointing
- [ ] Configure quality thresholds
- [ ] Update documentation

---

## FAQ

### Can I use both v1 and v2?
Yes! They coexist. Migrate at your own pace.

### Will v1 be deprecated?
No plans currently. v1 is simpler for basic use cases.

### Can v2 call v1 pipelines?
Yes! `Step.pipeline()` calls the same registered pipelines.

### What about existing schedules?
Update the runner code but keep the same schedule infrastructure.

### How do I handle failures during migration?
v2 has checkpointing - failed runs can be resumed after fixing issues.
