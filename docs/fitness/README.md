# Architecture Fitness Tests — Index

> **Purpose**: Validate institutional-grade calculation lifecycle and database hardening via structured stress tests.

---

## Quick Commands

```bash
# Run all fitness tests
cd market-spine-basic
python -m pytest tests/test_fitness.py -v

# Run smoke test (includes calc pipelines)
python scripts/smoke_test.py

# Run all unit tests
python -m pytest tests/ -v

# Run venue share pipeline
spine run finra.otc_transparency.compute_venue_share -p week_ending=2025-12-26 -p tier=OTC
```

---

## Document Index

| Doc | Purpose |
|-----|---------|
| [01-current-state-map.md](01-current-state-map.md) | Where calcs live, tables exist, constraints enforced |
| [02-calc-contract-and-conventions.md](02-calc-contract-and-conventions.md) | Calc identity model, versioning, determinism rules |
| [03-calc-lifecycle-scenarios.md](03-calc-lifecycle-scenarios.md) | CREATE / CHANGE / VERSION / DEPRECATE / DELETE |
| [04-db-schema-and-index-policy.md](04-db-schema-and-index-policy.md) | Constraints, indexes, replay correctness |
| [05-test-strategy-and-fixtures.md](05-test-strategy-and-fixtures.md) | Fixture layout, golden vs invariants, smoke tests |
| [06-add-datasource-playbook.md](06-add-datasource-playbook.md) | Playbook for adding new data sources (verified: 19 tests) |

---

## Stress Test Matrix

| Test Area | Scenario | Status | Test File |
|-----------|----------|--------|-----------|
| Uniqueness | Duplicate insert fails | ✅ | `test_fitness.py::TestUniquenessConstraints` |
| Uniqueness | Different capture succeeds | ✅ | `test_fitness.py::TestUniquenessConstraints` |
| Replay | DELETE + INSERT idempotent | ✅ | `test_fitness.py::TestReplayIdempotency` |
| Versioning | Policy-driven version selection | ✅ | `test_fitness.py::TestCalcVersionRegistry` |
| Versioning | v10 > v2 ordering | ✅ | `test_fitness.py::TestCalcVersionRegistry` |
| Versioning | Registry contract invariants | ✅ | `test_fitness.py::TestCalcVersionRegistry` |
| Versioning | Deprecation surfacing | ✅ | `test_fitness.py::TestCalcVersionRegistry` |
| Determinism | Strip audit fields | ✅ | `test_fitness.py::TestDeterminism` |
| Determinism | rows_equal_deterministic | ✅ | `test_fitness.py::TestDeterminism` |
| Venue Share | Shares sum to 1.0 | ✅ | `test_fitness.py::TestVenueShareCalc` |
| Venue Share | Ranks consecutive | ✅ | `test_fitness.py::TestVenueShareCalc` |
| Venue Share | Pipeline runs | ✅ | `test_fitness.py::TestVenueSharePipeline` |
| Missing Data | Empty input handled | ✅ | `test_fitness.py::TestMissingDataBehavior` |
| Missing Data | Zero volume handled | ✅ | `test_fitness.py::TestMissingDataBehavior` |
| Missing Data | Invalid data detected | ✅ | `test_fitness.py::TestMissingDataBehavior` |
| Missing Data | Unknown calc fails loudly | ✅ | `test_fitness.py::TestMissingDataBehavior` |
| Sources | File + API abstraction | ✅ | `test_sources.py` (19 tests) |

---

## Architecture Invariants

These invariants are enforced by tests:

1. **Domain purity**: `spine.domains.*` never imports `sqlite3`, `fastapi`, or app-layer code
2. **Calc determinism**: Same inputs → same outputs (no random, no wall-clock in calcs)
3. **Capture propagation**: Every output row has `capture_id` tracing to raw data
4. **Idempotency**: Rerunning with same params is safe (skip or identical output)
5. **Share invariants**: Venue shares sum to 1.0 per (week, tier)
6. **Version policy**: Use `get_current_version()`, not `MAX(calc_version)`
7. **Registry contract**: Current version never deprecated, deprecated versions preserved

---

## Deprecation Surfacing

When a calc version is deprecated:

### API Responses

```json
{
  "calc_name": "venue_share",
  "calc_version": "v1",
  "is_current": true,
  "deprecated": false,
  "deprecation_warning": null
}
```

For deprecated versions:

```json
{
  "calc_name": "venue_share",
  "calc_version": "v0",
  "is_current": false,
  "deprecated": true,
  "deprecation_warning": "DEPRECATED: venue_share v0 is deprecated. Use version 'v1' instead."
}
```

### CLI Integration

```python
from spine.domains.finra.otc_transparency.schema import check_deprecation_warning

warning = check_deprecation_warning("venue_share", requested_version)
if warning:
    print(f"⚠️  {warning}", file=sys.stderr)
```

### Documentation Badge

Use this badge in calc documentation for deprecated versions:

```markdown
> ⚠️ **DEPRECATED**: This calc version is deprecated. Use `v2` instead.
```

---

## Key Implementation Files

| Component | File |
|-----------|------|
| Calc registry | [schema.py](../../packages/spine-domains/src/spine/domains/finra/otc_transparency/schema.py) |
| Venue share calc | [calculations.py](../../packages/spine-domains/src/spine/domains/finra/otc_transparency/calculations.py) |
| Venue share pipeline | [pipelines.py](../../packages/spine-domains/src/spine/domains/finra/otc_transparency/pipelines.py) |
| Source abstraction | [sources.py](../../packages/spine-domains/src/spine/domains/finra/otc_transparency/sources.py) |
| Fitness tests | [test_fitness.py](../../market-spine-basic/tests/test_fitness.py) |
| Source tests | [test_sources.py](../../market-spine-basic/tests/test_sources.py) |
