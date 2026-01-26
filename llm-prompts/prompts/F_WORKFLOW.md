# Prompt F: Implement Workflow

**Use this prompt when:** Orchestrating multiple pipelines with validation steps, quality gates, or data passing between steps.

---

## Copy-Paste Prompt

```
I need to implement a workflow for Market Spine.

CONTEXT:
- Read llm-prompts/CONTEXT.md first for repository structure and workflow overview
- Workflows ORCHESTRATE pipelines - they don't replace them
- Pipelines do the actual work; workflows coordinate the sequence
- Lambda steps are for LIGHTWEIGHT validation only (no business logic)

WORKFLOW DETAILS:
- Name: {workflow_name}
- Domain: {domain_name}
- Purpose: {What multi-step operation does this coordinate?}
- Steps: {List the operations in sequence}
- Quality Gates: {What validation between steps?}

---

ARCHITECTURE RULE: Separation of Concerns

┌─────────────────────────────────────────────────────────────┐
│  Workflow: Orchestrates pipelines, passes context           │
│    Step.pipeline("name", "registered.pipeline")             │
│    Step.lambda_("validate", lightweight_check)              │
│                                                              │
│    ❌ NO business logic here                                 │
│    ❌ NO data fetching here                                  │
│    ❌ NO database writes here                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Pipelines: Do the actual work                               │
│    @register_pipeline("domain.ingest")                       │
│    class IngestPipeline(Pipeline):                          │
│        def run(self):                                        │
│            source = create_source()                          │
│            data = source.fetch()                             │
│            self._write_to_db(data)                           │
│                                                              │
│    ✅ ALL business logic here                                │
│    ✅ ALL data fetching here                                 │
│    ✅ ALL database writes here                               │
└─────────────────────────────────────────────────────────────┘

---

STEP TYPES REFERENCE:

### 1. Pipeline Step (Basic tier)
References a registered pipeline by name:
```python
Step.pipeline("ingest", "finra.otc_transparency.ingest_week")
#             └─name─┘   └───registered pipeline name─────────┘
```

### 2. Lambda Step (Basic tier)
Lightweight validation/routing ONLY:
```python
def check_record_count(ctx, config):
    """Lambda: Validate previous step output."""
    rows = ctx.get_output("ingest", "row_count", 0)
    if rows < 100:
        return StepResult.fail("Too few records", "QUALITY_GATE")
    return StepResult.ok(output={"validated": True})

Step.lambda_("validate", check_record_count)
```

### 3. Choice Step (Intermediate tier)
Conditional branching:
```python
Step.choice("route",
    condition=lambda ctx: ctx.params.get("full_refresh", False),
    then_step="full_process",
    else_step="incremental_process",
)
```

---

IMPLEMENTATION CHECKLIST:

### 1. Identify Required Pipelines

| Step | Pipeline Name | Exists? | If No, Create |
|------|--------------|---------|---------------|
| {step_1} | {domain}.{operation} | ⬜ Yes / ⬜ No | Use Prompt A or B |
| {step_2} | {domain}.{operation} | ⬜ Yes / ⬜ No | Use Prompt A or B |
| ... | ... | | |

⚠️ **All pipelines must exist and be registered before creating the workflow.**

### 2. Define Lambda Steps (Validation Only)

| Lambda | Purpose | What It Checks |
|--------|---------|----------------|
| {validate_step} | Quality gate | Record count, error rate, etc. |
| ... | | |

**Lambda step rules:**
- ✅ Check `ctx.get_output("prev_step", "field")` values
- ✅ Return `StepResult.ok()` or `StepResult.fail()`
- ✅ Log diagnostic info
- ❌ NO database queries (use pipeline outputs)
- ❌ NO data transformation
- ❌ NO business logic

### 3. Create Workflow
Location: `spine-domains/src/spine/domains/{domain}/workflows.py`

```python
"""
Workflows for {domain} domain.

Workflows orchestrate pipelines - they don't contain business logic.
"""
from spine.orchestration import Workflow, Step, StepResult


def validate_{step_name}(ctx, config):
    """
    Lambda: Validate {previous_step} output before {next_step}.
    
    Checks:
        - {check_1}
        - {check_2}
    
    Returns:
        StepResult.ok() if validation passes
        StepResult.fail() if validation fails (workflow stops)
    """
    # Get output from previous step
    result = ctx.get_output("{previous_step}")
    if not result:
        return StepResult.fail("No output from {previous_step}", "STEP_ERROR")
    
    # Check quality metrics
    row_count = result.get("row_count", 0)
    if row_count < {minimum_threshold}:
        return StepResult.fail(
            f"Too few records: {{row_count}} < {minimum_threshold}",
            "QUALITY_GATE"
        )
    
    return StepResult.ok(output={"validated": True, "row_count": row_count})


{WORKFLOW_NAME} = Workflow(
    name="{domain}.{workflow_name}",
    domain="{domain}",
    description="{Description of what this workflow does}",
    steps=[
        Step.pipeline("ingest", "{domain}.ingest_{data}"),
        Step.lambda_("validate_ingest", validate_{step_name}),
        Step.pipeline("normalize", "{domain}.normalize_{data}"),
        Step.pipeline("aggregate", "{domain}.aggregate_{data}"),
    ],
)
```

### 4. Workflow Runner Integration
Location: CLI command or scheduler

```python
from spine.orchestration import WorkflowRunner
from spine.domains.{domain}.workflows import {WORKFLOW_NAME}

def run_workflow(params: dict):
    """Execute {workflow_name} workflow."""
    runner = WorkflowRunner()
    result = runner.execute({WORKFLOW_NAME}, params=params)
    
    if result.status == WorkflowStatus.COMPLETED:
        log.info("workflow_completed", 
            steps=result.completed_steps,
            duration=result.duration_seconds)
    else:
        log.error("workflow_failed",
            failed_step=result.error_step,
            error=result.error)
    
    return result
```

### 5. Track in core_manifest
```python
from spine.core.manifest import WorkManifest

manifest = WorkManifest(
    conn,
    domain="workflow.{domain}.{workflow_name}",
    stages=["STARTED", "INGESTED", "VALIDATED", "NORMALIZED", "COMPLETED"]
)

# Before execution
manifest.advance_to(partition_key, "STARTED", execution_id=run_id)

# After each step
manifest.advance_to(partition_key, "INGESTED", execution_id=run_id, row_count=N)

# After completion
manifest.advance_to(partition_key, "COMPLETED", execution_id=run_id,
    step_count=len(result.completed_steps),
    duration_seconds=result.duration_seconds)
```

### 6. Record Anomalies on Failure
```python
if result.status == WorkflowStatus.FAILED:
    conn.execute("""
        INSERT INTO core_anomalies (
            anomaly_id, domain, stage, partition_key,
            severity, category, message, detected_at, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()),
        "{domain}",
        f"workflow.{result.error_step}",
        partition_key_str,
        "ERROR",
        "WORKFLOW_FAILURE",
        result.error,
        datetime.utcnow().isoformat(),
        json.dumps({"workflow": "{workflow_name}", "run_id": result.run_id}),
    ))
```

---

ANTI-PATTERNS TO AVOID:

| Anti-Pattern | Why It's Wrong | Correct Approach |
|-------------|----------------|------------------|
| Business logic in lambda | Duplicates pipeline logic | Put logic in registered pipeline |
| Database queries in lambda | Lambdas should be stateless | Use ctx.get_output() from previous step |
| Workflow without pipelines | Workflows orchestrate, not execute | Create pipelines first, then workflow |
| Ignoring StepResult | Loses error context | Always return StepResult.ok() or .fail() |
| Skipping core_manifest | No execution tracking | Track workflow stages in manifest |

---

REQUIRED TESTS:

1. **Unit test each lambda step** (test validation logic)
2. **Integration test full workflow** (all steps execute)
3. **Failure test** (lambda returns StepResult.fail, workflow stops)
4. **Idempotency test** (same params twice produces same result)

---

DEFINITION OF DONE:

- [ ] All required pipelines exist and are registered
- [ ] Lambda steps are LIGHTWEIGHT (no business logic)
- [ ] Workflow defined with proper name/domain
- [ ] WorkflowRunner integration implemented
- [ ] core_manifest tracking implemented
- [ ] core_anomalies recording on failure
- [ ] Unit tests for lambda steps
- [ ] Integration test for full workflow
- [ ] Documentation in domain docs folder
```

---

## When to Use Workflow vs Pipeline

| Scenario | Use |
|----------|-----|
| Single data fetch | Pipeline only |
| Single calculation | Pipeline only |
| Fetch → Validate → Transform | Workflow with pipelines |
| Parallel ingestion from sources | Workflow with pipelines |
| Scheduled multi-step job | Workflow with pipelines |
| Need step-level metrics | Workflow |
| Need quality gates between steps | Workflow with lambda steps |

---

## Complete Example

```python
"""
Example: Weekly OTC data refresh workflow.

Orchestrates: ingest → validate → normalize → aggregate
"""
from spine.orchestration import Workflow, Step, StepResult


def validate_ingest(ctx, config):
    """Lambda: Check ingest quality before normalize."""
    result = ctx.get_output("ingest")
    
    if result.get("row_count", 0) < 1000:
        return StepResult.fail("Too few records ingested", "QUALITY_GATE")
    
    if result.get("error_count", 0) > 10:
        return StepResult.fail("Too many ingest errors", "DATA_QUALITY")
    
    return StepResult.ok(output={
        "validated": True,
        "row_count": result.get("row_count"),
    })


def validate_normalize(ctx, config):
    """Lambda: Check normalize quality before aggregate."""
    result = ctx.get_output("normalize")
    
    null_rate = result.get("null_rate", 0)
    if null_rate > 0.05:
        return StepResult.fail(f"Null rate too high: {null_rate:.1%}", "DATA_QUALITY")
    
    return StepResult.ok()


WEEKLY_REFRESH = Workflow(
    name="finra.otc_transparency.weekly_refresh",
    domain="finra.otc_transparency",
    description="Weekly OTC data refresh: ingest, validate, normalize, aggregate",
    steps=[
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        Step.lambda_("validate_ingest", validate_ingest),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.lambda_("validate_normalize", validate_normalize),
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
    ],
)


# Usage
if __name__ == "__main__":
    from spine.orchestration import WorkflowRunner
    
    runner = WorkflowRunner()
    result = runner.execute(
        WEEKLY_REFRESH,
        params={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"}
    )
    
    print(f"Status: {result.status}")
    print(f"Completed steps: {result.completed_steps}")
    if result.error:
        print(f"Error at {result.error_step}: {result.error}")
```

---

## Related Documents

- [CONTEXT.md](../CONTEXT.md) - Repository structure and workflow overview
- [A_DATASOURCE.md](A_DATASOURCE.md) - Creating source ingestion pipelines
- [B_CALCULATION.md](B_CALCULATION.md) - Creating calculation pipelines
- [C_OPERATIONAL.md](C_OPERATIONAL.md) - Scheduling workflows
- [ANTI_PATTERNS.md](../ANTI_PATTERNS.md) - Common mistakes to avoid
