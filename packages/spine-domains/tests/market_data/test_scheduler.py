"""Tests for market_data scheduler module."""

import pytest
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

from spine.domains.market_data.scheduler import (
    PriceScheduleConfig,
    PriceScheduleResult,
    generate_price_capture_id,
    run_price_schedule,
)


class TestPriceScheduleResult:
    """Tests for PriceScheduleResult dataclass."""
    
    def test_has_failures_false_when_no_failures(self):
        """No failures means has_failures is False."""
        result = PriceScheduleResult()
        result.success = ["AAPL", "MSFT"]
        
        assert result.has_failures is False
    
    def test_has_failures_true_when_failures(self):
        """Failures present means has_failures is True."""
        result = PriceScheduleResult()
        result.success = ["AAPL"]
        result.failed = [{"symbol": "MSFT", "error": "API error"}]
        
        assert result.has_failures is True
    
    def test_all_failed_true_when_none_succeeded(self):
        """All failed when success list is empty."""
        result = PriceScheduleResult()
        result.failed = [{"symbol": "AAPL", "error": "API error"}]
        
        assert result.all_failed is True
    
    def test_all_failed_false_when_some_succeeded(self):
        """Not all failed when some succeeded."""
        result = PriceScheduleResult()
        result.success = ["AAPL"]
        result.failed = [{"symbol": "MSFT", "error": "API error"}]
        
        assert result.all_failed is False
    
    def test_as_dict_serialization(self):
        """Result can be serialized to dict."""
        result = PriceScheduleResult()
        result.success = ["AAPL"]
        result.total_rows = 100
        result.duration_seconds = 5.5
        
        d = result.as_dict()
        
        assert d["success"] == ["AAPL"]
        assert d["total_rows"] == 100
        assert d["duration_seconds"] == 5.5
        assert d["has_failures"] is False


class TestGeneratePriceCaptureId:
    """Tests for capture ID generation."""
    
    def test_capture_id_format(self):
        """Capture ID has expected format."""
        capture_id = generate_price_capture_id(
            symbol="AAPL",
            source="alpha_vantage",
            run_date=date(2026, 1, 9),
        )
        
        assert capture_id == "market_data.prices.AAPL.alpha_vantage.20260109"
    
    def test_capture_id_deterministic(self):
        """Same inputs produce same capture ID."""
        id1 = generate_price_capture_id("AAPL", "alpha_vantage", date(2026, 1, 9))
        id2 = generate_price_capture_id("AAPL", "alpha_vantage", date(2026, 1, 9))
        
        assert id1 == id2
    
    def test_different_dates_different_ids(self):
        """Different dates produce different capture IDs."""
        id1 = generate_price_capture_id("AAPL", "alpha_vantage", date(2026, 1, 9))
        id2 = generate_price_capture_id("AAPL", "alpha_vantage", date(2026, 1, 10))
        
        assert id1 != id2


class TestRunPriceScheduleDryRun:
    """Tests for dry-run mode execution."""
    
    def setup_method(self):
        """Create temp database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        
        # Create minimal schema
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
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
            
            CREATE TABLE IF NOT EXISTS market_data_prices_daily (
                symbol TEXT,
                date TEXT,
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
                is_valid INTEGER,
                PRIMARY KEY (symbol, date, capture_id)
            );
        """)
        conn.close()
    
    def teardown_method(self):
        """Clean up temp database."""
        Path(self.db_path).unlink(missing_ok=True)
    
    def test_dry_run_no_database_writes(self):
        """Dry-run mode doesn't write to database."""
        result = run_price_schedule(
            symbols=["AAPL", "MSFT"],
            mode="dry-run",
            db_path=self.db_path,
        )
        
        # Should succeed without actually fetching
        assert len(result.success) == 2
        assert len(result.failed) == 0
        
        # Database should be empty
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM market_data_prices_daily"
        ).fetchone()[0]
        conn.close()
        
        assert count == 0
    
    def test_dry_run_returns_result(self):
        """Dry-run mode returns proper result object."""
        result = run_price_schedule(
            symbols=["AAPL"],
            mode="dry-run",
            db_path=self.db_path,
        )
        
        assert isinstance(result, PriceScheduleResult)
        assert result.duration_seconds > 0


class TestRunPriceScheduleFailFast:
    """Tests for fail-fast mode."""
    
    def setup_method(self):
        """Create temp database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
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
            
            CREATE TABLE IF NOT EXISTS market_data_prices_daily (
                symbol TEXT,
                date TEXT,
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
                is_valid INTEGER,
                PRIMARY KEY (symbol, date, capture_id)
            );
        """)
        conn.close()
    
    def teardown_method(self):
        """Clean up temp database."""
        Path(self.db_path).unlink(missing_ok=True)
    
    @patch("spine.domains.market_data.scheduler.create_source")
    def test_fail_fast_stops_on_first_failure(self, mock_create_source):
        """Fail-fast stops processing after first failure."""
        # First call fails, second should not be attempted
        mock_source = MagicMock()
        mock_source.fetch.side_effect = [
            MagicMock(success=False, error="API error"),
            MagicMock(success=True, data=[{"date": "2026-01-09", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000}]),
        ]
        mock_create_source.return_value = mock_source
        
        result = run_price_schedule(
            symbols=["FAIL_SYMBOL", "GOOD_SYMBOL", "ANOTHER_SYMBOL"],
            mode="run",
            fail_fast=True,
            db_path=self.db_path,
            sleep_between=0,  # No delay for tests
        )
        
        # First should fail
        assert len(result.failed) == 1
        assert result.failed[0]["symbol"] == "FAIL_SYMBOL"
        
        # Remaining should be skipped (not failed)
        assert len(result.skipped) == 2


class TestRunPriceScheduleRateLimiting:
    """Tests for rate limiting behavior."""
    
    def setup_method(self):
        """Create temp database."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
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
    
    def teardown_method(self):
        Path(self.db_path).unlink(missing_ok=True)
    
    def test_max_symbols_limit_respected(self):
        """Max symbols limit causes extra symbols to be skipped."""
        result = run_price_schedule(
            symbols=["S1", "S2", "S3", "S4", "S5"],
            mode="dry-run",
            max_symbols=3,
            db_path=self.db_path,
        )
        
        # Only first 3 processed
        assert len(result.success) == 3
        
        # Rest skipped
        assert len(result.skipped) == 2
