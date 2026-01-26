# Spine-Core Patterns: When to Use What

## Quick Decision Guide

```
┌─────────────────────────────────────────────────────────────────┐
│                    DO I NEED A WORKFLOW?                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Is it a SINGLE operation?                                       │
│    YES → Use Pipeline only                                       │
│    NO  → Continue...                                             │
│                                                                  │
│  Do steps need to pass data to each other?                       │
│    YES → Use Workflow with context                               │
│    NO  → Continue...                                             │
│                                                                  │
│  Do you need validation BETWEEN steps?                           │
│    YES → Use Workflow with lambda steps                          │
│    NO  → Continue...                                             │
│                                                                  │
│  Do you need conditional branching?                              │
│    YES → Use Workflow with choice steps                          │
│    NO  → Pipeline sequence may be enough                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Pattern Summary

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Pipeline Only** | Single operation, no dependencies | Fetch data from API |
| **Pipeline Sequence** | Multiple ops, no validation needed | Fetch → Store |
| **Workflow** | Need validation between steps | Fetch → Validate → Process |
| **Workflow + Choice** | Conditional logic | Route based on data quality |

---

## Examples in This Directory

| File | Pattern | Description |
|------|---------|-------------|
| `01_pipeline_only.py` | Pipeline Only | Single operations |
| `02_pipeline_sequence.py` | Pipeline Sequence | Simple multi-step without workflow |
| `03_workflow_basic.py` | Basic Workflow | Orchestration with validation |
| `04_workflow_with_tracking.py` | Workflow + DB Tracking | core_manifest and core_anomalies usage |
| `05_datasource_template.py` | Datasource | Template for new data sources |
| `06_calculation_template.py` | Calculation | Template for computations |
| `07_aggregation_template.py` | Aggregation | Template for rollups |
| `08_full_domain_example.py` | Full Domain | Complete implementation |

---

## Best Practices

### 1. Keep Pipelines Focused
```python
# ✅ GOOD - One responsibility
class FetchPricePipeline(Pipeline):
    """Fetch price data from Alpha Vantage."""
    
# ✅ GOOD - One responsibility  
class StorePricePipeline(Pipeline):
    """Store price data to database."""

# ❌ BAD - Too many responsibilities
class FetchAndStoreAndValidatePricePipeline(Pipeline):
    """Does everything in one place."""
```

### 2. Lambda Steps = Lightweight Glue
```python
# ✅ GOOD - Validates previous step's output
def validate_record_count(ctx, cfg):
    count = ctx.get_output("fetch")["records"]
    if count < 100:
        return StepResult.fail("Too few records")
    return StepResult.ok()

# ❌ BAD - Does actual work (should be a pipeline!)
def fetch_and_parse(ctx, cfg):
    data = requests.get(url).json()  # This is pipeline work!
    parsed = parse_data(data)         # This too!
    return StepResult.ok(output=parsed)
```

### 3. Use Workflow Context for Data Flow
```python
# Step 1 output
return StepResult.ok(output={"record_count": 1000})

# Step 2 reads it
prev_count = ctx.get_output("step1")["record_count"]
```

### 4. Error Categories Enable Retry Logic
```python
# Transient errors can be retried
return StepResult.fail(
    error="API timeout",
    error_category="TRANSIENT",  # Will retry
)

# Validation errors should not retry
return StepResult.fail(
    error="Invalid data format",
    error_category="VALIDATION",  # Won't retry
)
```

### 5. Quality Metrics for Observability
```python
return StepResult.ok(
    metrics=QualityMetrics(
        records_in=1000,
        records_out=950,
        records_rejected=50,
    )
)
```

---

## Anti-Patterns to Avoid

### ❌ Copying Pipeline Logic into Workflows
```python
# BAD - This should be in a Pipeline class!
Step.lambda_("fetch", lambda ctx, cfg:
    StepResult.ok(output=requests.get(url).json())
)

# GOOD - Reference a registered pipeline
Step.pipeline("fetch", "prices.fetch")
```

### ❌ Overly Complex Lambda Steps
```python
# BAD - Too much logic for a lambda
def complex_transform(ctx, cfg):
    data = ctx.get_output("fetch")
    # 100 lines of transformation logic...
    return StepResult.ok(output=transformed)

# GOOD - Put complex logic in a Pipeline
Step.pipeline("transform", "prices.transform")
```

### ❌ Not Using Quality Metrics
```python
# BAD - No observability
return StepResult.ok(output={"done": True})

# GOOD - Track what happened
return StepResult.ok(
    output={"processed": 1000},
    metrics=QualityMetrics(records_in=1000, records_out=980),
)
```

### ❌ Ignoring Error Categories
```python
# BAD - Generic error
return StepResult.fail(error="Something broke")

# GOOD - Categorized error
return StepResult.fail(
    error="API rate limited",
    error_category="TRANSIENT",  # Retry-able
)
```

---

## Naming Conventions

### Pipelines
```
{domain}.{operation}
{domain}.{entity}_{operation}

Examples:
  prices.fetch
  prices.store
  otc.ingest
  otc.normalize
  calendar.sync_holidays
```

### Workflows
```
{domain}.{process_name}
{domain}.{frequency}_{process_name}

Examples:
  prices.daily_update
  otc.weekly_refresh
  calendar.monthly_sync
```

### Steps
```
{verb}_{noun}  (for pipeline steps)
validate_{what}  (for validation lambdas)
check_{condition}  (for quality gates)
route_{decision}  (for choice steps)

Examples:
  fetch_prices
  validate_record_count
  check_quality_grade
  route_by_tier
```

---

## Testing Patterns

### Pipeline Tests
```python
def test_pipeline_success():
    pipeline = MyPipeline()
    result = pipeline.execute({"param": "value"})
    assert "expected_key" in result

def test_pipeline_error_handling():
    pipeline = MyPipeline()
    with pytest.raises(SomeError):
        pipeline.execute({"bad": "params"})
```

### Workflow Tests
```python
def test_workflow_completes():
    workflow = create_my_workflow()
    runner = WorkflowRunner(dry_run=True)  # Mock pipelines
    result = runner.execute(workflow, params={...})
    assert result.status == WorkflowStatus.COMPLETED

def test_workflow_validates():
    # Test that validation lambda rejects bad data
    ...
```
