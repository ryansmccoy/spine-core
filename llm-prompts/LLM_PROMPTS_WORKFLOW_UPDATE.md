# LLM Prompts Update Plan: Workflow v2 System

**Date**: January 2025  
**Purpose**: Document what needs to change in each llm-prompts file to reflect the new Workflow orchestration system.

---

## Executive Summary

The spine-core package now includes a **Workflow v2 system** (`spine.orchestration`) that provides context-aware orchestration with lambda steps, quality metrics, and data passing between steps. The existing LLM prompts were written before this system existed and need updates.

### Key Concepts to Add

1. **Workflow vs Pipeline distinction**:
   - **Pipeline**: Single operation unit that does actual work (fetch, transform, calculate)
   - **Workflow**: Orchestrates multiple pipelines with validation steps between them

2. **Step Types**:
   - `Step.pipeline("name", "registered.pipeline")` - Runs a registered pipeline
   - `Step.lambda_("name", fn)` - Lightweight validation/routing (NOT business logic)
   - `Step.choice("name", condition=fn, then_step="x", else_step="y")` - Branching

3. **Critical Anti-Pattern**:
   - ❌ WRONG: Copying pipeline logic into workflow lambdas
   - ✅ RIGHT: Workflows reference registered pipelines via `Step.pipeline()`

---

## Files Requiring Updates

### 1. CONTEXT.md [HIGH PRIORITY]

**Current State**: Documents repository structure and layers. No mention of Workflow.

**Changes Needed**:
- [ ] Add "Orchestration Layer" section after "Architecture Layers"
- [ ] Update architecture diagram to show Workflow
- [ ] Add spine.orchestration to package listing
- [ ] Document core_manifest for workflow execution tracking

**Add Section**:
```markdown
## Orchestration (Workflow v2)

For multi-step operations, use the Workflow system:

Location: `packages/spine-core/src/spine/orchestration/`

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow: "finra.weekly_refresh"                            │
│    Step.pipeline("ingest", "finra.otc.ingest_week")          │
│    Step.lambda_("validate", check_record_count)              │
│    Step.pipeline("normalize", "finra.otc.normalize_week")    │
└─────────────────────────────────────────────────────────────┘
                              ↓ looks up
┌─────────────────────────────────────────────────────────────┐
│  Spine Registry: Pipeline classes by name                    │
└─────────────────────────────────────────────────────────────┘
                              ↓ executes
┌─────────────────────────────────────────────────────────────┐
│  Pipelines: Do the actual work                               │
│  (Sources → Transform → Write to DB)                         │
└─────────────────────────────────────────────────────────────┘
```

Lambda steps should be LIGHTWEIGHT:
- ✅ Check record counts
- ✅ Validate data passed previous step
- ✅ Route to different paths
- ❌ NOT business logic (that goes in pipelines)
```

---

### 2. MASTER_PROMPT.md [HIGH PRIORITY]

**Current State**: Implementation rules for pipelines only. No workflow guidance.

**Changes Needed**:
- [ ] Add "Orchestration Tier" section after "Layering"
- [ ] Add workflow anti-patterns to ANTI-PATTERNS section
- [ ] Update REQUIRED TESTS section for workflow tests
- [ ] Add workflow to Definition of Done

**Add to Implementation Rules**:
```markdown
8. **Orchestration**:
   - Single operation? Use Pipeline only
   - Multiple steps with validation? Use Workflow + Pipeline
   - Workflow lambdas: LIGHTWEIGHT validation only
   - Never copy pipeline logic into lambdas
   - Reference pipelines via: Step.pipeline("name", "registered.pipeline")
```

**Add to Anti-Patterns**:
```markdown
- ❌ Copying pipeline logic into workflow lambdas
- ❌ Using lambda steps for business logic
- ❌ Workflows without registered pipelines
```

---

### 3. A_DATASOURCE.md [MEDIUM PRIORITY]

**Current State**: Shows Pipeline → Source pattern. No workflow integration.

**Changes Needed**:
- [ ] Add section: "Workflow Integration for Multi-Source Ingestion"
- [ ] Show pattern for orchestrating multiple source pipelines
- [ ] Document quality gates between source ingestion steps

**Add Section**:
```markdown
### 4. Workflow Integration (Multi-Step Ingestion)

When ingesting from multiple sources that depend on each other:

```python
from spine.orchestration import Workflow, Step

def check_base_data(ctx, config):
    """Lambda: Validate base data before enrichment."""
    rows = ctx.get_output("ingest_base", "rows", 0)
    if rows < 100:
        return StepResult.fail("Insufficient base data")
    return StepResult.ok()

workflow = Workflow(
    name="{domain}.multi_source_refresh",
    steps=[
        Step.pipeline("ingest_base", "{domain}.ingest_base"),
        Step.lambda_("validate_base", check_base_data),
        Step.pipeline("ingest_enrichment", "{domain}.ingest_enrichment"),
        Step.pipeline("merge", "{domain}.merge_sources"),
    ],
)
```

Each Step.pipeline() references a REGISTERED pipeline - the workflow does NOT contain ingestion logic.
```

---

### 4. B_CALCULATION.md [MEDIUM PRIORITY]

**Current State**: Shows Pipeline pattern for calculations. No workflow orchestration.

**Changes Needed**:
- [ ] Add section: "Workflow Integration for Calculation Chains"
- [ ] Show quality gates between calculation steps
- [ ] Document data passing for calculation pipelines

**Add Section**:
```markdown
### 4. Workflow Integration (Multi-Calculation Chains)

When calculations depend on each other:

```python
from spine.orchestration import Workflow, Step

def validate_aggregates(ctx, config):
    """Lambda: Check aggregation quality before rolling calcs."""
    metrics = ctx.get_output("aggregate", "metrics", {})
    if metrics.get("null_rate", 0) > 0.05:
        return StepResult.fail("Too many null values in aggregates")
    return StepResult.ok()

workflow = Workflow(
    name="{domain}.calculation_chain",
    steps=[
        Step.pipeline("aggregate", "{domain}.compute_aggregates"),
        Step.lambda_("validate", validate_aggregates),
        Step.pipeline("rolling", "{domain}.compute_rolling_avg"),
        Step.pipeline("score", "{domain}.compute_scores"),
    ],
)
```

Lambda steps validate BETWEEN calculations - they don't compute anything.
```

---

### 5. C_OPERATIONAL.md [MEDIUM PRIORITY]

**Current State**: Focuses on schedulers, quality gates. Uses pipeline patterns.

**Changes Needed**:
- [ ] Add section: "Workflow for Scheduled Operations"
- [ ] Show how workflows replace PipelineGroup for multi-step scheduling
- [ ] Document workflow observability (step metrics)

**Add Section**:
```markdown
### 5. Workflow-Based Scheduling

For multi-step scheduled operations, use Workflow instead of PipelineGroup:

```python
from spine.orchestration import Workflow, WorkflowRunner, Step

def validate_readiness(ctx, config):
    """Lambda: Check data readiness before processing."""
    # Query core_data_readiness table
    return StepResult.ok() if ready else StepResult.fail("Data not ready")

scheduled_workflow = Workflow(
    name="daily.market_data.refresh",
    steps=[
        Step.lambda_("check_readiness", validate_readiness),
        Step.pipeline("fetch", "market_data.fetch_prices"),
        Step.pipeline("validate", "market_data.quality_check"),
        Step.pipeline("aggregate", "market_data.daily_aggregates"),
    ],
)

# Run via scheduler
runner = WorkflowRunner()
result = runner.execute(scheduled_workflow, params={"date": date_str})

# Track in core_manifest
manifest.advance_to({"date": date_str}, "COMPLETED", 
    execution_id=result.run_id)
```

Workflow provides:
- Step-level metrics (duration, status per step)
- Automatic failure handling per step
- Context passing between steps
```

---

### 6. E_REVIEW.md [LOW PRIORITY]

**Current State**: Review checklist for PRs. No workflow checks.

**Changes Needed**:
- [ ] Add "Workflow Compliance" section to audit checklist

**Add Section**:
```markdown
### 11. Workflow Compliance (if applicable)

| Check | Status | Notes |
|-------|--------|-------|
| Workflows reference registered pipelines? | ⬜ | |
| Lambda steps are lightweight (no business logic)? | ⬜ | |
| No pipeline logic duplicated in lambdas? | ⬜ | |
| Context passing used correctly? | ⬜ | |
| Workflow tracked in core_manifest? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A
```

---

### 7. ERROR_MODEL_AND_ANOMALIES.md [LOW PRIORITY]

**Current State**: Documents error model. No workflow-specific guidance.

**Changes Needed**:
- [ ] Add section: "Workflow Step Failures"
- [ ] Document StepResult.fail() vs exceptions

**Add Section**:
```markdown
## Workflow Step Failures

Workflow steps can fail gracefully:

```python
from spine.orchestration import StepResult

def my_validation_step(ctx, config):
    if some_check_fails:
        # Graceful failure - workflow records this
        return StepResult.fail("Check failed", error_category="QUALITY_GATE")
    return StepResult.ok(output={"validated": True})
```

StepResult.fail() vs Exceptions:
- `StepResult.fail()`: Expected failure (quality gate, validation)
- Exception: Unexpected failure (bug, infrastructure issue)
```

---

### 8. NEW: F_WORKFLOW.md [CREATE NEW FILE]

**Purpose**: Dedicated prompt for implementing workflows.

**Contents**:
- When to use Workflow vs Pipeline
- Step type reference (pipeline, lambda, choice)
- Anti-patterns (lambda logic)
- Examples
- Definition of Done

See full content in the file creation below.

---

## Template File Updates

### llm-prompts/templates/pipeline.py [LOW PRIORITY]

**Current State**: Pipeline template. OK as-is.

**Changes Needed**:
- [ ] Add comment explaining pipeline can be referenced by workflows

---

### NEW: llm-prompts/templates/workflow.py [CREATE NEW FILE]

**Purpose**: Template for creating workflows.

---

## Priority Order

1. **HIGH**: CONTEXT.md, MASTER_PROMPT.md (foundations)
2. **MEDIUM**: A_DATASOURCE.md, B_CALCULATION.md, C_OPERATIONAL.md
3. **LOW**: E_REVIEW.md, ERROR_MODEL_AND_ANOMALIES.md, templates
4. **CREATE**: F_WORKFLOW.md (new prompt), workflow.py (new template)

---

## Core Tables for Workflow Tracking

Workflows should use these existing tables:

### core_manifest
Track workflow execution:
```python
manifest.advance_to(
    key={"workflow": "daily.refresh", "date": "2025-01-09"},
    stage="COMPLETED",
    execution_id=result.run_id,
    metrics={"steps_completed": 4, "duration_seconds": 120}
)
```

### core_anomalies
Record workflow failures:
```python
INSERT INTO core_anomalies (
    anomaly_id, domain, stage, partition_key,
    severity, category, message, detected_at, metadata
) VALUES (
    ?, 'workflow', 'daily.refresh', '2025-01-09',
    'ERROR', 'STEP_FAILURE', 'Step validate failed: Too few records',
    ?, '{"step": "validate", "workflow_run_id": "..."}'
)
```

---

## Implementation Checklist

- [x] Create this plan document ✅
- [x] Update CONTEXT.md ✅
- [x] Update MASTER_PROMPT.md ✅
- [x] Create F_WORKFLOW.md ✅
- [x] Update A_DATASOURCE.md ✅
- [x] Update B_CALCULATION.md ✅
- [x] Update C_OPERATIONAL.md ✅
- [x] Update E_REVIEW.md ✅
- [ ] Update ERROR_MODEL_AND_ANOMALIES.md (low priority)
- [ ] Create workflow.py template (low priority)
- [x] Create pattern example with DB tracking ✅ (04_workflow_with_tracking.py)
