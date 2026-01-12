# Prompt C: Add Operational Feature

**Use this prompt when:** Implementing schedulers, gap detection, quality gates, monitoring, readiness tracking, or other operational infrastructure.

---

## Copy-Paste Prompt

```
I need to implement an operational feature for Market Spine.

CONTEXT:
- Read llm-prompts/CONTEXT.md first for repository structure
- Operational features use core tables (owned by spine-core, DO NOT modify)
- Add domain-specific helpers in spine-domains
- Must handle edge cases gracefully (record anomalies, don't crash)

CORE TABLES AVAILABLE (read/write, DO NOT modify schema):
- core_manifest: Capture lineage (capture_id, domain, stage, status)
- core_anomalies: Error recording (severity, category, partition_key)
- core_data_readiness: Availability tracking (is_ready per week)
- core_expected_schedules: When data should arrive
- core_calc_dependencies: Calculation DAG

FEATURE DETAILS:
- Name: {feature_name}
- Type: {Scheduler / Quality Gate / Gap Detection / Monitoring / Other}
- Domain: {domain_name or "cross-domain"}
- Purpose: {What problem does this solve?}

---

IMPLEMENTATION CHECKLIST:

### 1. Identify Core Tables Needed

| Table | Purpose in This Feature |
|-------|------------------------|
| core_manifest | {How you'll use it} |
| core_anomalies | {How you'll use it} |
| core_data_readiness | {How you'll use it} |
| core_expected_schedules | {How you'll use it} |

### 2. Helper Functions (Domain-Specific)
Location: `spine-domains/src/spine/domains/{domain}/validators.py`

```python
"""
Validation and quality gate helpers for {domain}.

These helpers use core tables but don't modify their schemas.
"""

def require_{condition}(
    conn,
    table: str,
    week_ending: date,
    **kwargs
) -> tuple[bool, list[str]]:
    """
    Validate {condition} before proceeding.
    
    INSTITUTIONAL-GRADE CONTRACT:
    - Returns (True, []) if condition met
    - Returns (False, [reasons]) if condition not met
    - Records anomaly if condition not met
    - Caller decides whether to proceed or skip
    
    Args:
        conn: Database connection
        table: Table to check
        week_ending: Target week
        **kwargs: Additional parameters
    
    Returns:
        (ok, issues) tuple
    """
    # Check condition
    issues = []
    
    # Query data
    rows = conn.execute("""
        SELECT ... FROM {table}
        WHERE week_ending = ?
    """, (week_ending,)).fetchall()
    
    # Validate
    if not rows:
        issues.append(f"No data for {week_ending}")
    
    # Additional checks...
    
    ok = len(issues) == 0
    
    if not ok:
        log.warning(f"{condition}_check_failed: {issues}")
    else:
        log.info(f"{condition}_check_passed")
    
    return ok, issues


def get_{filtered_items}(
    conn,
    table: str,
    week_ending: date,
    **kwargs
) -> set[str]:
    """
    Get items that pass {condition}.
    
    Used for partial processing: compute valid items, skip invalid.
    
    Args:
        conn: Database connection
        table: Table to check
        week_ending: Target week
    
    Returns:
        Set of valid item identifiers
    """
    # Query and filter
    pass
```

### 3. Quality Gate Integration
Location: `spine-domains/src/spine/domains/{domain}/pipelines.py`

```python
def run(self) -> dict:
    # 1. QUALITY GATE (before any computation)
    ok, issues = require_{condition}(
        self.conn,
        table="source_table",
        week_ending=self.params["week_ending"],
        tier=self.params["tier"],
    )
    
    if not ok:
        # Record anomaly
        self.record_anomaly(
            severity="ERROR",
            category="QUALITY_GATE",
            partition_key=f"{week_ending}|{tier}",
            message=f"Quality gate failed: {issues}",
            metadata={"issues": issues}
        )
        # Skip processing (don't crash)
        return {
            "status": "skipped",
            "reason": "quality_gate_failed",
            "issues": issues,
        }
    
    # 2. Proceed with processing
    results = self._process()
    
    # 3. Update readiness
    self._update_readiness(week_ending, tier, is_ready=True)
    
    return {"status": "complete", "rows": len(results)}
```

### 4. Anomaly Recording Pattern
```python
def record_anomaly(
    self,
    severity: str,
    category: str,
    partition_key: str,
    message: str,
    metadata: dict = None,
):
    """
    Record an anomaly for later review/alerting.
    
    Severity levels:
        DEBUG: Diagnostic info
        INFO: Notable event
        WARN: Potential issue, processing continues
        ERROR: Processing failed for this partition
        CRITICAL: System-level failure
    
    Categories:
        QUALITY_GATE: Input validation failed
        NETWORK: External service error
        DATA_QUALITY: Data validation failed
        SCHEDULE: Expected data missing
        PROCESSING: Computation error
    """
    import uuid
    from datetime import datetime
    
    self.conn.execute("""
        INSERT INTO core_anomalies (
            anomaly_id, domain, stage, partition_key,
            severity, category, message,
            detected_at, metadata, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
    """, (
        str(uuid.uuid4()),
        self.domain,
        self.stage,
        partition_key,
        severity,
        category,
        message,
        datetime.utcnow().isoformat(),
        json.dumps(metadata) if metadata else None,
    ))
```

### 5. Scoped Anomaly Filtering (CRITICAL)
When filtering data based on anomalies, ALWAYS scope by partition:

```sql
-- ❌ WRONG: Global filter hides all data if any error exists
SELECT * FROM data_table
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies WHERE severity = 'ERROR'
)

-- ✅ CORRECT: Scoped filter only hides affected partitions
SELECT * FROM data_table d
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.domain = '{domain}'
      AND a.stage = '{stage}'
      AND a.partition_key = d.week_ending || '|' || d.tier
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
)
```

### 6. Views (Schema-Based)
Location: `spine-domains/src/spine/domains/{domain}/schema/02_views.sql`

```sql
-- View with quality gate
CREATE VIEW IF NOT EXISTS {domain}_{feature}_latest AS
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY week_ending, tier 
               ORDER BY captured_at DESC
           ) as rn
    FROM {domain}_{table}
    WHERE is_complete = 1  -- Quality gate
) WHERE rn = 1;

-- View with scoped anomaly filtering
CREATE VIEW IF NOT EXISTS {domain}_{feature}_clean AS
SELECT d.* FROM {domain}_{feature}_latest d
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.domain = '{domain}'
      AND a.stage = '{STAGE}'
      AND a.partition_key = d.week_ending || '|' || d.tier
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
);

-- Stats view for monitoring
CREATE VIEW IF NOT EXISTS {domain}_{feature}_stats AS
SELECT 
    week_ending,
    tier,
    COUNT(*) as total_items,
    SUM(CASE WHEN is_complete = 1 THEN 1 ELSE 0 END) as complete_items,
    ROUND(100.0 * SUM(CASE WHEN is_complete = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as pct_complete
FROM {domain}_{table}
GROUP BY week_ending, tier;
```

### 7. Readiness Tracking
```python
def update_readiness(self, week_ending: str, partition_key: str, is_ready: bool):
    """Update data readiness status."""
    from datetime import datetime
    
    self.conn.execute("""
        INSERT INTO core_data_readiness (domain, stage, partition_key, week_ending, is_ready, checked_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (domain, stage, partition_key, week_ending) 
        DO UPDATE SET is_ready = ?, checked_at = ?
    """, (
        self.domain,
        self.stage,
        partition_key,
        week_ending,
        1 if is_ready else 0,
        datetime.utcnow().isoformat(),
        1 if is_ready else 0,
        datetime.utcnow().isoformat(),
    ))
```

### 8. Tests
Location: `tests/{domain}/test_{feature}.py`

Required tests:
```python
class Test{Feature}:
    def test_quality_gate_pass(self, db_conn, valid_data):
        """Valid data passes quality gate."""
        ok, issues = require_{condition}(db_conn, ...)
        assert ok
        assert issues == []
    
    def test_quality_gate_fail(self, db_conn, invalid_data):
        """Invalid data fails gracefully."""
        ok, issues = require_{condition}(db_conn, ...)
        assert not ok
        assert len(issues) > 0
    
    def test_anomaly_recorded_on_failure(self, db_conn, invalid_data):
        """Failure records anomaly."""
        pipeline.run()
        anomalies = get_anomalies(db_conn, domain, stage)
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "ERROR"
    
    def test_partial_success(self, db_conn, mixed_data):
        """Some items pass, some fail."""
        result = pipeline.run()
        assert result["processed"] > 0
        assert result["skipped"] > 0
    
    def test_scoped_filtering(self, db_conn, data_with_errors):
        """Error in partition A doesn't hide partition B."""
        # Insert error for week 1, tier 1
        insert_anomaly(db_conn, partition="2026-01-09|TIER_1")
        
        # Week 2 data should still be visible
        rows = get_clean_data(db_conn, week="2026-01-16", tier="TIER_1")
        assert len(rows) > 0
    
    def test_readiness_updated(self, db_conn, valid_data):
        """Successful processing updates readiness."""
        pipeline.run()
        readiness = get_readiness(db_conn, domain, stage, partition)
        assert readiness["is_ready"] == 1
```

### 9. Documentation
Location: `docs/{FEATURE}.md`

Required sections:
- Overview (what does it protect/enable?)
- Components (tables, helpers, views)
- Usage examples (code + SQL)
- Behavior changes (before/after)
- Monitoring queries
- Edge cases handled
- Troubleshooting

---

MONITORING QUERIES:

```sql
-- Check anomalies by severity
SELECT 
    severity,
    category,
    COUNT(*) as count
FROM core_anomalies
WHERE domain = '{domain}'
  AND resolved_at IS NULL
GROUP BY severity, category
ORDER BY 
    CASE severity 
        WHEN 'CRITICAL' THEN 1 
        WHEN 'ERROR' THEN 2 
        WHEN 'WARN' THEN 3 
        ELSE 4 
    END;

-- Check data readiness
SELECT 
    week_ending,
    stage,
    is_ready,
    checked_at
FROM core_data_readiness
WHERE domain = '{domain}'
ORDER BY week_ending DESC, stage;

-- Completeness trend
SELECT * FROM {domain}_{feature}_stats
ORDER BY week_ending DESC, tier;
```

---

ANTI-PATTERNS TO AVOID:
- ❌ Modifying core table schemas
- ❌ Global anomaly filtering (must scope by partition)
- ❌ Runtime CREATE VIEW
- ❌ Silent failures (always record anomaly)
- ❌ Hardcoding schedules (use core_expected_schedules)
- ❌ Crashing on quality gate failure (skip gracefully)

---

EXPECTED FILES:
```
spine-domains/src/spine/domains/{domain}/validators.py    [NEW or UPDATED]
spine-domains/src/spine/domains/{domain}/pipelines.py     [UPDATED]
spine-domains/src/spine/domains/{domain}/schema/02_views.sql [UPDATED]
tests/{domain}/test_{feature}.py                          [NEW]
docs/{FEATURE}.md                                         [NEW]
README.md                                                 [UPDATED]
```

---

DEFINITION OF DONE:
- [ ] Core tables identified and usage documented
- [ ] Helper functions in validators.py
- [ ] Quality gate integrated in pipeline
- [ ] Anomaly recording with correct severity/category
- [ ] Scoped filtering (partition_key match)
- [ ] Views in schema/02_views.sql
- [ ] Readiness tracking updated
- [ ] 6+ tests including scoped filtering test
- [ ] Documentation with monitoring queries

PROCEED with Change Surface Map, then implementation.
```

---

## Workflow-Based Scheduling

For multi-step scheduled operations, use **Workflow** instead of PipelineGroup.

### PipelineGroup vs Workflow

| Feature | PipelineGroup (v1) | Workflow (v2) |
|---------|-------------------|---------------|
| Data passing between steps | ❌ No | ✅ Yes |
| Validation between steps | ❌ No | ✅ Lambda steps |
| Step-level metrics | ❌ No | ✅ Yes |
| Conditional branching | ❌ No | ✅ Choice steps |
| Context awareness | ❌ No | ✅ WorkflowContext |
| Quality gates | ❌ External | ✅ Built-in |

**Recommendation**: Use Workflow for new multi-step scheduled operations.

### Example: Scheduled Workflow

```python
from spine.orchestration import Workflow, WorkflowRunner, Step, StepResult


def check_data_readiness(ctx, config):
    """Lambda: Check data readiness before processing."""
    conn = config.get("conn")
    date_str = ctx.params.get("date")
    
    # Query core_data_readiness (passed via context)
    result = conn.execute("""
        SELECT is_ready FROM core_data_readiness
        WHERE domain = ? AND stage = 'INGEST' AND week_ending = ?
    """, ("{domain}", date_str)).fetchone()
    
    if not result or not result[0]:
        return StepResult.fail("Data not ready for processing", "SCHEDULE")
    
    return StepResult.ok(output={"data_ready": True})


def check_quality(ctx, config):
    """Lambda: Validate quality before final aggregation."""
    result = ctx.get_output("validate_pipeline")
    if result.get("error_count", 0) > 0:
        return StepResult.fail("Quality check failed", "QUALITY_GATE")
    return StepResult.ok()


DAILY_REFRESH = Workflow(
    name="daily.{domain}.refresh",
    domain="{domain}",
    description="Daily scheduled refresh: check → fetch → validate → aggregate",
    steps=[
        Step.lambda_("check_readiness", check_data_readiness),
        Step.pipeline("fetch", "{domain}.fetch_daily"),
        Step.pipeline("validate", "{domain}.quality_check"),
        Step.lambda_("check_quality", check_quality),
        Step.pipeline("aggregate", "{domain}.daily_aggregates"),
    ],
)
```

### Scheduler Integration

```python
from spine.orchestration import WorkflowRunner
from spine.core.manifest import WorkManifest

def run_scheduled_workflow(workflow, params, conn):
    """Execute workflow with tracking."""
    
    # Initialize manifest
    manifest = WorkManifest(
        conn,
        domain=f"workflow.{workflow.name}",
        stages=["STARTED", "READY_CHECK", "FETCHED", "VALIDATED", "COMPLETED"]
    )
    
    partition_key = {"date": params.get("date")}
    
    # Record start
    manifest.advance_to(partition_key, "STARTED")
    
    # Execute workflow
    runner = WorkflowRunner()
    result = runner.execute(workflow, params=params, config={"conn": conn})
    
    if result.status == WorkflowStatus.COMPLETED:
        manifest.advance_to(
            partition_key, 
            "COMPLETED",
            execution_id=result.run_id,
            step_count=len(result.completed_steps),
            duration_seconds=result.duration_seconds,
        )
    else:
        # Record failure to core_anomalies
        conn.execute("""
            INSERT INTO core_anomalies (
                anomaly_id, domain, stage, partition_key,
                severity, category, message, detected_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            "{domain}",
            f"workflow.{result.error_step}",
            str(partition_key),
            "ERROR",
            "WORKFLOW_FAILURE",
            result.error,
            datetime.utcnow().isoformat(),
            json.dumps({"workflow": workflow.name, "run_id": result.run_id}),
        ))
    
    return result
```

### Monitoring Workflow Executions

```sql
-- Check workflow stage progress
SELECT 
    partition_key,
    stage,
    execution_id,
    updated_at
FROM core_manifest
WHERE domain LIKE 'workflow.%'
ORDER BY updated_at DESC
LIMIT 20;

-- Check workflow failures
SELECT 
    partition_key,
    stage,
    message,
    detected_at
FROM core_anomalies
WHERE category = 'WORKFLOW_FAILURE'
  AND resolved_at IS NULL
ORDER BY detected_at DESC;
```

---

## Related Documents

- [../CONTEXT.md](../CONTEXT.md) - Core tables reference
- [../reference/QUALITY_GATES.md](../reference/QUALITY_GATES.md) - Quality gate patterns
- [../ANTI_PATTERNS.md](../ANTI_PATTERNS.md) - Scoped filtering rules
- [F_WORKFLOW.md](F_WORKFLOW.md) - Full workflow implementation guide
