# Definition of Done

**Universal checklist for ANY feature implementation. Every item must be checked before a feature is considered complete.**

---

## Quick Checklist (Copy-Paste)

```markdown
## Definition of Done

### Planning
- [ ] Change Surface Map created and validated
- [ ] Correct prompt selected (Master/A/B/C/D)
- [ ] Anti-patterns reviewed

### Code Quality
- [ ] Changes in correct layer (domains > app > core)
- [ ] Minimal scope (only files that need to change)
- [ ] No anti-patterns introduced
- [ ] Registry-driven (no if/elif factories)

### Data Integrity
- [ ] Capture ID in all outputs
- [ ] Idempotency: same capture_id reruns work
- [ ] Determinism: same inputs → same outputs
- [ ] Versioning: calculations have version field
- [ ] Provenance: rolled-up data tracks input captures

### Error Handling
- [ ] Errors recorded in core_anomalies
- [ ] Severity/category set correctly
- [ ] Partition_key scoped for filtering
- [ ] No silent failures
- [ ] Partial success supported

### Schema & Database
- [ ] Tables in schema/00_tables.sql
- [ ] Views in schema/02_views.sql
- [ ] build_schema.py run
- [ ] No runtime DDL
- [ ] Migrations backward compatible

### Tests
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing
- [ ] Determinism test written and passing
- [ ] Idempotency test written and passing
- [ ] Fitness test written (if multi-pipeline)
- [ ] All tests passing (100%)

### Documentation
- [ ] docs/{FEATURE}.md created
- [ ] README.md updated
- [ ] Usage examples included
- [ ] Monitoring queries documented
- [ ] Edge cases documented

### Operational
- [ ] Readiness tracking updated (if applicable)
- [ ] Monitoring queries provided
- [ ] Alerting thresholds documented
- [ ] Runbooks created (if applicable)

### Review
- [ ] Self-review completed
- [ ] No spine-core changes (or escalation approved)
- [ ] Change surface map accurate
```

---

## Detailed Requirements

### Planning Phase

#### Change Surface Map
Before writing code, list every file that will change and why:

```markdown
## Change Surface Map

### Domain Layer
- [ ] src/spine/domains/finra/otc_transparency/pipelines.py 
      WHY: Add new rolling calculation pipeline

### Schema
- [ ] src/spine/domains/finra/otc_transparency/schema/00_tables.sql
      WHY: Add output table for new calculation

### Tests  
- [ ] tests/finra/otc_transparency/test_rolling.py
      WHY: Unit and integration tests for new pipeline

### Documentation
- [ ] docs/ROLLING_CALCULATION.md
      WHY: Document new feature
```

**Purpose:** Prevents scope creep, ensures minimal changes, documents rationale.

---

### Code Quality

#### Layering
| Layer | When to Use | Approval |
|-------|------------|----------|
| spine-domains | Domain-specific features | ✅ Default |
| spine-app | Thin CLI/API adapters | ⚠️ No business logic |
| spine-core | Framework changes | ❌ Requires escalation |

#### Registry Pattern
```python
# ✅ CORRECT
from spine.framework.registry import PIPELINES

@PIPELINES.register("compute_rolling")
class ComputeRollingPipeline(Pipeline):
    ...

# ❌ WRONG
if pipeline_type == "rolling":
    return ComputeRollingPipeline()
```

---

### Data Integrity

#### Capture ID Contract
Every output row MUST have:
```python
{
    "capture_id": "finra.otc.ROLLING.2026-01-09|T1.20260104T143022Z",
    "captured_at": "2026-01-04T14:30:22Z",
    "execution_id": "exec-abc123",
    "batch_id": "batch-xyz789"
}
```

#### Idempotency Test
```python
def test_idempotency():
    # Run twice with same capture_id
    result1 = run_pipeline(capture_id="test.1")
    result2 = run_pipeline(capture_id="test.1")
    
    # Should update, not duplicate
    count = conn.execute("SELECT COUNT(*) FROM output").fetchone()[0]
    assert count == expected_count  # Not 2x
```

#### Determinism Test
```python
def test_determinism():
    result1 = run_pipeline(params)
    result2 = run_pipeline(params)
    
    # Compare excluding audit fields
    assert_equal_excluding(
        result1, result2,
        exclude=["captured_at", "batch_id", "execution_id"]
    )
```

#### Provenance Tracking
For rolled-up data:
```python
{
    "input_min_capture_id": "earliest-input-capture",
    "input_max_capture_id": "latest-input-capture",
    "input_min_captured_at": "2026-01-01T00:00:00Z",
    "input_max_captured_at": "2026-01-04T00:00:00Z"
}
```

---

### Error Handling

#### Anomaly Recording
```python
record_anomaly(
    domain="finra.otc_transparency",
    stage="ROLLING",
    partition_key="2026-01-09|NMS_TIER_1",
    severity="ERROR",  # DEBUG, INFO, WARN, ERROR, CRITICAL
    category="QUALITY_GATE",  # NETWORK, DATA_QUALITY, VALIDATION, etc.
    message="Insufficient history: missing 2 weeks",
    metadata={"missing_weeks": ["2025-11-29", "2025-12-06"]}
)
```

#### Partial Success
```python
def process_batch(items):
    successes = []
    failures = []
    
    for item in items:
        try:
            result = process_item(item)
            successes.append(result)
        except Exception as e:
            record_anomaly(...)
            failures.append(item.id)
    
    return {
        "processed": len(successes),
        "skipped": len(failures),
        "results": successes
    }
```

---

### Schema & Database

#### File Organization
```
schema/
├── 00_tables.sql    # CREATE TABLE statements
├── 01_indexes.sql   # CREATE INDEX statements (optional)
└── 02_views.sql     # CREATE VIEW statements
```

#### View Definition (NOT Runtime)
```sql
-- In schema/02_views.sql
CREATE VIEW IF NOT EXISTS my_domain_latest AS
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY week_ending, tier, symbol 
               ORDER BY captured_at DESC
           ) as rn
    FROM my_domain_table
) WHERE rn = 1;
```

#### Build Process
```bash
python scripts/build_schema.py
# Verify:
sqlite3 :memory: < schema.sql
```

---

### Tests

#### Required Test Types

| Test Type | Purpose | Required? |
|-----------|---------|-----------|
| Unit | Individual functions | ✅ Always |
| Integration | Full pipeline + DB | ✅ Always |
| Determinism | Same input → same output | ✅ Always |
| Idempotency | Same capture_id twice | ✅ Always |
| Fitness | Multi-pipeline workflow | ⚠️ If multi-pipeline |

#### Test File Template
```python
"""Tests for {feature}."""
import pytest
from spine.domains.finra.otc_transparency.pipelines import MyPipeline

class TestMyFeature:
    """Unit tests for MyFeature."""
    
    def test_basic_functionality(self, db_conn):
        """Happy path test."""
        pass
    
    def test_edge_case_empty_input(self, db_conn):
        """Handle empty input gracefully."""
        pass
    
    def test_edge_case_single_item(self, db_conn):
        """Handle single item."""
        pass


class TestMyFeatureIntegration:
    """Integration tests with real database."""
    
    def test_full_pipeline(self, db_conn, fixtures):
        """Run complete pipeline."""
        pass
    
    def test_determinism(self, db_conn, fixtures):
        """Same inputs produce same outputs."""
        pass
    
    def test_idempotency(self, db_conn, fixtures):
        """Same capture_id doesn't duplicate."""
        pass
```

---

### Documentation

#### Required Sections
```markdown
# Feature Name

## Overview
What this feature does and why it exists.

## Components Implemented
- Files created/modified
- Tables/views added
- Pipelines registered

## Usage Examples

### Python API
```python
# Code example
```

### SQL Queries
```sql
-- Query example
```

## Behavior Changes
| Before | After |
|--------|-------|
| Old behavior | New behavior |

## Edge Cases
- How empty input is handled
- How errors are surfaced
- Partial success scenarios

## Monitoring
```sql
-- Anomaly check
SELECT * FROM core_anomalies WHERE domain = '...'
```

## Performance Considerations
- Index recommendations
- Query optimization tips
```

---

### Review Checklist

Before submitting, verify:

```markdown
## Self-Review

### Code
- [ ] I ran all tests locally
- [ ] I checked for anti-patterns
- [ ] I verified the change surface map is accurate

### Data
- [ ] I tested with real data (not just mocks)
- [ ] I verified idempotency manually
- [ ] I checked determinism with multiple runs

### Documentation
- [ ] I wrote docs before forgetting details
- [ ] Examples in docs actually run
- [ ] Monitoring queries are tested

### Edge Cases
- [ ] Empty input handled
- [ ] Single item handled
- [ ] Error cases logged properly
```

---

## Related Documents

- [MASTER_PROMPT.md](MASTER_PROMPT.md) - Implementation guidance
- [ANTI_PATTERNS.md](ANTI_PATTERNS.md) - What not to do
- [prompts/E_REVIEW.md](prompts/E_REVIEW.md) - Full review checklist
