# 10: Golden Tests

> **Purpose**: Pytest tests that verify the full backfill workflow produces correct, predictable results against the fixture data.

---

## Test Strategy

### Categories

1. **Unit Tests**: Test individual components (validators, calculations)
2. **Integration Tests**: Test single pipelines with database
3. **Golden Tests**: Test full workflow against fixtures with known expected results

### Key Assertions

A golden test should verify:
- ✅ Manifest created for all 6 weeks
- ✅ Correct stage progression (INGESTED → NORMALIZED → AGGREGATED → ROLLING → SNAPSHOT)
- ✅ Rejects table contains expected bad records
- ✅ Rolling has `weeks_in_window == 6` and `is_complete_window == 1` for all symbols
- ✅ Snapshot contains expected totals for specific symbols
- ✅ Quality checks exist and PASS for valid weeks
- ✅ Batch ID links all records across tables

---

## Test Files

### `tests/domains/otc/conftest.py`

```python
"""
Pytest fixtures for OTC domain tests.
"""
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from spine.core.database import init_database, get_connection
from spine.core.dispatcher import Dispatcher, set_dispatcher
from spine.core.runner import Runner
from spine.core.registry import get_registry


@pytest.fixture(scope="function")
def temp_db() -> Generator[Path, None, None]:
    """Create a temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_spine.db"
        
        # Initialize database with all migrations
        init_database(str(db_path))
        
        yield db_path


@pytest.fixture(scope="function")
def db_connection(temp_db: Path) -> Generator[sqlite3.Connection, None, None]:
    """Get connection to temporary database."""
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    
    yield conn
    
    conn.close()


@pytest.fixture(scope="function")
def dispatcher(temp_db: Path) -> Dispatcher:
    """Create and configure dispatcher for testing."""
    runner = Runner(db_path=str(temp_db))
    dispatcher = Dispatcher(runner=runner)
    set_dispatcher(dispatcher)
    
    return dispatcher


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    """Path to OTC fixture files."""
    # Try multiple locations
    candidates = [
        Path("data/fixtures/otc"),
        Path("../data/fixtures/otc"),
        Path(__file__).parent.parent.parent.parent / "data" / "fixtures" / "otc",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    
    pytest.skip("Fixture directory not found")


@pytest.fixture(scope="session")
def expected_weeks() -> list[str]:
    """List of expected week_ending dates in fixtures."""
    return [
        "2025-11-21",
        "2025-11-28",
        "2025-12-05",
        "2025-12-12",
        "2025-12-19",
        "2025-12-26",
    ]


@pytest.fixture(scope="session")
def expected_symbols() -> list[str]:
    """List of valid symbols in fixtures."""
    return ["AAPL", "TSLA", "NVDA", "MSFT", "META"]


@pytest.fixture(scope="session")
def expected_rejects() -> list[dict]:
    """Expected rejected records."""
    return [
        {"week_ending": "2025-12-05", "reason_code": "INVALID_SYMBOL"},
        {"week_ending": "2025-12-19", "reason_code": "NEGATIVE_VOLUME"},
    ]
```

---

### `tests/domains/otc/test_validators_unit.py`

```python
"""
Unit tests for OTC validators and value objects.
"""
import pytest
from datetime import date

from spine.domains.otc.validators import WeekEnding, Symbol, MPID, compute_record_hash
from spine.domains.otc.enums import Tier


class TestWeekEnding:
    """Tests for WeekEnding value object."""
    
    def test_valid_friday(self):
        """Accept valid Friday dates."""
        week = WeekEnding("2025-12-26")
        assert str(week) == "2025-12-26"
        assert week.value == date(2025, 12, 26)
    
    def test_reject_non_friday(self):
        """Reject dates that are not Fridays."""
        with pytest.raises(ValueError, match="must be a Friday"):
            WeekEnding("2025-12-25")  # Thursday
    
    def test_reject_invalid_date(self):
        """Reject invalid date formats."""
        with pytest.raises(ValueError, match="Invalid date format"):
            WeekEnding("not-a-date")
    
    def test_from_any_date(self):
        """from_any_date finds the containing week's Friday."""
        # Wednesday -> Friday of same week
        week = WeekEnding.from_any_date(date(2025, 12, 24))
        assert str(week) == "2025-12-26"
        
        # Saturday -> Friday of following week
        week = WeekEnding.from_any_date(date(2025, 12, 27))
        assert str(week) == "2026-01-02"
    
    def test_from_weeks_back(self):
        """from_weeks_back computes correct dates."""
        # This is relative to test execution date, so we verify structure
        week = WeekEnding.from_weeks_back(0)
        assert week.value.weekday() == 4  # Friday
    
    def test_equality(self):
        """WeekEnding objects are equal if they represent same date."""
        w1 = WeekEnding("2025-12-26")
        w2 = WeekEnding("2025-12-26")
        assert w1 == w2
        assert w1 == "2025-12-26"  # Compare with string
    
    def test_ordering(self):
        """WeekEnding objects can be compared."""
        w1 = WeekEnding("2025-12-19")
        w2 = WeekEnding("2025-12-26")
        assert w1 < w2


class TestSymbol:
    """Tests for Symbol value object."""
    
    def test_valid_symbol(self):
        """Accept valid symbols."""
        assert str(Symbol("AAPL")) == "AAPL"
        assert str(Symbol("BRK.A")) == "BRK.A"
        assert str(Symbol("X")) == "X"
    
    def test_normalize_case(self):
        """Symbols are normalized to uppercase."""
        assert str(Symbol("aapl")) == "AAPL"
        assert str(Symbol("Tsla")) == "TSLA"
    
    def test_reject_invalid_chars(self):
        """Reject symbols with invalid characters."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol("BAD$YM")
        
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol("BAD@SYM")
    
    def test_reject_empty(self):
        """Reject empty symbols."""
        with pytest.raises(ValueError, match="cannot be empty"):
            Symbol("")
    
    def test_reject_too_long(self):
        """Reject symbols longer than 10 chars."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol("ABCDEFGHIJK")  # 11 chars
    
    def test_reject_starts_with_number(self):
        """Reject symbols that start with a number."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol("1ABC")


class TestMPID:
    """Tests for MPID value object."""
    
    def test_valid_mpid(self):
        """Accept valid MPIDs."""
        assert str(MPID("NITE")) == "NITE"
        assert str(MPID("CITD")) == "CITD"
    
    def test_normalize_case(self):
        """MPIDs are normalized to uppercase."""
        assert str(MPID("nite")) == "NITE"
    
    def test_reject_wrong_length(self):
        """Reject MPIDs that are not exactly 4 chars."""
        with pytest.raises(ValueError, match="must be exactly 4 characters"):
            MPID("NIT")  # 3 chars
        
        with pytest.raises(ValueError, match="must be exactly 4 characters"):
            MPID("NITEE")  # 5 chars


class TestTier:
    """Tests for Tier enum."""
    
    def test_from_string(self):
        """Parse tier from various formats."""
        assert Tier.from_string("NMS_TIER_1") == Tier.NMS_TIER_1
        assert Tier.from_string("nms_tier_1") == Tier.NMS_TIER_1
        assert Tier.from_string("NMS-TIER-1") == Tier.NMS_TIER_1
    
    def test_reject_invalid(self):
        """Reject invalid tier values."""
        with pytest.raises(ValueError, match="Invalid tier"):
            Tier.from_string("INVALID")


class TestRecordHash:
    """Tests for record hash computation."""
    
    def test_deterministic(self):
        """Same inputs produce same hash."""
        h1 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 1000, 50)
        h2 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 1000, 50)
        assert h1 == h2
    
    def test_different_values_different_hash(self):
        """Different inputs produce different hashes."""
        h1 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 1000, 50)
        h2 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 1001, 50)
        assert h1 != h2
    
    def test_hash_length(self):
        """Hash is exactly 32 characters."""
        h = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 1000, 50)
        assert len(h) == 32
```

---

### `tests/domains/otc/test_backfill_golden.py`

```python
"""
Golden tests for OTC multi-week backfill workflow.

These tests run the full backfill against fixture data and verify
that the results match expected values.
"""
import pytest
import sqlite3
from pathlib import Path

from spine.domains.otc.enums import ManifestStage, QualityStatus


class TestBackfillGolden:
    """Golden tests for the full backfill workflow."""
    
    @pytest.fixture(autouse=True)
    def run_backfill(self, dispatcher, fixture_dir, db_connection):
        """Run backfill before each test."""
        # Execute backfill
        result = dispatcher.submit(
            "otc.backfill_range",
            params={
                "tier": "NMS_TIER_1",
                "start_week": "2025-11-21",
                "end_week": "2025-12-26",
                "source_dir": str(fixture_dir),
            }
        )
        
        self.backfill_result = result
        self.conn = db_connection
        self.batch_id = result.metrics.get("batch_id")
    
    # =========================================================================
    # Test 1: Manifest created for all weeks
    # =========================================================================
    def test_manifest_all_weeks_present(self, expected_weeks):
        """Verify manifest has entries for all 6 weeks."""
        rows = self.conn.execute("""
            SELECT week_ending, tier, stage
            FROM otc_week_manifest
            WHERE tier = 'NMS_TIER_1'
            ORDER BY week_ending
        """).fetchall()
        
        assert len(rows) == 6, f"Expected 6 weeks, got {len(rows)}"
        
        actual_weeks = [r["week_ending"] for r in rows]
        assert actual_weeks == expected_weeks
    
    def test_manifest_stages_correct(self):
        """Verify each week reached expected stage."""
        rows = self.conn.execute("""
            SELECT week_ending, stage
            FROM otc_week_manifest
            WHERE tier = 'NMS_TIER_1'
            ORDER BY week_ending
        """).fetchall()
        
        # All weeks should be at least AGGREGATED
        for row in rows[:-1]:  # All but last
            stage = ManifestStage(row["stage"])
            assert stage >= ManifestStage.AGGREGATED, \
                f"Week {row['week_ending']} at {row['stage']}, expected >= AGGREGATED"
        
        # Last week should be SNAPSHOT (includes rolling)
        last = rows[-1]
        assert ManifestStage(last["stage"]) == ManifestStage.SNAPSHOT, \
            f"Last week at {last['stage']}, expected SNAPSHOT"
    
    # =========================================================================
    # Test 2: Rejects contain expected records
    # =========================================================================
    def test_rejects_count(self, expected_rejects):
        """Verify correct number of rejects."""
        count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM otc_rejects WHERE tier = 'NMS_TIER_1'"
        ).fetchone()["cnt"]
        
        assert count == len(expected_rejects), \
            f"Expected {len(expected_rejects)} rejects, got {count}"
    
    def test_rejects_invalid_symbol(self):
        """Verify BAD$YM was rejected with correct reason."""
        row = self.conn.execute("""
            SELECT week_ending, reason_code, reason_detail
            FROM otc_rejects
            WHERE reason_code = 'INVALID_SYMBOL'
        """).fetchone()
        
        assert row is not None, "Expected INVALID_SYMBOL reject not found"
        assert row["week_ending"] == "2025-12-05"
        assert "BAD$YM" in row["reason_detail"] or "BAD" in row["reason_detail"]
    
    def test_rejects_negative_volume(self):
        """Verify negative volume was rejected."""
        row = self.conn.execute("""
            SELECT week_ending, reason_code, reason_detail
            FROM otc_rejects
            WHERE reason_code = 'NEGATIVE_VOLUME'
        """).fetchone()
        
        assert row is not None, "Expected NEGATIVE_VOLUME reject not found"
        assert row["week_ending"] == "2025-12-19"
        assert "-50000" in row["reason_detail"]
    
    # =========================================================================
    # Test 3: Rolling has complete windows
    # =========================================================================
    def test_rolling_complete_windows(self, expected_symbols):
        """Verify all symbols have complete 6-week windows."""
        rows = self.conn.execute("""
            SELECT symbol, weeks_in_window, is_complete_window
            FROM otc_symbol_rolling_6w
            WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
        """).fetchall()
        
        assert len(rows) == len(expected_symbols), \
            f"Expected {len(expected_symbols)} symbols in rolling, got {len(rows)}"
        
        for row in rows:
            assert row["weeks_in_window"] == 6, \
                f"Symbol {row['symbol']} has {row['weeks_in_window']} weeks, expected 6"
            assert row["is_complete_window"] == 1, \
                f"Symbol {row['symbol']} not marked as complete window"
    
    def test_rolling_trends_computed(self):
        """Verify trend directions are computed."""
        rows = self.conn.execute("""
            SELECT symbol, trend_direction, trend_pct
            FROM otc_symbol_rolling_6w
            WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
        """).fetchall()
        
        for row in rows:
            assert row["trend_direction"] in ("UP", "DOWN", "FLAT"), \
                f"Invalid trend direction for {row['symbol']}: {row['trend_direction']}"
    
    # =========================================================================
    # Test 4: Snapshot contains expected totals
    # =========================================================================
    def test_snapshot_symbol_count(self, expected_symbols):
        """Verify snapshot has all valid symbols."""
        rows = self.conn.execute("""
            SELECT symbol
            FROM otc_research_snapshot
            WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
        """).fetchall()
        
        actual_symbols = sorted([r["symbol"] for r in rows])
        assert actual_symbols == sorted(expected_symbols)
    
    def test_snapshot_aapl_totals(self):
        """Verify AAPL snapshot has expected values."""
        row = self.conn.execute("""
            SELECT total_volume, total_trades, venue_count, has_rolling_data
            FROM otc_research_snapshot
            WHERE week_ending = '2025-12-26' 
              AND tier = 'NMS_TIER_1' 
              AND symbol = 'AAPL'
        """).fetchone()
        
        assert row is not None, "AAPL not found in snapshot"
        
        # Expected from week_2025-12-26.psv: NITE=1650000, CITD=1320000, JANE=890000
        expected_volume = 1650000 + 1320000 + 890000  # = 3,860,000
        assert row["total_volume"] == expected_volume, \
            f"AAPL volume: expected {expected_volume}, got {row['total_volume']}"
        
        assert row["venue_count"] == 3
        assert row["has_rolling_data"] == 1
    
    def test_snapshot_has_rolling_data(self):
        """Verify all snapshot records have rolling data."""
        rows = self.conn.execute("""
            SELECT symbol, has_rolling_data, rolling_weeks_available
            FROM otc_research_snapshot
            WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
        """).fetchall()
        
        for row in rows:
            assert row["has_rolling_data"] == 1, \
                f"Symbol {row['symbol']} missing rolling data"
            assert row["rolling_weeks_available"] == 6, \
                f"Symbol {row['symbol']} has {row['rolling_weeks_available']} rolling weeks"
    
    # =========================================================================
    # Test 5: Quality checks exist and pass
    # =========================================================================
    def test_quality_checks_exist(self):
        """Verify quality checks were recorded."""
        count = self.conn.execute("""
            SELECT COUNT(*) as cnt
            FROM otc_quality_checks
            WHERE tier = 'NMS_TIER_1'
        """).fetchone()["cnt"]
        
        # At least 5 checks per aggregated week + rolling checks
        assert count >= 30, f"Expected at least 30 quality checks, got {count}"
    
    def test_quality_checks_pass(self):
        """Verify no quality checks failed."""
        failed = self.conn.execute("""
            SELECT week_ending, check_name, status, message
            FROM otc_quality_checks
            WHERE tier = 'NMS_TIER_1' AND status = 'FAIL'
        """).fetchall()
        
        assert len(failed) == 0, \
            f"Found {len(failed)} failed quality checks: {[r['check_name'] for r in failed]}"
    
    def test_market_share_sums(self):
        """Verify market shares sum to ~100% for each week."""
        rows = self.conn.execute("""
            SELECT week_ending, check_name, check_value, status
            FROM otc_quality_checks
            WHERE check_name = 'market_share_sum_100' AND tier = 'NMS_TIER_1'
        """).fetchall()
        
        for row in rows:
            assert row["status"] in ("PASS", "WARN"), \
                f"Market share check failed for {row['week_ending']}"
            
            # Value should be close to 100
            value = float(row["check_value"])
            assert 99.5 <= value <= 100.5, \
                f"Market share sum {value} outside tolerance for {row['week_ending']}"
    
    # =========================================================================
    # Test 6: Batch ID links all records
    # =========================================================================
    def test_batch_id_consistent(self):
        """Verify batch_id links records across tables."""
        batch_id = self.batch_id
        
        # Check raw records
        raw_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM otc_raw WHERE batch_id = ?",
            (batch_id,)
        ).fetchone()["cnt"]
        assert raw_count > 0, "No raw records with batch_id"
        
        # Check normalized
        norm_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM otc_venue_volume WHERE batch_id = ?",
            (batch_id,)
        ).fetchone()["cnt"]
        assert norm_count > 0, "No venue_volume records with batch_id"
        
        # Check summaries
        sum_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM otc_symbol_summary WHERE batch_id = ?",
            (batch_id,)
        ).fetchone()["cnt"]
        assert sum_count > 0, "No symbol_summary records with batch_id"
    
    # =========================================================================
    # Test 7: Backfill result metrics
    # =========================================================================
    def test_backfill_success(self):
        """Verify backfill completed successfully."""
        from spine.core.pipeline import PipelineStatus
        
        assert self.backfill_result.status == PipelineStatus.COMPLETED
        assert self.backfill_result.error is None
    
    def test_backfill_metrics_accurate(self):
        """Verify backfill metrics match database state."""
        metrics = self.backfill_result.metrics
        
        assert metrics["weeks_processed"] == 6
        assert metrics["rolling_computed"] == True
        assert metrics["snapshot_built"] == True
        
        # Total ingested should match raw count
        raw_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM otc_raw WHERE tier = 'NMS_TIER_1'"
        ).fetchone()["cnt"]
        assert metrics["total_ingested"] == raw_count


class TestBackfillIdempotency:
    """Tests for idempotency of backfill operations."""
    
    def test_double_backfill_same_result(self, dispatcher, fixture_dir, db_connection):
        """Running backfill twice produces same final state."""
        params = {
            "tier": "NMS_TIER_1",
            "start_week": "2025-11-21",
            "end_week": "2025-12-26",
            "source_dir": str(fixture_dir),
        }
        
        # First run
        result1 = dispatcher.submit("otc.backfill_range", params=params)
        
        count1 = db_connection.execute(
            "SELECT COUNT(*) as cnt FROM otc_raw WHERE tier = 'NMS_TIER_1'"
        ).fetchone()["cnt"]
        
        # Second run (should skip due to idempotency)
        result2 = dispatcher.submit("otc.backfill_range", params=params)
        
        count2 = db_connection.execute(
            "SELECT COUNT(*) as cnt FROM otc_raw WHERE tier = 'NMS_TIER_1'"
        ).fetchone()["cnt"]
        
        # Counts should be equal (no duplicates)
        assert count1 == count2, f"Count changed from {count1} to {count2} on re-run"
    
    def test_force_reprocess(self, dispatcher, fixture_dir, db_connection):
        """Force flag allows reprocessing."""
        base_params = {
            "tier": "NMS_TIER_1",
            "start_week": "2025-11-21",
            "end_week": "2025-12-26",
            "source_dir": str(fixture_dir),
        }
        
        # First run
        dispatcher.submit("otc.backfill_range", params=base_params)
        
        # Force re-run
        force_params = {**base_params, "force": True}
        result = dispatcher.submit("otc.backfill_range", params=force_params)
        
        # Should complete without error
        from spine.core.pipeline import PipelineStatus
        assert result.status == PipelineStatus.COMPLETED
```

---

### Running the Tests

```powershell
# Run all OTC tests
pytest tests/domains/otc/ -v

# Run only golden tests
pytest tests/domains/otc/test_backfill_golden.py -v

# Run with coverage
pytest tests/domains/otc/ --cov=spine.domains.otc --cov-report=term-missing

# Run specific test
pytest tests/domains/otc/test_backfill_golden.py::TestBackfillGolden::test_rejects_invalid_symbol -v
```

---

## Next: Read [11-cli-examples.md](11-cli-examples.md) for CLI usage
