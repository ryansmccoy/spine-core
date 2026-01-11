# 05 — Test Strategy and Fixtures

> **Fixtures layout, golden vs invariant testing, and smoke test patterns**

---

## 1. Test Pyramid

```
           ╱╲
          ╱  ╲
         ╱ E2E╲          ← Smoke tests (5-10)
        ╱──────╲
       ╱        ╲
      ╱ Integration╲     ← Pipeline tests (20-30)
     ╱──────────────╲
    ╱                ╲
   ╱   Unit Tests     ╲  ← Calc functions (50-100)
  ╱────────────────────╲
```

### Test Categories

| Category | Location | Purpose | Runtime |
|----------|----------|---------|---------|
| Unit | `tests/unit/` | Pure functions | < 1s each |
| Integration | `tests/integration/` | Pipeline + DB | < 5s each |
| Smoke | `scripts/smoke_*.py` | End-to-end | < 60s total |
| Fitness | `tests/fitness/` | Architecture invariants | < 30s total |

---

## 2. Fixture Layout

### Directory Structure

```
tests/
├── fixtures/
│   ├── finra/
│   │   ├── otc_transparency/
│   │   │   ├── raw/                    # Raw input fixtures
│   │   │   │   ├── sample_week.csv
│   │   │   │   └── edge_cases.csv
│   │   │   ├── expected/               # Golden outputs
│   │   │   │   ├── venue_volume.json
│   │   │   │   ├── symbol_summary.json
│   │   │   │   ├── venue_concentration.json
│   │   │   │   └── top_n_symbols.json
│   │   │   └── scenarios/              # Test scenarios
│   │   │       ├── replay_idempotent/
│   │   │       ├── backfill_range/
│   │   │       └── multi_capture/
│   └── core/
│       └── ...
├── conftest.py                         # Shared fixtures
├── unit/
│   └── test_calculations.py
├── integration/
│   └── test_pipelines.py
└── fitness/
    ├── test_calc_invariants.py
    ├── test_db_constraints.py
    └── test_scale.py
```

### Fixture Naming Convention

```
{domain}_{entity}_{scenario}_{variant}.{ext}

Examples:
  finra_otc_transparency_raw_minimal.csv
  finra_otc_transparency_raw_50k_rows.csv
  finra_otc_transparency_expected_venue_concentration_v1.json
```

### Fixture Loading

```python
# tests/conftest.py

from pathlib import Path
import json
import csv

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def load_fixture_csv(path: str) -> list[dict]:
    """Load CSV fixture as list of dicts."""
    with open(FIXTURES_DIR / path) as f:
        return list(csv.DictReader(f))

def load_fixture_json(path: str) -> dict | list:
    """Load JSON fixture."""
    with open(FIXTURES_DIR / path) as f:
        return json.load(f)

def load_expected(calc_name: str, version: str = "v1") -> list[dict]:
    """Load expected output for a calculation."""
    path = f"finra/otc_transparency/expected/{calc_name}_{version}.json"
    return load_fixture_json(path)

# Pytest fixtures
@pytest.fixture
def raw_fixture():
    return load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")

@pytest.fixture
def minimal_venue_rows():
    """Minimal fixture for unit tests."""
    return [
        VenueVolumeRow(
            week_ending=date(2025, 12, 26),
            tier=Tier.OTC,
            symbol="AAPL",
            mpid="ETRD",
            total_shares=1000,
            total_trades=10,
        ),
        VenueVolumeRow(
            week_ending=date(2025, 12, 26),
            tier=Tier.OTC,
            symbol="AAPL",
            mpid="SCHW",
            total_shares=500,
            total_trades=5,
        ),
    ]
```

---

## 3. Golden vs Invariant Testing

### When to Use Each

| Use Golden Tests When... | Use Invariant Tests When... |
|--------------------------|----------------------------|
| Output format is critical | Output values may change |
| Regression detection needed | Testing mathematical properties |
| Small, stable fixtures | Large or generated data |
| API contracts | Internal calculations |

### Golden Test Pattern

```python
def test_venue_concentration_golden():
    """Output matches expected golden file."""
    # Arrange
    input_rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    expected = load_expected("venue_concentration", "v1")
    
    # Act
    result = compute_venue_concentration_v1(parse_rows(input_rows))
    
    # Assert - exact match
    actual = [asdict(r) for r in result]
    assert actual == expected

def test_venue_concentration_update_golden():
    """Helper to update golden file when intentionally changing."""
    input_rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    result = compute_venue_concentration_v1(parse_rows(input_rows))
    
    # Write new golden
    with open(FIXTURES_DIR / "finra/otc_transparency/expected/venue_concentration_v1.json", "w") as f:
        json.dump([asdict(r) for r in result], f, indent=2, default=str)
```

### Invariant Test Patterns

```python
def test_shares_sum_to_one():
    """Market shares must sum to 1.0 for each (week, tier)."""
    rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    result = compute_venue_concentration_v1(parse_rows(rows))
    
    # Group by (week, tier)
    by_group = defaultdict(list)
    for r in result:
        by_group[(r.week_ending, r.tier)].append(r)
    
    # Check invariant
    for (week, tier), group in by_group.items():
        total = sum(r.market_share_pct for r in group)
        assert abs(total - 1.0) < 0.0001, f"{week}/{tier}: {total}"

def test_ranks_are_consecutive():
    """Ranks must be 1, 2, 3... with no gaps."""
    rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    result = compute_top_n_symbols_v1(parse_rows(rows), n=10)
    
    by_group = defaultdict(list)
    for r in result:
        by_group[(r.week_ending, r.tier)].append(r)
    
    for (week, tier), group in by_group.items():
        ranks = sorted(r.rank for r in group)
        expected = list(range(1, len(ranks) + 1))
        assert ranks == expected, f"{week}/{tier}: ranks={ranks}"

def test_cumulative_share_increasing():
    """Cumulative share must monotonically increase."""
    rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    result = compute_top_n_symbols_v1(parse_rows(rows), n=10)
    
    by_group = defaultdict(list)
    for r in result:
        by_group[(r.week_ending, r.tier)].append(r)
    
    for group in by_group.values():
        sorted_group = sorted(group, key=lambda x: x.rank)
        for i in range(1, len(sorted_group)):
            assert sorted_group[i].cumulative_share_pct >= sorted_group[i-1].cumulative_share_pct

def test_hhi_bounds():
    """HHI must be between 0 and 1."""
    rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    _, metrics = compute_top_n_symbols_v1(parse_rows(rows))
    
    for m in metrics:
        assert 0.0 <= m.hhi <= 1.0, f"HHI out of bounds: {m.hhi}"

def test_volume_is_non_negative():
    """All volumes must be non-negative."""
    rows = load_fixture_csv("finra/otc_transparency/raw/sample_week.csv")
    result = compute_venue_concentration_v1(parse_rows(rows))
    
    for r in result:
        assert r.total_volume >= 0
        assert r.total_trades >= 0
```

---

## 4. Integration Test Patterns

### Pipeline + DB Tests

```python
@pytest.fixture
def test_db(tmp_path):
    """Create fresh test database."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.execute_script(Path("migrations/schema.sql").read_text())
    return db

def test_pipeline_writes_to_db(test_db):
    """Pipeline correctly writes to database."""
    runner = PipelineRunner(test_db)
    
    # Run ingest
    runner.run("ingest_week", week="2025-12-26", capture_id="test-001")
    
    # Verify
    rows = test_db.query("SELECT COUNT(*) FROM finra_otc_transparency_raw")
    assert rows[0][0] > 0

def test_replay_idempotent(test_db):
    """Same capture re-run produces identical results."""
    runner = PipelineRunner(test_db)
    
    # First run
    runner.run("aggregate_week", week="2025-12-26", capture_id="test-001")
    count_1 = test_db.query("SELECT COUNT(*) FROM finra_otc_transparency_symbol_summary")[0][0]
    
    # Replay
    runner.run("aggregate_week", week="2025-12-26", capture_id="test-001")
    count_2 = test_db.query("SELECT COUNT(*) FROM finra_otc_transparency_symbol_summary")[0][0]
    
    assert count_1 == count_2

def test_constraint_violation_fails(test_db):
    """Duplicate insert violates unique constraint."""
    runner = PipelineRunner(test_db)
    
    # Insert directly (bypassing DELETE)
    test_db.execute("""
        INSERT INTO finra_otc_transparency_symbol_summary 
        (execution_id, batch_id, week_ending, tier, symbol, capture_id, captured_at)
        VALUES ('e1', 'b1', '2025-12-26', 'OTC', 'AAPL', 'cap-001', '2025-01-01')
    """)
    
    with pytest.raises(IntegrityError):
        test_db.execute("""
            INSERT INTO finra_otc_transparency_symbol_summary 
            (execution_id, batch_id, week_ending, tier, symbol, capture_id, captured_at)
            VALUES ('e1', 'b1', '2025-12-26', 'OTC', 'AAPL', 'cap-001', '2025-01-01')
        """)
```

---

## 5. Fitness Test Patterns

### DB Constraint Tests

```python
# tests/fitness/test_db_constraints.py

class TestUniqueConstraints:
    """Every table enforces uniqueness correctly."""
    
    @pytest.mark.parametrize("table,unique_cols", [
        ("finra_otc_transparency_symbol_summary", ["week_ending", "tier", "symbol", "capture_id"]),
        ("finra_otc_transparency_venue_concentration", ["week_ending", "tier", "mpid", "capture_id", "calc_version"]),
    ])
    def test_unique_constraint_enforced(self, test_db, table, unique_cols):
        """Inserting duplicate unique key fails."""
        # Build insert with same values for unique cols
        values = {col: "test_value" for col in unique_cols}
        # ... insert twice, expect IntegrityError on second

class TestIdempotency:
    """Replay operations are idempotent."""
    
    def test_delete_insert_pattern(self, test_db):
        """DELETE + INSERT produces same result as fresh INSERT."""
        pass

class TestTemporalQueries:
    """Latest and as-of queries work correctly."""
    
    def test_latest_view_returns_newest(self, test_db):
        pass
    
    def test_as_of_returns_historical(self, test_db):
        pass
```

### Calc Invariant Tests

```python
# tests/fitness/test_calc_invariants.py

class TestVenueConcentration:
    """Venue concentration invariants."""
    
    def test_shares_sum_to_one(self, venue_rows):
        pass
    
    def test_ranks_unique_per_group(self, venue_rows):
        pass

class TestTopNSymbols:
    """Top-N symbols invariants."""
    
    def test_cumulative_monotonic(self, symbol_rows):
        pass
    
    def test_top_n_matches_metrics(self, symbol_rows):
        pass
```

### Scale Tests

```python
# tests/fitness/test_scale.py

@pytest.mark.slow
class TestScale:
    """Scale and performance tests."""
    
    def test_50k_ingest_under_30s(self, test_db):
        pass
    
    def test_query_latest_under_500ms(self, test_db):
        pass
    
    def test_memory_bounded(self):
        pass
```

---

## 6. Smoke Test Updates

### Smoke Test Script

```python
# scripts/smoke_calcs.py
"""Smoke tests for calculation pipelines."""

import sys
from pathlib import Path
from datetime import date

def main():
    """Run calculation smoke tests."""
    print("=== Calculation Smoke Tests ===")
    
    # Setup
    db_path = Path("smoke_test.db")
    if db_path.exists():
        db_path.unlink()
    
    from spine.domains.finra.otc_transparency import pipelines
    runner = pipelines.PipelineRunner(db_path)
    
    # 1. Ingest
    print("\n1. Testing ingest_week...")
    runner.run("ingest_week", week="2025-12-26")
    raw_count = runner.db.query("SELECT COUNT(*) FROM finra_otc_transparency_raw")[0][0]
    assert raw_count > 0, f"Expected raw rows, got {raw_count}"
    print(f"   ✓ Ingested {raw_count} raw rows")
    
    # 2. Aggregate
    print("\n2. Testing aggregate_week...")
    runner.run("aggregate_week", week="2025-12-26")
    summary_count = runner.db.query("SELECT COUNT(*) FROM finra_otc_transparency_symbol_summary")[0][0]
    assert summary_count > 0, f"Expected summary rows, got {summary_count}"
    print(f"   ✓ Aggregated to {summary_count} symbol summaries")
    
    # 3. Venue concentration
    print("\n3. Testing compute_venue_concentration...")
    runner.run("compute_venue_concentration", week="2025-12-26")
    conc_count = runner.db.query("SELECT COUNT(*) FROM finra_otc_transparency_venue_concentration")[0][0]
    assert conc_count > 0, f"Expected concentration rows, got {conc_count}"
    
    # Invariant: shares sum to 1.0
    bad_sums = runner.db.query("""
        SELECT week_ending, tier, SUM(CAST(market_share_pct AS REAL)) as total
        FROM finra_otc_transparency_venue_concentration
        GROUP BY week_ending, tier
        HAVING ABS(total - 1.0) > 0.001
    """)
    assert len(bad_sums) == 0, f"Shares don't sum to 1.0: {bad_sums}"
    print(f"   ✓ Computed {conc_count} venue concentrations")
    print(f"   ✓ Shares sum to 1.0 ✓")
    
    # 4. Replay idempotency
    print("\n4. Testing replay idempotency...")
    runner.run("aggregate_week", week="2025-12-26")  # Replay
    summary_count_2 = runner.db.query("SELECT COUNT(*) FROM finra_otc_transparency_symbol_summary")[0][0]
    assert summary_count == summary_count_2, f"Replay changed count: {summary_count} → {summary_count_2}"
    print(f"   ✓ Replay produced same {summary_count_2} rows")
    
    # 5. Query latest view
    print("\n5. Testing latest view...")
    latest = runner.db.query("SELECT COUNT(*) FROM finra_otc_transparency_symbol_summary_latest")[0][0]
    assert latest > 0, f"Latest view empty"
    print(f"   ✓ Latest view has {latest} rows")
    
    # Cleanup
    db_path.unlink()
    
    print("\n=== All Smoke Tests Passed ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Running Smoke Tests

```bash
# Run all smoke tests
python scripts/smoke_calcs.py

# Run with verbose output
python scripts/smoke_calcs.py -v

# Run specific test
pytest tests/fitness/ -k "concentration" -v
```

---

## 7. Test Commands Summary

```bash
# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Fitness tests
pytest tests/fitness/ -v

# Slow/scale tests
pytest tests/fitness/test_scale.py -v --slow

# All tests
pytest tests/ -v

# Smoke tests
python scripts/smoke_calcs.py

# Coverage
pytest tests/ --cov=spine --cov-report=html

# Watch mode (requires pytest-watch)
ptw tests/unit/
```

---

## 8. Test Maintenance Checklist

### When Adding a New Calc

- [ ] Add unit tests for pure function (`tests/unit/test_calculations.py`)
- [ ] Add invariant tests (`tests/fitness/test_calc_invariants.py`)
- [ ] Add golden fixture (`tests/fixtures/.../expected/`)
- [ ] Add integration test for pipeline
- [ ] Update smoke test script

### When Changing a Calc

- [ ] Run existing tests to verify breakage
- [ ] Update golden fixtures if output format changed
- [ ] Add tests for new behavior
- [ ] Verify invariants still hold

### When Adding a Table

- [ ] Add constraint tests
- [ ] Add idempotency tests
- [ ] Add to scale test parameters
