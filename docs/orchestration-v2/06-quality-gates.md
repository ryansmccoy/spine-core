# Quality Gates

> **Document**: Data quality validation integrated into workflows

## Overview

Quality Gates provide:

- **Early failure detection**: Stop bad data before it propagates
- **Metrics tracking**: Record quality metrics for every step
- **Threshold enforcement**: Configurable pass/fail thresholds
- **Observability**: Historical quality trends

---

## QualityMetrics

### Structure

```python
@dataclass
class QualityMetrics:
    """Quality metrics for a step execution."""
    
    # Core counts
    record_count: int = 0           # Total records processed
    valid_count: int = 0            # Records passing validation
    invalid_count: int = 0          # Records failing validation
    null_count: int = 0             # Records with null values
    
    # Rates (computed)
    @property
    def valid_rate(self) -> float:
        return self.valid_count / self.record_count if self.record_count else 0
    
    @property
    def null_rate(self) -> float:
        return self.null_count / self.record_count if self.record_count else 0
    
    # Pass/fail
    passed: bool = True             # Did step meet quality thresholds?
    
    # Custom metrics (domain-specific)
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    
    # Failure details
    failure_reasons: list[str] = field(default_factory=list)
```

### Usage in Step Result

```python
def my_step(ctx: WorkflowContext, config: dict) -> StepResult:
    records = fetch_data()
    
    valid = [r for r in records if is_valid(r)]
    null_records = [r for r in records if has_nulls(r)]
    
    quality = QualityMetrics(
        record_count=len(records),
        valid_count=len(valid),
        invalid_count=len(records) - len(valid),
        null_count=len(null_records),
        passed=len(valid) / len(records) > 0.95,  # 95% threshold
    )
    
    return StepResult.ok(
        output={"processed": len(records)},
        quality=quality,
    )
```

---

## Quality Thresholds

### Configurable Thresholds

```python
from spine.orchestration import QualityThresholds

thresholds = QualityThresholds(
    min_valid_rate=0.95,      # At least 95% valid
    max_null_rate=0.01,       # At most 1% nulls
    min_record_count=100,     # At least 100 records
    max_record_count=1000000, # At most 1M records
)

Step.lambda_("validate", validate_fn, quality_thresholds=thresholds)
```

### Threshold Enforcement

```python
def validate_step(ctx: WorkflowContext, config: dict) -> StepResult:
    thresholds = QualityThresholds.from_config(config)
    
    records = ctx.get_output("fetch", "records", [])
    valid_records = [r for r in records if validate_record(r)]
    
    quality = QualityMetrics(
        record_count=len(records),
        valid_count=len(valid_records),
    )
    
    # Check against thresholds
    violations = thresholds.check(quality)
    
    if violations:
        quality.passed = False
        quality.failure_reasons = violations
        
        return StepResult.fail(
            error=f"Quality gate failed: {'; '.join(violations)}",
            category="DATA_QUALITY",
            quality=quality,
        )
    
    quality.passed = True
    return StepResult.ok(
        output={"valid_records": len(valid_records)},
        quality=quality,
    )
```

---

## Quality Gate Patterns

### Pattern 1: Inline Validation

Quick validation within a lambda:

```python
def ingest_with_validation(ctx: WorkflowContext, config: dict) -> StepResult:
    raw_records = fetch_from_source()
    
    # Validate as we process
    valid = []
    invalid = []
    
    for record in raw_records:
        errors = validate_record(record)
        if errors:
            invalid.append({"record": record, "errors": errors})
        else:
            valid.append(record)
    
    # Quality gate
    valid_rate = len(valid) / len(raw_records) if raw_records else 0
    
    if valid_rate < 0.90:  # Hard threshold
        return StepResult.fail(
            error=f"Only {valid_rate:.1%} records valid, need 90%",
            category="DATA_QUALITY",
            output={
                "sample_errors": invalid[:10],
            },
            quality=QualityMetrics(
                record_count=len(raw_records),
                valid_count=len(valid),
                passed=False,
            ),
        )
    
    # Store invalid for review
    if invalid:
        store_invalid_records(invalid, ctx.partition)
    
    return StepResult.ok(
        output={
            "valid_count": len(valid),
            "invalid_count": len(invalid),
        },
        quality=QualityMetrics(
            record_count=len(raw_records),
            valid_count=len(valid),
            passed=True,
        ),
    )
```

### Pattern 2: Dedicated Quality Gate Step

Separate step for validation:

```python
workflow = Workflow(
    steps=[
        Step.pipeline("ingest", "my.ingest"),
        Step.lambda_("quality_gate", quality_gate_fn,
            on_error=ErrorPolicy.STOP),  # Stop workflow on failure
        Step.pipeline("transform", "my.transform"),
    ],
)


def quality_gate_fn(ctx: WorkflowContext, config: dict) -> StepResult:
    """Dedicated quality gate step."""
    ingest_output = ctx.get_output("ingest")
    
    checks = [
        check_record_count(ingest_output),
        check_null_rates(ingest_output),
        check_data_freshness(ingest_output),
        check_schema_compliance(ingest_output),
    ]
    
    failures = [c for c in checks if not c.passed]
    
    if failures:
        return StepResult.fail(
            error="Quality gate failed",
            category="DATA_QUALITY",
            output={"failures": [f.to_dict() for f in failures]},
        )
    
    return StepResult.ok(
        output={"all_checks_passed": True, "check_count": len(checks)},
    )
```

### Pattern 3: Soft vs Hard Gates

Some gates warn, others fail:

```python
def soft_quality_gate(ctx: WorkflowContext, config: dict) -> StepResult:
    """Warn on quality issues but don't fail."""
    issues = check_quality(ctx)
    
    if issues:
        # Log warning but continue
        log_quality_warning(issues)
        
        return StepResult.ok(
            output={
                "warnings": issues,
                "continued_despite_warnings": True,
            },
            quality=QualityMetrics(passed=True),  # Soft pass
            events=[
                {"type": "quality_warning", "issues": len(issues)},
            ],
        )
    
    return StepResult.ok(output={"quality_clean": True})


def hard_quality_gate(ctx: WorkflowContext, config: dict) -> StepResult:
    """Fail on any quality issue."""
    issues = check_quality(ctx)
    
    if issues:
        return StepResult.fail(
            error=f"Quality gate failed: {issues[0]}",
            category="DATA_QUALITY",
        )
    
    return StepResult.ok(output={"quality_clean": True})
```

---

## Domain-Specific Quality Checks

### FINRA OTC Quality Gate

```python
def finra_quality_gate(ctx: WorkflowContext, config: dict) -> StepResult:
    """Quality gate for FINRA OTC data."""
    records = ctx.get_output("normalize", "records", [])
    tier = ctx.params["tier"]
    week_ending = ctx.params["week_ending"]
    
    checks = {
        "record_count": check_finra_record_count(records, tier),
        "required_symbols": check_required_symbols(records, tier),
        "price_range": check_price_ranges(records),
        "volume_sanity": check_volume_sanity(records),
        "date_consistency": check_dates(records, week_ending),
    }
    
    failures = {k: v for k, v in checks.items() if not v["passed"]}
    
    quality = QualityMetrics(
        record_count=len(records),
        passed=len(failures) == 0,
        custom_metrics={
            "tier": tier,
            "check_results": checks,
        },
        failure_reasons=[f["reason"] for f in failures.values()],
    )
    
    if failures:
        return StepResult.fail(
            error=f"FINRA quality gate failed: {list(failures.keys())}",
            category="DATA_QUALITY",
            quality=quality,
        )
    
    return StepResult.ok(
        output={"checks_passed": list(checks.keys())},
        quality=quality,
    )


def check_finra_record_count(records: list, tier: str) -> dict:
    """Check record count is reasonable for tier."""
    count = len(records)
    
    expected_ranges = {
        "NMS_TIER_1": (10000, 100000),
        "NMS_TIER_2": (5000, 50000),
        "OTC": (1000, 20000),
    }
    
    min_expected, max_expected = expected_ranges.get(tier, (0, 1000000))
    
    if count < min_expected:
        return {"passed": False, "reason": f"Too few records: {count} < {min_expected}"}
    if count > max_expected:
        return {"passed": False, "reason": f"Too many records: {count} > {max_expected}"}
    
    return {"passed": True, "count": count}


def check_required_symbols(records: list, tier: str) -> dict:
    """Check that required symbols are present."""
    symbols = {r["symbol"] for r in records}
    
    required = {"AAPL", "MSFT", "GOOGL", "AMZN"}  # Top stocks
    missing = required - symbols
    
    if missing:
        return {"passed": False, "reason": f"Missing required symbols: {missing}"}
    
    return {"passed": True, "symbol_count": len(symbols)}
```

### Market Data Quality Gate

```python
def market_data_quality_gate(ctx: WorkflowContext, config: dict) -> StepResult:
    """Quality gate for market data."""
    prices = ctx.get_output("fetch_prices", "prices", [])
    run_date = ctx.params["run_date"]
    
    issues = []
    
    # Check for stale data
    stale = [p for p in prices if p["price_date"] != run_date]
    if len(stale) / len(prices) > 0.05:
        issues.append(f"Too many stale prices: {len(stale)}")
    
    # Check for extreme moves
    extreme = [p for p in prices if abs(p.get("pct_change", 0)) > 0.50]
    if len(extreme) > 10:
        issues.append(f"Too many extreme price moves: {len(extreme)}")
    
    # Check for gaps
    expected_symbols = get_expected_symbols()
    actual_symbols = {p["symbol"] for p in prices}
    missing = expected_symbols - actual_symbols
    if missing:
        issues.append(f"Missing {len(missing)} symbols")
    
    quality = QualityMetrics(
        record_count=len(prices),
        valid_count=len(prices) - len(stale),
        passed=len(issues) == 0,
        custom_metrics={
            "stale_count": len(stale),
            "extreme_moves": len(extreme),
            "missing_symbols": len(missing),
        },
        failure_reasons=issues,
    )
    
    if issues:
        return StepResult.fail(
            error=f"Market data quality failed: {issues[0]}",
            category="DATA_QUALITY",
            quality=quality,
        )
    
    return StepResult.ok(
        output={"validated": True},
        quality=quality,
    )
```

---

## Quality Metrics Storage

### Automatic Storage

Quality metrics are stored in `core_workflow_run_steps`:

```sql
SELECT 
    step_name,
    quality_record_count,
    quality_valid_count,
    quality_null_count,
    quality_passed,
    quality_custom
FROM core_workflow_run_steps
WHERE run_id = 'abc-123'
ORDER BY started_at;
```

### Historical Analysis

```sql
-- Quality trend over time
SELECT 
    DATE(created_at) as run_date,
    AVG(quality_valid_count::float / NULLIF(quality_record_count, 0)) as avg_valid_rate,
    COUNT(*) FILTER (WHERE quality_passed) as passes,
    COUNT(*) FILTER (WHERE NOT quality_passed) as failures
FROM core_workflow_run_steps
WHERE step_name = 'quality_gate'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY run_date;
```

---

## Best Practices

### 1. Fail Fast

```python
# ❌ Bad: Check quality at the end
workflow = Workflow(steps=[
    Step.pipeline("ingest", ...),
    Step.pipeline("transform", ...),  # Wastes time on bad data
    Step.pipeline("load", ...),       # Wastes time on bad data
    Step.lambda_("validate", ...),    # Too late!
])

# ✅ Good: Check quality early
workflow = Workflow(steps=[
    Step.pipeline("ingest", ...),
    Step.lambda_("validate", ...),    # Fail before transform
    Step.pipeline("transform", ...),
    Step.pipeline("load", ...),
])
```

### 2. Use Appropriate Thresholds

```python
# ❌ Bad: Too strict (causes false failures)
if valid_rate < 1.0:  # 100% required
    return StepResult.fail(...)

# ✅ Good: Reasonable threshold with monitoring
if valid_rate < 0.95:  # 95% required
    return StepResult.fail(...)
```

### 3. Provide Actionable Errors

```python
# ❌ Bad: Vague error
return StepResult.fail(error="Quality check failed")

# ✅ Good: Specific, actionable error
return StepResult.fail(
    error=f"Quality check failed: null rate {null_rate:.1%} exceeds 1% threshold",
    category="DATA_QUALITY",
    output={
        "null_rate": null_rate,
        "threshold": 0.01,
        "sample_null_records": null_records[:5],
    },
)
```

### 4. Track Quality Over Time

```python
def quality_gate_with_trends(ctx: WorkflowContext, config: dict) -> StepResult:
    current_quality = calculate_quality(ctx)
    
    # Get historical baseline
    historical = get_historical_quality(
        workflow=ctx.workflow_name,
        step="ingest",
        days=30,
    )
    
    # Check for significant deviation
    if current_quality.valid_rate < historical.avg_valid_rate - 0.10:
        # 10% below historical average
        return StepResult.fail(
            error=f"Quality significantly below historical average",
            output={
                "current_rate": current_quality.valid_rate,
                "historical_avg": historical.avg_valid_rate,
            },
        )
    
    return StepResult.ok(output={"quality": current_quality})
```
