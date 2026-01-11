# OTC Multi-Week Real Example: Implementation Plan

> **Purpose**: This directory contains the complete implementation specification for the Market Spine Basic real multi-week OTC workflow. Each file covers a specific aspect of the implementation.

---

## Document Index

| File | Contents |
|------|----------|
| [00-overview.md](00-overview.md) | This file - overview and file structure |
| [01-schema-migration.md](01-schema-migration.md) | SQLite migration with all new tables |
| [02-models-and-types.md](02-models-and-types.md) | Domain models, value objects, enums |
| [03-pipelines-ingest.md](03-pipelines-ingest.md) | `otc.ingest_week` pipeline implementation |
| [04-pipelines-normalize.md](04-pipelines-normalize.md) | `otc.normalize_week` pipeline implementation |
| [05-pipelines-aggregate.md](05-pipelines-aggregate.md) | `otc.aggregate_week` pipeline implementation |
| [06-pipelines-rolling.md](06-pipelines-rolling.md) | `otc.compute_rolling_6w` pipeline implementation |
| [07-pipelines-snapshot.md](07-pipelines-snapshot.md) | `otc.research_snapshot_week` pipeline implementation |
| [08-pipelines-backfill.md](08-pipelines-backfill.md) | `otc.backfill_range` orchestration pipeline |
| [09-fixtures.md](09-fixtures.md) | Test fixture files and format |
| [10-golden-tests.md](10-golden-tests.md) | Pytest golden tests with assertions |
| [11-cli-examples.md](11-cli-examples.md) | CLI usage examples |
| [12-checklist.md](12-checklist.md) | Reviewer verification checklist |

---

## File Tree Changes

```
market-spine-basic/
├── migrations/
│   └── 021_otc_multiweek_real_example.sql    # NEW: All schema changes
│
├── src/spine/
│   └── domains/
│       └── otc/
│           ├── __init__.py
│           ├── models.py                      # NEW: Domain models + value objects
│           ├── enums.py                       # NEW: Tier, Stage, QualityStatus enums
│           ├── validators.py                  # NEW: WeekEnding, Symbol validation
│           ├── parser.py                      # MODIFY: Use new models
│           ├── pipelines/                     # NEW: Pipeline package
│           │   ├── __init__.py
│           │   ├── ingest_week.py
│           │   ├── normalize_week.py
│           │   ├── aggregate_week.py
│           │   ├── compute_rolling.py
│           │   ├── research_snapshot.py
│           │   └── backfill_range.py
│           ├── calculations.py                # MODIFY: Add versioning
│           └── quality_checks.py              # NEW: Quality check logic
│
├── data/
│   └── fixtures/
│       └── otc/
│           ├── README.md                      # Fixture documentation
│           ├── week_2025-11-21.psv            # 6 fixture files
│           ├── week_2025-11-28.psv
│           ├── week_2025-12-05.psv
│           ├── week_2025-12-12.psv
│           ├── week_2025-12-19.psv
│           └── week_2025-12-26.psv
│
└── tests/
    └── domains/
        └── otc/
            ├── __init__.py
            ├── test_backfill_golden.py        # NEW: Golden tests
            ├── test_pipelines_unit.py         # NEW: Unit tests
            └── conftest.py                    # NEW: Pytest fixtures
```

---

## Design Principles (Frozen for Basic Tier)

### 1. Synchronous Execution Only
All pipelines run in-process, blocking. No async, no queues, no workers.

```python
# This is how backfill works in Basic:
for week in week_list:
    ingest_result = run_pipeline("otc.ingest_week", params)
    normalize_result = run_pipeline("otc.normalize_week", params)
    aggregate_result = run_pipeline("otc.aggregate_week", params)
```

### 2. SQLite Only
Single database file. All tables in one schema. Connection pooling via `sqlite3` stdlib.

### 3. Dispatcher/Runner/Registry Intact
Pipelines register themselves. Dispatcher submits. Runner executes. No changes to this pattern.

### 4. Small, Readable Python
Each pipeline is one class in one file. No abstract base class explosion. Comments explain "why."

### 5. Week is the Unit of Work
Every pipeline operates on a single `(week_ending, tier)` pair. Multi-week is a loop over single-week operations.

---

## Key Concepts

### Week Ending Validation
OTC data is published every Friday. `week_ending` must always be a Friday.

```python
def validate_week_ending_is_friday(week_ending: str) -> date:
    """Validate and return date. Raise ValueError if not Friday."""
    d = date.fromisoformat(week_ending)
    if d.weekday() != 4:  # Friday = 4
        raise ValueError(f"week_ending must be Friday, got {d.strftime('%A')}")
    return d
```

### Natural Keys
These composite keys are domain invariants:

| Table | Natural Key |
|-------|-------------|
| `otc_venue_volume` | `(week_ending, tier, symbol, mpid)` |
| `otc_symbol_summary` | `(week_ending, tier, symbol)` |
| `otc_venue_share` | `(week_ending, tier, mpid)` |
| `otc_symbol_rolling_6w` | `(week_ending, tier, symbol)` |
| `otc_research_snapshot` | `(week_ending, tier, symbol)` |

### Idempotency Levels
Each pipeline documents its idempotency:

| Level | Name | Behavior |
|-------|------|----------|
| L2 | Input-Idempotent | Same input → same records (via hash dedup) |
| L3 | State-Idempotent | Re-run → DELETE + INSERT (same final state) |

### Execution Lineage
Every data record tracks:
- `execution_id`: Which pipeline run created it
- `batch_id`: Which backfill group it belongs to

---

## Pipeline Dependency Graph

```
backfill_range (orchestrator)
│
├── For each week in range:
│   │
│   ├── ingest_week
│   │   └── writes: otc_raw, otc_week_manifest, otc_rejects
│   │
│   ├── normalize_week (depends on ingest)
│   │   └── writes: otc_venue_volume, otc_normalization_map, otc_rejects
│   │
│   └── aggregate_week (depends on normalize)
│       └── writes: otc_symbol_summary, otc_venue_share, otc_quality_checks
│
├── After all weeks:
│   │
│   ├── compute_rolling_6w
│   │   └── writes: otc_symbol_rolling_6w
│   │
│   └── research_snapshot_week (for latest week)
│       └── writes: otc_research_snapshot
```

---

## Quick Start (After Implementation)

```powershell
# 1. Initialize database
spine db init

# 2. Run 6-week backfill with fixtures
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc

# 3. Query rolling metrics
spine run otc.query_rolling -p tier=NMS_TIER_1

# 4. Check manifest status
sqlite3 spine.db "SELECT week_ending, stage, row_count_inserted FROM otc_week_manifest"

# 5. Check quality results
sqlite3 spine.db "SELECT check_name, status, check_value FROM otc_quality_checks LIMIT 10"
```

---

## Next: Read [01-schema-migration.md](01-schema-migration.md) for database schema
