# 02 — Calculation Contract & Conventions

> **Minimal but strong conventions for calc identity, versioning, and correctness.**

---

## Calc Identity Model

### Required Fields

Every calculation output must include:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `calc_name` | TEXT | Stable identifier | `"venue_concentration"` |
| `calc_version` | TEXT | Version tag | `"v1"`, `"v2"` |
| Business keys | varies | Natural key for the row | `week_ending`, `tier`, `symbol` |
| `capture_id` | TEXT | Links to source data capture | `"finra.otc....:a3f5b2"` |
| `captured_at` | TEXT | Timestamp of source capture | ISO datetime |
| `calculated_at` | TEXT | When this calc ran | ISO datetime |

### Naming Convention

**Table naming**: `{domain}_{calc_name}` or `{domain}_{calc_name}_{version}`

Decision: **Use column for version, not table suffix**.

Rationale:
- Simpler migrations (add rows, not tables)
- Single table for queries with version filter
- Views can expose `_latest` and `_v{N}` subsets

```sql
-- Single table with version column
CREATE TABLE finra_otc_transparency_venue_concentration (
    ...
    calc_version TEXT NOT NULL DEFAULT 'v1',
    ...
    UNIQUE(week_ending, tier, mpid, capture_id, calc_version)
);

-- View for latest version
CREATE VIEW finra_otc_transparency_venue_concentration_latest AS
SELECT * FROM finra_otc_transparency_venue_concentration
WHERE calc_version = (SELECT MAX(calc_version) FROM ...);
```

### Calc Registry (Convention, not framework)

Calcs are registered in `schema.py` with policy-driven version selection:

```python
# packages/spine-domains/src/spine/domains/finra/otc_transparency/schema.py

CALCS = {
    "venue_share": {
        "versions": ["v1"],
        "current": "v1",           # Policy-defined current version
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_venue_share",
        "business_keys": ["week_ending", "tier", "mpid"],
    },
    "symbol_summary": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_symbol_summary",
        "business_keys": ["week_ending", "tier", "symbol"],
    },
}

def get_current_version(calc_name: str) -> str:
    """Return policy-defined current version. Use instead of MAX(calc_version)."""
    return CALCS[calc_name]["current"]

def get_version_rank(calc_name: str, version: str) -> int:
    """Return numeric rank for ordering (v10 > v2)."""
    return int(version.lstrip("v"))

def is_deprecated(calc_name: str, version: str) -> bool:
    """Check if version is deprecated."""
    return version in CALCS[calc_name].get("deprecated", [])
```

**Why policy-driven, not MAX(calc_version)?**

MAX("v10") < MAX("v2") in string comparison! Use `get_current_version()` for correct selection.

### Registry Contract Invariants

> ⚠️ **These invariants are enforced by `test_fitness.py`** and must never be violated.

| # | Rule | Rationale |
|---|------|-----------|
| 1 | `current` MUST exist in `versions` | Ensures current version is valid |
| 2 | `current` MUST NOT be in `deprecated` | You cannot serve a deprecated calc as current |
| 3 | `deprecated` versions MUST exist in `versions` | Never remove versions—deprecate them |
| 4 | `versions` MUST NOT be empty | Every calc has at least one version |
| 5 | `business_keys` MUST NOT be empty | Every calc defines its natural key |
| 6 | `versions` SHOULD be sorted chronologically | Convention for readability |
| 7 | `table` SHOULD use domain prefix | Convention for namespace isolation |

### Migration Rules

```
✅ To add a new version:     append to versions[], leave current unchanged
✅ To activate new version:  update current to the new version
✅ To deprecate a version:   add to deprecated[], update current if needed
❌ NEVER remove a version from versions[] without full migration plan
❌ NEVER set current to a deprecated version
```
```

---

## Determinism & Replay

### What "Same Run" Means

A calc is **deterministic** if:
```
same(inputs, version) → same(outputs)
```

Inputs include:
- Source data (identified by `capture_id`)
- Calc version
- Business parameters (week_ending, tier, etc.)

**NOT inputs:**
- Wall-clock time (use `calculated_at` for audit only)
- Random seeds
- External state

### What May Change Across capture_ids

| Change Type | Allowed? | Example |
|-------------|----------|---------|
| Source data corrections | ✅ Yes | FINRA restates a file → new capture_id |
| Calc version upgrade | ✅ Yes | v1 → v2 changes formula |
| Historical recompute | ✅ Yes | Rerun old weeks with bug fix |
| Non-deterministic output | ❌ No | Random sampling, wall-clock in calc |

### Replay Contract

```python
# Replay for a specific capture must produce identical results
def test_calc_determinism():
    result1 = run_calc(week="2025-12-26", tier="OTC", capture_id="abc123")
    result2 = run_calc(week="2025-12-26", tier="OTC", capture_id="abc123")
    assert result1 == result2  # Byte-for-byte identical
```

### Deterministic vs Audit Fields

**Defined in `calculations.py`:**

```python
# Fields to EXCLUDE from deterministic comparison
AUDIT_FIELDS = frozenset({
    "calculated_at",   # Wall-clock when calc ran
    "ingested_at",     # Wall-clock when ingested
    "normalized_at",   # Wall-clock when normalized
    "computed_at",     # Wall-clock when computed
    "id",              # Auto-increment IDs
    "rn",              # Row numbers from window functions
})

def strip_audit_fields(row: dict) -> dict:
    """Strip audit-only fields for deterministic comparison."""
    return {k: v for k, v in row.items() if k not in AUDIT_FIELDS}

def rows_equal_deterministic(rows1, rows2) -> bool:
    """Compare rows ignoring audit fields."""
    stripped1 = [strip_audit_fields(r) for r in rows1]
    stripped2 = [strip_audit_fields(r) for r in rows2]
    return sorted(stripped1) == sorted(stripped2)
```

**Usage in tests:**

```python
def test_replay_deterministic():
    rows1 = run_calc(capture_id="abc")
    rows2 = run_calc(capture_id="abc")  # Replay
    
    # Different calculated_at, but deterministically equal
    assert rows_equal_deterministic(rows1, rows2)
```

---

## Invariants & Quality Checks

### Mandatory Invariant Patterns

Calcs MUST implement quality checks via `QualityRunner`:

#### 1. Share/Percentage Sums

```python
# venue_concentration: shares must sum to 1.0 per (week, tier)
def check_shares_sum_to_one(rows, tolerance=0.001):
    by_group = group_by(rows, ["week_ending", "tier"])
    for key, group in by_group.items():
        total = sum(r.market_share_pct for r in group)
        if abs(total - 1.0) > tolerance:
            quality.record_fail(
                check_name="shares_sum_to_one",
                category="BUSINESS_RULE",
                message=f"Shares sum to {total}, expected 1.0",
                actual_value=str(total),
                expected_value="1.0",
            )
```

#### 2. Bucket Counts

```python
# histogram calcs: bucket counts must equal total
def check_buckets_sum_to_total(rows):
    for row in rows:
        bucket_sum = sum([row.bucket_0_100, row.bucket_100_1k, ...])
        if bucket_sum != row.total_count:
            quality.record_fail(...)
```

#### 3. Non-Negative Constraints

```python
def check_non_negative(rows, fields):
    for row in rows:
        for field in fields:
            if getattr(row, field) < 0:
                quality.record_fail(
                    check_name=f"non_negative_{field}",
                    category="INTEGRITY",
                    message=f"{field} is negative: {getattr(row, field)}",
                )
```

#### 4. Record Counts

```python
# normalized + rejects <= raw
def check_record_counts(raw_count, normalized_count, reject_count):
    if normalized_count + reject_count != raw_count:
        quality.record_warn(
            check_name="record_count_balance",
            category="COMPLETENESS",
            message=f"raw={raw_count}, norm={normalized_count}, rej={reject_count}",
        )
```

### Quality Check Registration

Quality checks are recorded in `core_quality`:

```sql
SELECT * FROM core_quality
WHERE domain = 'finra_otc_transparency'
  AND partition_key LIKE '%2025-12-26%'
  AND status = 'FAIL';
```

---

## Dataclass Contracts

### CalcOutput Protocol

All calc outputs should follow this pattern:

```python
from dataclasses import dataclass
from datetime import date
from typing import Protocol

class CalcOutput(Protocol):
    """Protocol for calculation outputs."""
    calc_name: str
    calc_version: str
    capture_id: str
    captured_at: str
    calculated_at: str

@dataclass
class VenueConcentrationRow:
    """Venue concentration calculation output."""
    # Business keys
    week_ending: date
    tier: str
    mpid: str
    
    # Calc output
    total_volume: int
    total_trades: int
    symbol_count: int
    market_share_pct: float
    rank: int
    
    # Calc identity
    calc_name: str = "venue_concentration"
    calc_version: str = "v1"
    
    # Capture identity (propagated from source)
    capture_id: str = ""
    captured_at: str = ""
    
    # Audit
    calculated_at: str = ""
```

---

## Version Selection Rules

### Query Behavior

| Query Type | Behavior |
|------------|----------|
| No version specified | Return latest version (`calc_version = current`) |
| Explicit version | Return that version only |
| All versions | Return all (for comparison/audit) |

### Implementation

```python
def query_venue_concentration(
    week_ending: str,
    tier: str,
    version: str | None = None,  # None = latest
) -> list[VenueConcentrationRow]:
    if version is None:
        # Use _latest view
        return query("SELECT * FROM venue_concentration_latest WHERE ...")
    else:
        return query("SELECT * FROM venue_concentration WHERE calc_version = ?", version)
```

### CLI Interface

```bash
# Default: latest version
spine query venue-concentration -p tier=OTC -p week_ending=2025-12-26

# Explicit version
spine query venue-concentration -p tier=OTC -p week_ending=2025-12-26 --calc-version=v1
```

---

## Migration Discipline

### Adding a New Calc Version

1. **Update schema.py** — Add version to `CALCS` registry
2. **Add migration** — `ALTER TABLE` or new view (no schema change if column-based)
3. **Implement calc function** — New function `calc_v2()`
4. **Wire to pipeline** — Version parameter selects function
5. **Update docs** — Changelog for consumers
6. **Deprecate old version** — Mark in registry, add warning

### Backfilling New Versions

```bash
# Backfill v2 for all historical weeks
spine run finra.otc_transparency.compute_venue_concentration \
    -p start_date=2025-01-01 \
    -p end_date=2025-12-26 \
    -p tier=OTC \
    -p calc_version=v2 \
    -p force=true
```

Backfill creates new rows with `calc_version=v2`, preserving v1 rows for audit.
