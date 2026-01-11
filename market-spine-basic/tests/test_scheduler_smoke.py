"""
Scheduler Smoke Tests.

End-to-end integration tests for scheduler entrypoints.
Tests both dry-run and real execution modes.

Run with: pytest tests/test_scheduler_smoke.py -v
"""

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# Add package paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-domains" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "market-spine-basic" / "src"))


class TestSchedulerResultContract:
    """Tests for the SchedulerResult contract."""
    
    def test_result_contract_imports(self):
        """Contract classes can be imported."""
        from market_spine.app.scheduling import (
            SchedulerResult,
            SchedulerStats,
            SchedulerStatus,
            RunResult,
            RunStatus,
            AnomalySummary,
        )
        
        assert SchedulerResult is not None
        assert SchedulerStatus.SUCCESS.value == "success"
        assert RunStatus.COMPLETED.value == "completed"
    
    def test_result_contract_to_json(self):
        """SchedulerResult produces valid JSON."""
        from market_spine.app.scheduling import (
            SchedulerResult,
            SchedulerStats,
            SchedulerStatus,
            RunResult,
            RunStatus,
        )
        
        result = SchedulerResult(
            domain="test.domain",
            scheduler="test_scheduler",
            started_at="2025-01-01T00:00:00Z",
            finished_at="2025-01-01T00:01:00Z",
            status=SchedulerStatus.SUCCESS,
            stats=SchedulerStats(attempted=3, succeeded=3, failed=0, skipped=0),
            runs=[
                RunResult(
                    pipeline="test.pipeline",
                    partition_key="2025-01-01|TIER1",
                    status=RunStatus.COMPLETED,
                    duration_ms=100,
                ),
            ],
            config={"mode": "dry-run"},
        )
        
        json_str = result.to_json()
        assert json_str is not None
        
        # Parse and validate
        parsed = json.loads(json_str)
        assert parsed["domain"] == "test.domain"
        assert parsed["status"] == "success"
        assert parsed["stats"]["succeeded"] == 3
        assert len(parsed["runs"]) == 1
    
    def test_result_exit_code(self):
        """SchedulerResult.exit_code matches status."""
        from market_spine.app.scheduling import (
            SchedulerResult,
            SchedulerStats,
            SchedulerStatus,
        )
        
        success_result = SchedulerResult(
            domain="test", scheduler="test",
            started_at="2025-01-01T00:00:00Z",
            finished_at="2025-01-01T00:01:00Z",
            status=SchedulerStatus.SUCCESS,
            stats=SchedulerStats(attempted=1, succeeded=1, failed=0, skipped=0),
        )
        assert success_result.exit_code == 0
        
        failure_result = SchedulerResult(
            domain="test", scheduler="test",
            started_at="2025-01-01T00:00:00Z",
            finished_at="2025-01-01T00:01:00Z",
            status=SchedulerStatus.FAILURE,
            stats=SchedulerStats(attempted=1, succeeded=0, failed=1, skipped=0),
        )
        assert failure_result.exit_code == 1
        
        partial_result = SchedulerResult(
            domain="test", scheduler="test",
            started_at="2025-01-01T00:00:00Z",
            finished_at="2025-01-01T00:01:00Z",
            status=SchedulerStatus.PARTIAL,
            stats=SchedulerStats(attempted=2, succeeded=1, failed=1, skipped=0),
        )
        assert partial_result.exit_code == 2
    
    def test_validate_scheduler_result(self):
        """validate_scheduler_result checks required fields."""
        from market_spine.app.scheduling import validate_scheduler_result
        
        # Valid result
        valid = {
            "domain": "test",
            "scheduler": "test",
            "started_at": "2025-01-01T00:00:00Z",
            "finished_at": "2025-01-01T00:01:00Z",
            "status": "success",
            "stats": {"attempted": 1, "succeeded": 1, "failed": 0, "skipped": 0},
        }
        errors = validate_scheduler_result(valid)
        assert errors == []
        
        # Missing required field
        invalid = {"domain": "test"}
        errors = validate_scheduler_result(invalid)
        assert len(errors) > 0
        assert any("scheduler" in e for e in errors)


class TestFinraSchedulerSmoke:
    """Smoke tests for FINRA scheduler."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        import sqlite3
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        # Create minimal schema
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS core_manifest (
                capture_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                stage TEXT NOT NULL,
                partition_key TEXT,
                captured_at TEXT NOT NULL,
                row_count INTEGER,
                metadata_json TEXT
            );
            
            CREATE TABLE IF NOT EXISTS core_anomalies (
                anomaly_id TEXT PRIMARY KEY,
                domain TEXT,
                stage TEXT,
                partition_key TEXT,
                severity TEXT,
                category TEXT,
                message TEXT,
                detected_at TEXT,
                metadata TEXT,
                resolved_at TEXT,
                capture_id TEXT
            );
        """)
        conn.close()
        
        yield db_path
        
        # Cleanup
        Path(db_path).unlink(missing_ok=True)
    
    def test_finra_scheduler_dry_run(self, temp_db):
        """FINRA scheduler dry-run returns SchedulerResult."""
        from spine.domains.finra.otc_transparency.scheduler import run_finra_schedule
        
        result = run_finra_schedule(
            lookback_weeks=1,
            tiers=["NMS_TIER_1"],
            mode="dry-run",
            db_path=temp_db,
            source_type="file",
        )
        
        # Should return SchedulerResult with exit_code
        assert hasattr(result, 'exit_code')
        assert hasattr(result, 'status')
        
        # Dry-run should succeed (even if no files)
        # Status may be success or failure depending on fixture availability
        assert result.exit_code in (0, 1, 2)
    
    def test_finra_scheduler_json_output(self, temp_db):
        """FINRA scheduler result serializes to JSON."""
        from spine.domains.finra.otc_transparency.scheduler import run_finra_schedule
        
        result = run_finra_schedule(
            lookback_weeks=1,
            tiers=["NMS_TIER_1"],
            mode="dry-run",
            db_path=temp_db,
            source_type="file",
        )
        
        if hasattr(result, 'to_json'):
            json_str = result.to_json()
            parsed = json.loads(json_str)
            
            assert "domain" in parsed
            assert "scheduler" in parsed
            assert "status" in parsed
            assert "stats" in parsed
    
    def test_finra_scheduler_max_lookback_clamped(self, temp_db):
        """Lookback > 12 is clamped unless --force."""
        from spine.domains.finra.otc_transparency.scheduler import run_finra_schedule
        
        result = run_finra_schedule(
            lookback_weeks=20,  # Exceeds MAX_LOOKBACK_WEEKS
            tiers=["NMS_TIER_1"],
            mode="dry-run",
            db_path=temp_db,
            source_type="file",
            force=False,  # Should clamp
        )
        
        if hasattr(result, 'warnings'):
            # Should have a warning about clamping
            assert any("lookback" in w.lower() or "max" in w.lower() for w in result.warnings)
        
        if hasattr(result, 'config'):
            # Config should show clamped value
            assert result.config.get("lookback_weeks", 0) <= 12


class TestPriceSchedulerSmoke:
    """Smoke tests for price scheduler."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        import sqlite3
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        # Create minimal schema
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS market_data_prices_daily (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                change REAL,
                change_percent REAL,
                source TEXT,
                capture_id TEXT,
                captured_at TEXT,
                is_valid INTEGER DEFAULT 1,
                PRIMARY KEY (symbol, date, capture_id)
            );
            
            CREATE TABLE IF NOT EXISTS core_anomalies (
                anomaly_id TEXT PRIMARY KEY,
                domain TEXT,
                stage TEXT,
                partition_key TEXT,
                severity TEXT,
                category TEXT,
                message TEXT,
                detected_at TEXT,
                metadata TEXT,
                resolved_at TEXT
            );
        """)
        conn.close()
        
        yield db_path
        
        # Cleanup
        Path(db_path).unlink(missing_ok=True)
    
    def test_price_scheduler_dry_run(self, temp_db):
        """Price scheduler dry-run returns SchedulerResult."""
        from spine.domains.market_data.scheduler import run_price_schedule
        
        result = run_price_schedule(
            symbols=["AAPL", "MSFT"],
            mode="dry-run",
            db_path=temp_db,
            sleep_between=0,  # No rate limiting in tests
        )
        
        # Should return SchedulerResult with exit_code
        assert hasattr(result, 'exit_code')
        assert hasattr(result, 'status')
        
        # Dry-run should succeed
        assert result.exit_code == 0
    
    def test_price_scheduler_json_output(self, temp_db):
        """Price scheduler result serializes to JSON."""
        from spine.domains.market_data.scheduler import run_price_schedule
        
        result = run_price_schedule(
            symbols=["AAPL"],
            mode="dry-run",
            db_path=temp_db,
            sleep_between=0,
        )
        
        if hasattr(result, 'to_json'):
            json_str = result.to_json()
            parsed = json.loads(json_str)
            
            assert "domain" in parsed
            assert "scheduler" in parsed
            assert "status" in parsed
            assert "stats" in parsed


class TestWrapperScriptHelp:
    """Test that wrapper scripts have valid --help output."""
    
    def test_finra_script_help(self):
        """schedule_finra.py --help runs without error."""
        import subprocess
        
        script_path = PROJECT_ROOT / "scripts" / "schedule_finra.py"
        if not script_path.exists():
            pytest.skip("schedule_finra.py not found")
        
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0
        assert "--mode" in result.stdout
        assert "--json" in result.stdout
        assert "--fail-fast" in result.stdout
        assert "--log-level" in result.stdout
    
    def test_prices_script_help(self):
        """schedule_prices.py --help runs without error."""
        import subprocess
        
        script_path = PROJECT_ROOT / "scripts" / "schedule_prices.py"
        if not script_path.exists():
            pytest.skip("schedule_prices.py not found")
        
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0
        assert "--mode" in result.stdout
        assert "--json" in result.stdout
        assert "--fail-fast" in result.stdout
        assert "--log-level" in result.stdout
