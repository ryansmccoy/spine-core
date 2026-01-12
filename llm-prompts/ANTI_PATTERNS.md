# Anti-Patterns Reference

**Review this before implementing any feature. These patterns are FORBIDDEN.**

---

## Quick Reference Table

| Anti-Pattern | Why Forbidden | Correct Pattern |
|-------------|---------------|-----------------|
| Standalone ingestion CLI commands | Bypasses pipeline framework, no dispatcher | `@register_pipeline` in domains |
| Runtime `CREATE VIEW` | Schema drift, testing gaps | `schema/02_views.sql` |
| Branching factories | Tight coupling, not extensible | Registry: `SOURCES.register()` |
| `MAX(version)` queries | Non-deterministic with ties | `ROW_NUMBER() OVER (... ORDER BY ...)` |
| Silent failures | Hides errors, breaks observability | Record anomaly, then handle |
| Global anomaly filtering | Hides unrelated clean data | Scoped: `partition_key = ?` |
| Audit fields in comparisons | False negatives in tests | Exclude: `captured_at`, `batch_id` |
| Hardcoded week lists | Brittle, fails with changes | Generate from period utils |
| Non-consecutive window checks | Mathematical incorrectness | Enforce ALL consecutive weeks |
| Missing capture_id | Breaks lineage/replay | Every output needs capture_id |
| Missing provenance | Can't audit rolled-up data | Track input_min/max_capture_id |
| **Pipeline logic in workflow lambdas** | Duplicates code, bypasses registry | `Step.pipeline("name", "registered.pipeline")` |
| **Business logic in lambda steps** | Wrong layer, hard to test | Put logic in registered pipelines |
| **Workflows without pipelines** | Misses framework benefits | Create pipelines first, then workflow |

---

## Detailed Anti-Patterns

### 1. Standalone Ingestion CLI Commands

**❌ WRONG:**
```python
# In: market-spine-basic/src/market_spine/app/commands/fetch_prices.py
def main():
    source = AlphaVantageSource(config)
    data = source.fetch(params)
    conn = sqlite3.connect(db_path)
    for row in data:
        conn.execute("INSERT INTO prices ...")
```

**Why forbidden:**
- Bypasses pipeline framework (no dispatcher, no execution_id)
- No standard logging/metrics integration
- No dry-run support
- Can't be invoked via API
- Not discoverable via `spine pipelines list`
- Duplicates logic that should be in domains

**✅ CORRECT:**
```python
# In: packages/spine-domains/src/spine/domains/market_data/pipelines.py
@register_pipeline("market_data.ingest_prices")
class IngestPricesPipeline(Pipeline):
    def run(self) -> PipelineResult:
        source = create_source()
        data, anomalies = source.fetch(self.params)
        # ... insert to database ...
        return PipelineResult(status=PipelineStatus.COMPLETED, ...)

# Invoked via:
# spine run run market_data.ingest_prices -p symbol=AAPL
```

---

### 2. Runtime CREATE VIEW

**❌ WRONG:**
```python
# In Python code
def setup_views(conn):
    conn.execute("""
        CREATE VIEW IF NOT EXISTS my_view AS
        SELECT * FROM my_table WHERE is_active = 1
    """)
```

**Why forbidden:**
- Schema drift between environments
- Views not tracked in migrations
- Testing gaps (tests may not create views)
- Deployment inconsistency

**✅ CORRECT:**
```sql
-- In: spine-domains/src/spine/domains/{domain}/schema/02_views.sql
CREATE VIEW IF NOT EXISTS my_view AS
SELECT * FROM my_table WHERE is_active = 1;
```

Then run: `python scripts/build_schema.py`

---

### 2. Branching Factories

**❌ WRONG:**
```python
def get_source(source_type):
    if source_type == "finra":
        return FinraSource()
    elif source_type == "sec":
        return SecSource()
    elif source_type == "nasdaq":
        return NasdaqSource()
    else:
        raise ValueError(f"Unknown source: {source_type}")
```

**Why forbidden:**
- Tight coupling to all source types
- Adding new source requires modifying factory
- Violates Open/Closed principle
- Hard to test in isolation

**✅ CORRECT:**
```python
# In each source file:
from spine.framework.registry import SOURCES

@SOURCES.register("finra")
class FinraSource(Source):
    ...

# Usage:
source = SOURCES.get(source_type)
```

---

### 3. MAX(version) Queries

**❌ WRONG:**
```sql
SELECT * FROM calculations
WHERE version = (SELECT MAX(version) FROM calculations)
```

**Why forbidden:**
- Non-deterministic if multiple rows have same MAX
- Race conditions during inserts
- Unpredictable which row is returned

**✅ CORRECT:**
```sql
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY symbol, week_ending 
               ORDER BY captured_at DESC
           ) as rn
    FROM calculations
) WHERE rn = 1
```

---

### 4. Silent Failures

**❌ WRONG:**
```python
def process_item(item):
    try:
        return do_work(item)
    except Exception:
        pass  # Silently ignore
    return None

def process_batch(items):
    try:
        for item in items:
            process_item(item)
    except Exception:
        return []  # Return empty on any error
```

**Why forbidden:**
- Errors invisible to operators
- No alerting possible
- Data quality issues go undetected
- Debugging nightmare

**✅ CORRECT:**
```python
def process_item(item):
    try:
        return do_work(item)
    except ValidationError as e:
        record_anomaly(
            domain="finra.otc_transparency",
            stage="NORMALIZE",
            partition_key=f"{item.week}|{item.tier}",
            severity="ERROR",
            category="VALIDATION",
            message=str(e),
            metadata={"item_id": item.id, "error_type": type(e).__name__}
        )
        return None  # Partial success - skip this item

def process_batch(items):
    results = []
    errors = []
    for item in items:
        result = process_item(item)
        if result:
            results.append(result)
        else:
            errors.append(item.id)
    
    if errors:
        log.warning(f"Skipped {len(errors)} items: {errors}")
    
    return results
```

---

### 5. Global Anomaly Filtering

**❌ WRONG:**
```sql
-- This hides ALL data when ANY error exists
SELECT * FROM rolling_data r
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.severity = 'ERROR'
)
```

**Why forbidden:**
- One error hides ALL data
- Unrelated partitions affected
- Can't debug which partition has issues

**✅ CORRECT:**
```sql
-- Scoped to exact partition
SELECT * FROM rolling_data r
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.domain = 'finra.otc_transparency'
      AND a.stage = 'ROLLING'
      AND a.partition_key = r.week_ending || '|' || r.tier
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
)
```

---

### 6. Audit Fields in Determinism Checks

**❌ WRONG:**
```python
def test_determinism():
    result1 = run_pipeline(params)
    result2 = run_pipeline(params)
    assert result1 == result2  # FAILS: captured_at differs
```

**Why forbidden:**
- Timestamps always differ between runs
- False negatives (tests fail when code is correct)
- batch_id/execution_id are runtime-generated

**✅ CORRECT:**
```python
AUDIT_FIELDS = ["captured_at", "batch_id", "execution_id"]

def test_determinism():
    result1 = run_pipeline(params)
    result2 = run_pipeline(params)
    
    # Remove audit fields before comparison
    for r in [result1, result2]:
        for field in AUDIT_FIELDS:
            r.pop(field, None)
    
    assert result1 == result2
```

---

### 7. Hardcoded Week Lists

**❌ WRONG:**
```python
WEEKS_TO_PROCESS = [
    "2025-12-26",
    "2025-12-19",
    "2025-12-12",
    "2025-12-05",
    "2025-11-28",
    "2025-11-21",
]

def get_history_weeks():
    return WEEKS_TO_PROCESS
```

**Why forbidden:**
- Breaks when new weeks arrive
- Requires code changes for schedule changes
- Not portable across environments

**✅ CORRECT:**
```python
from spine.framework.periods import get_week_range

def get_history_weeks(reference_date, count=6):
    """Generate N weeks ending before reference_date."""
    return get_week_range(
        end_date=reference_date,
        weeks=count,
        week_ending_day="Friday"
    )

# Or query from schedule table:
def get_expected_weeks(conn, domain, stage, count=6):
    return conn.execute("""
        SELECT DISTINCT week_ending 
        FROM core_data_readiness
        WHERE domain = ? AND stage = ?
        ORDER BY week_ending DESC
        LIMIT ?
    """, (domain, stage, count)).fetchall()
```

---

### 8. Non-Consecutive Window Checks

**❌ WRONG:**
```python
def has_enough_history(weeks_found, required=6):
    # Just checks count, not consecutiveness
    return len(weeks_found) >= required

# Passes with [week1, week2, week5, week6, week7, week8] - gap at 3,4!
```

**Why forbidden:**
- Mathematical incorrectness for rolling averages
- Missing weeks corrupt statistics
- Hidden data quality issues

**✅ CORRECT:**
```python
def has_consecutive_history(weeks_found, reference_week, required=6):
    """Enforce ALL consecutive weeks exist (no gaps)."""
    expected_weeks = generate_expected_weeks(reference_week, required)
    found_set = set(weeks_found)
    missing = [w for w in expected_weeks if w not in found_set]
    
    if missing:
        log.warning(f"Missing weeks: {missing}")
        return False, missing
    
    return True, []
```

---

### 9. Missing capture_id

**❌ WRONG:**
```python
def write_output(conn, rows):
    conn.executemany("""
        INSERT INTO output_table (symbol, value, calculated_at)
        VALUES (?, ?, ?)
    """, rows)
```

**Why forbidden:**
- Can't track data lineage
- Can't replay/recompute
- Can't implement idempotency
- Can't do as-of queries

**✅ CORRECT:**
```python
def write_output(conn, rows, capture_id, execution_id, batch_id):
    now = datetime.utcnow().isoformat()
    
    for row in rows:
        row["capture_id"] = capture_id
        row["captured_at"] = now
        row["execution_id"] = execution_id
        row["batch_id"] = batch_id
    
    conn.executemany("""
        INSERT INTO output_table 
        (symbol, value, calculated_at, capture_id, captured_at, execution_id, batch_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    
    # Track in manifest
    conn.execute("""
        INSERT INTO core_manifest 
        (capture_id, domain, stage, partition_key, captured_at, status, row_count)
        VALUES (?, ?, ?, ?, ?, 'complete', ?)
    """, (capture_id, domain, stage, partition_key, now, len(rows)))
```

---

### 10. Missing Provenance

**❌ WRONG:**
```python
def compute_rolling(input_rows):
    avg = sum(r["volume"] for r in input_rows) / len(input_rows)
    return {"avg_volume": avg}  # No provenance tracking
```

**Why forbidden:**
- Can't debug rolled-up data
- Can't trace back to source captures
- Can't handle restatements correctly

**✅ CORRECT:**
```python
def compute_rolling(input_rows):
    # Track which inputs contributed
    capture_ids = [r["capture_id"] for r in input_rows]
    captured_ats = [r["captured_at"] for r in input_rows]
    
    avg = sum(r["volume"] for r in input_rows) / len(input_rows)
    
    return {
        "avg_volume": avg,
        "input_min_capture_id": min(capture_ids),
        "input_max_capture_id": max(capture_ids),
        "input_min_captured_at": min(captured_ats),
        "input_max_captured_at": max(captured_ats),
        "input_row_count": len(input_rows),
    }
```

---

## Detection Checklist

Use this during code review:

- [ ] No `CREATE VIEW` in Python files
- [ ] No `if/elif` chains for type dispatch
- [ ] No `MAX(version)` or `MAX(captured_at)` without `ROW_NUMBER`
- [ ] No `except: pass` or `except Exception: return`
- [ ] No anomaly filtering without `partition_key` match
- [ ] No `assert x == y` with raw timestamps
- [ ] No hardcoded date/week lists
- [ ] No window checks that only count (must verify consecutive)
- [ ] All output tables have `capture_id` column
- [ ] Rolled-up data tracks `input_min/max_capture_id`
- [ ] Scheduler wrapper scripts remain thin (≤50 lines of logic)
- [ ] Schedulers return `SchedulerResult` (not custom result types)
- [ ] All scheduler runs use standard exit codes (0/1/2)

---

## Scheduler Anti-Patterns

### 12. Custom Scheduler Result Types

**❌ WRONG:**
```python
# Creating domain-specific result types
@dataclass
class MyDomainScheduleResult:
    success: list[str]
    failed: list[str]
    duration: float
    # ... non-standard fields
```

**Why forbidden:**
- Inconsistent JSON schema across domains
- Automation can't parse different result formats
- Exit codes not standardized
- No schema versioning

**✅ CORRECT:**
```python
from market_spine.app.scheduling import SchedulerResult, SchedulerStatus, RunResult

def run_my_schedule(...) -> SchedulerResult:
    # ... business logic ...
    return SchedulerResult(
        domain="my.domain",
        scheduler="my_scheduler",
        started_at=started_at,
        finished_at=finished_at,
        status=SchedulerStatus.SUCCESS,
        stats=SchedulerStats(...),
        runs=runs,  # List of RunResult
    )
```

---

### 13. Fat Wrapper Scripts

**❌ WRONG:**
```python
# scripts/schedule_my_domain.py
def main():
    # 100+ lines of business logic
    conn = sqlite3.connect(db_path)
    for week in weeks:
        data = fetch_data(week)
        # ... processing ...
        insert_data(conn, data)
    # ... more logic ...
```

**Why forbidden:**
- Business logic in wrapper scripts (should be in domain scheduler)
- Hard to test (subprocess required)
- Duplicates logic across scripts
- Violates thin wrapper principle

**✅ CORRECT:**
```python
# scripts/schedule_my_domain.py
def main() -> int:
    args = parse_args()
    log = setup_logging(args.log_level)
    
    # Import domain scheduler (all business logic is there)
    from spine.domains.my_domain.scheduler import run_my_schedule
    
    result = run_my_schedule(**vars(args))
    
    if args.json:
        print(result.to_json())
    
    return result.exit_code
```

---

### 14. Non-Standard Exit Codes

**❌ WRONG:**
```python
if success:
    return 0
elif partial:
    return 1  # Wrong! Partial should be 2
else:
    return -1  # Non-standard
```

**Why forbidden:**
- Breaks automation that expects standard codes
- Inconsistent across schedulers
- Negative codes don't work cross-platform

**✅ CORRECT:**
```python
# Use SchedulerResult.exit_code (derived from status)
return result.exit_code
# 0 = SUCCESS or DRY_RUN
# 1 = FAILURE (all failed)
# 2 = PARTIAL (some failed)
```

---

### 15. Unlimited Lookback

**❌ WRONG:**
```python
def run_schedule(lookback_weeks: int):
    weeks = calculate_weeks(lookback_weeks)  # No limit!
    # Could process 100+ weeks, hitting rate limits, OOM, etc.
```

**Why forbidden:**
- Accidental large backfills
- API rate limit violations
- Memory exhaustion
- Unexpected long-running jobs

**✅ CORRECT:**
```python
MAX_LOOKBACK_WEEKS = 12

def run_schedule(lookback_weeks: int, force: bool = False):
    if lookback_weeks > MAX_LOOKBACK_WEEKS and not force:
        warnings.append(f"Clamped to {MAX_LOOKBACK_WEEKS}. Use --force to override.")
        lookback_weeks = MAX_LOOKBACK_WEEKS
    # ...
```

---

## Related Documents

- [CONTEXT.md](CONTEXT.md) - Correct patterns
- [reference/SQL_PATTERNS.md](reference/SQL_PATTERNS.md) - SQL best practices

---

## Workflow-Specific Anti-Patterns

### 16. Pipeline Logic in Workflow Lambdas

**❌ WRONG:**
```python
def fetch_data_lambda(ctx, config):
    """Lambda step that does pipeline work."""
    # This should be in a pipeline!
    response = requests.get(url)
    data = parse_response(response)
    conn.executemany("INSERT INTO table...", data)
    return StepResult.ok(output={"rows": len(data)})

workflow = Workflow(
    steps=[
        Step.lambda_("fetch", fetch_data_lambda),  # Wrong!
        Step.pipeline("process", "domain.process"),
    ],
)
```

**Why forbidden:**
- Duplicates pipeline logic
- Bypasses pipeline registry
- No capture_id, execution_id tracking
- Not testable in isolation
- Can't be reused by other workflows

**✅ CORRECT:**
```python
def validate_fetch(ctx, config):
    """Lambda step that validates (not fetches)."""
    result = ctx.get_output("fetch")
    if result.get("row_count", 0) < 100:
        return StepResult.fail("Too few records", "QUALITY_GATE")
    return StepResult.ok()

workflow = Workflow(
    steps=[
        Step.pipeline("fetch", "domain.fetch_data"),  # Correct!
        Step.lambda_("validate", validate_fetch),      # Lightweight
        Step.pipeline("process", "domain.process"),
    ],
)
```

---

### 17. Business Logic in Lambda Steps

**❌ WRONG:**
```python
def calculate_metrics_lambda(ctx, config):
    """Lambda that computes (should be pipeline)."""
    data = load_from_db()
    
    # This is business logic!
    metrics = {}
    for row in data:
        metrics[row.symbol] = compute_rolling_avg(row)
    
    save_to_db(metrics)
    return StepResult.ok()
```

**Why forbidden:**
- Lambda steps should be stateless validators
- Business logic belongs in pipelines
- Makes testing and reuse harder
- Bypasses calculation framework

**✅ CORRECT:**
```python
def check_data_quality(ctx, config):
    """Lambda validates quality metrics from previous step."""
    result = ctx.get_output("aggregate")
    null_rate = result.get("null_rate", 0)
    if null_rate > 0.05:
        return StepResult.fail(f"Null rate: {null_rate:.1%}", "DATA_QUALITY")
    return StepResult.ok()

# Business logic is in the pipeline:
@register_pipeline("domain.compute_metrics")
class ComputeMetricsPipeline(Pipeline):
    def run(self):
        # All calculation logic here
        ...
```

---

### 18. Workflows Without Registered Pipelines

**❌ WRONG:**
```python
# Creating workflow with inline functions instead of registered pipelines
workflow = Workflow(
    steps=[
        Step.lambda_("ingest", lambda ctx, cfg: do_ingest()),   # Wrong
        Step.lambda_("normalize", lambda ctx, cfg: normalize()), # Wrong
        Step.lambda_("aggregate", lambda ctx, cfg: aggregate()), # Wrong
    ],
)
```

**Why forbidden:**
- No pipeline registration benefits (discovery, logging, metrics)
- Can't invoke individual steps via CLI
- No capture_id semantics
- Harder to test

**✅ CORRECT:**
```python
# First, create and register pipelines
@register_pipeline("domain.ingest")
class IngestPipeline(Pipeline): ...

@register_pipeline("domain.normalize")
class NormalizePipeline(Pipeline): ...

# Then, workflow references them
workflow = Workflow(
    steps=[
        Step.pipeline("ingest", "domain.ingest"),
        Step.lambda_("validate", check_ingest_quality),  # Only validation
        Step.pipeline("normalize", "domain.normalize"),
    ],
)
```

---

### 19. Ignoring Workflow Tracking

**❌ WRONG:**
```python
# Running workflow without manifest or anomaly tracking
result = runner.execute(workflow, params)
# Just checking result, not recording anything
if result.status == WorkflowStatus.FAILED:
    print(f"Failed: {result.error}")  # Lost to logs
```

**Why forbidden:**
- No persistent record of execution
- Can't query historical runs
- No idempotency enforcement
- Failures not auditable

**✅ CORRECT:**
```python
manifest = WorkManifest(conn, domain=f"workflow.{workflow.name}", stages=[...])
anomaly_recorder = AnomalyRecorder(conn, domain=workflow.name)

manifest.advance_to(key, "STARTED", execution_id=run_id)
result = runner.execute(workflow, params)

if result.status == WorkflowStatus.COMPLETED:
    manifest.advance_to(key, "COMPLETED", execution_id=run_id)
else:
    anomaly_recorder.record(
        stage=f"step.{result.error_step}",
        severity="ERROR",
        category="WORKFLOW_FAILURE",
        message=result.error,
    )
```
- [prompts/E_REVIEW.md](prompts/E_REVIEW.md) - Review checklist
- [docs/operations/SCHEDULER_OPERATIONS.md](../docs/operations/SCHEDULER_OPERATIONS.md) - Scheduler usage guide
