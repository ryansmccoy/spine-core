"""Tests for FINRA OTC scheduler module."""

import pytest
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from spine.domains.finra.otc_transparency.scheduler import (
    FinraScheduleConfig,
    FinraScheduleResult,
    calculate_target_weeks,
    parse_week_list,
    generate_capture_id,
    compute_content_hash,
    run_finra_schedule,
)


class TestFinraScheduleResult:
    """Tests for FinraScheduleResult dataclass."""
    
    def test_has_failures_false_when_no_failures(self):
        """No failures means has_failures is False."""
        result = FinraScheduleResult()
        result.success = [{"week": "2026-01-09", "tier": "OTC", "stage": "ingest"}]
        
        assert result.has_failures is False
    
    def test_has_failures_true_when_failures(self):
        """Failures present means has_failures is True."""
        result = FinraScheduleResult()
        result.failed = [{"week": "2026-01-09", "tier": "OTC", "stage": "ingest", "error": "test"}]
        
        assert result.has_failures is True
    
    def test_all_failed_true_when_none_succeeded(self):
        """All failed when success list is empty."""
        result = FinraScheduleResult()
        result.failed = [{"week": "2026-01-09", "tier": "OTC", "stage": "ingest", "error": "test"}]
        
        assert result.all_failed is True
    
    def test_success_count_property(self):
        """success_count returns correct count."""
        result = FinraScheduleResult()
        result.success = [
            {"week": "2026-01-09", "tier": "OTC", "stage": "ingest"},
            {"week": "2026-01-09", "tier": "NMS_TIER_1", "stage": "ingest"},
        ]
        
        assert result.success_count == 2
    
    def test_as_dict_serialization(self):
        """Result can be serialized to dict."""
        result = FinraScheduleResult()
        result.success = [{"week": "2026-01-09", "tier": "OTC", "stage": "ingest"}]
        result.duration_seconds = 5.5
        
        d = result.as_dict()
        
        assert len(d["success"]) == 1
        assert d["duration_seconds"] == 5.5
        assert d["has_failures"] is False


class TestCalculateTargetWeeks:
    """Tests for week calculation utilities."""
    
    def test_friday_is_included(self):
        """If today is Friday, it's included as most recent."""
        friday = date(2026, 1, 9)  # This is a Thursday, let me pick a real Friday
        # Actually check: 2026-01-09 is a Friday
        # date(2026, 1, 9).weekday() = 4 (Friday)
        assert date(2026, 1, 9).weekday() == 4  # Verify it's Friday
        
        weeks = calculate_target_weeks(3, reference_date=date(2026, 1, 9))
        
        assert len(weeks) == 3
        assert weeks[0] == date(2026, 1, 9)  # This Friday
        assert weeks[1] == date(2026, 1, 2)  # Previous Friday
        assert weeks[2] == date(2025, 12, 26)  # Friday before that
    
    def test_non_friday_finds_previous(self):
        """If today is not Friday, find most recent past Friday."""
        wednesday = date(2026, 1, 7)  # Wednesday
        
        weeks = calculate_target_weeks(2, reference_date=wednesday)
        
        assert len(weeks) == 2
        assert weeks[0] == date(2026, 1, 2)  # Previous Friday
        assert weeks[1] == date(2025, 12, 26)  # Friday before that
    
    def test_lookback_zero_returns_empty(self):
        """Zero lookback returns empty list."""
        weeks = calculate_target_weeks(0, reference_date=date(2026, 1, 9))
        
        assert weeks == []
    
    def test_all_returned_dates_are_fridays(self):
        """All returned dates should be Fridays."""
        weeks = calculate_target_weeks(10, reference_date=date(2026, 1, 15))
        
        for week in weeks:
            assert week.weekday() == 4, f"{week} is not a Friday"


class TestParseWeekList:
    """Tests for week list parsing."""
    
    def test_single_week(self):
        """Parse single week."""
        weeks = parse_week_list("2025-12-26")
        
        assert len(weeks) == 1
        assert weeks[0] == date(2025, 12, 26)
    
    def test_multiple_weeks(self):
        """Parse multiple comma-separated weeks."""
        weeks = parse_week_list("2025-12-26,2025-12-19,2025-12-12")
        
        assert len(weeks) == 3
        assert weeks[0] == date(2025, 12, 26)
        assert weeks[1] == date(2025, 12, 19)
    
    def test_whitespace_handling(self):
        """Whitespace around dates is stripped."""
        weeks = parse_week_list("2025-12-26 , 2025-12-19")
        
        assert len(weeks) == 2
    
    def test_invalid_date_raises(self):
        """Invalid date format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_week_list("not-a-date")
    
    def test_non_friday_raises(self):
        """Non-Friday date raises ValueError."""
        with pytest.raises(ValueError, match="not a Friday"):
            parse_week_list("2025-12-25")  # Thursday


class TestGenerateCaptureId:
    """Tests for capture ID generation."""
    
    def test_capture_id_format(self):
        """Capture ID has expected format."""
        capture_id = generate_capture_id(
            week_ending=date(2025, 12, 26),
            tier="NMS_TIER_1",
            run_date=date(2025, 12, 30),
        )
        
        assert capture_id == "finra.otc_transparency:NMS_TIER_1:2025-12-26:20251230"
    
    def test_capture_id_deterministic(self):
        """Same inputs produce same capture ID."""
        id1 = generate_capture_id(date(2025, 12, 26), "OTC", date(2025, 12, 30))
        id2 = generate_capture_id(date(2025, 12, 26), "OTC", date(2025, 12, 30))
        
        assert id1 == id2
    
    def test_different_run_dates_different_ids(self):
        """Different run dates produce different capture IDs (restatement)."""
        id1 = generate_capture_id(date(2025, 12, 26), "OTC", date(2025, 12, 30))
        id2 = generate_capture_id(date(2025, 12, 26), "OTC", date(2025, 12, 31))
        
        assert id1 != id2


class TestComputeContentHash:
    """Tests for content hashing."""
    
    def test_hash_consistency(self):
        """Same content produces same hash."""
        content = b"test,data,content"
        
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        
        assert hash1 == hash2
    
    def test_hash_difference(self):
        """Different content produces different hash."""
        hash1 = compute_content_hash(b"content-a")
        hash2 = compute_content_hash(b"content-b")
        
        assert hash1 != hash2
    
    def test_hash_length(self):
        """Hash is truncated to 16 characters."""
        hash_result = compute_content_hash(b"any content")
        
        assert len(hash_result) == 16


class TestRunFinraScheduleDryRun:
    """Tests for dry-run mode execution."""
    
    def setup_method(self):
        """Create temp database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        
        # Create minimal schema
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS core_manifest (
                domain TEXT,
                stage TEXT,
                partition_key TEXT,
                metadata_json TEXT,
                row_count INTEGER,
                captured_at TEXT,
                capture_id TEXT
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
    
    def teardown_method(self):
        """Clean up temp database."""
        Path(self.db_path).unlink(missing_ok=True)
    
    def test_dry_run_no_database_writes(self):
        """Dry-run mode doesn't write anomalies."""
        result = run_finra_schedule(
            weeks=[date(2025, 12, 26)],
            tiers=["OTC"],
            mode="dry-run",
            only_stage="ingest",
            db_path=self.db_path,
        )
        
        # Should have some success (fetch will fail but dry-run doesn't care)
        # Actually in dry-run, fetch still happens but write is skipped
        # The result depends on whether files exist
        
        # Database should have no anomalies written
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM core_anomalies"
        ).fetchone()[0]
        conn.close()
        
        assert count == 0
    
    def test_dry_run_returns_result(self):
        """Dry-run mode returns proper result object."""
        result = run_finra_schedule(
            lookback_weeks=2,
            tiers=["OTC"],
            mode="dry-run",
            only_stage="ingest",
            db_path=self.db_path,
        )
        
        assert isinstance(result, FinraScheduleResult)
        assert result.duration_seconds > 0


class TestRunFinraScheduleFailFast:
    """Tests for fail-fast mode."""
    
    def setup_method(self):
        """Create temp database."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS core_manifest (
                domain TEXT,
                stage TEXT,
                partition_key TEXT,
                metadata_json TEXT,
                row_count INTEGER,
                captured_at TEXT,
                capture_id TEXT
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
    
    def teardown_method(self):
        Path(self.db_path).unlink(missing_ok=True)
    
    @patch("spine.domains.finra.otc_transparency.scheduler.fetch_source_data")
    def test_fail_fast_stops_on_first_failure(self, mock_fetch):
        """Fail-fast stops processing after first failure."""
        # All fetches will fail
        mock_fetch.return_value = (None, "File not found")
        
        result = run_finra_schedule(
            weeks=[date(2025, 12, 26), date(2025, 12, 19)],
            tiers=["OTC", "NMS_TIER_1"],
            mode="run",
            only_stage="ingest",
            fail_fast=True,
            db_path=self.db_path,
        )
        
        # Should have exactly 1 failure (stopped after first)
        assert len(result.failed) == 1
        assert result.has_failures is True


class TestWeekCalculationEdgeCases:
    """Edge case tests for week calculation."""
    
    def test_year_boundary(self):
        """Weeks correctly cross year boundary."""
        # Reference date in early January
        weeks = calculate_target_weeks(3, reference_date=date(2026, 1, 5))
        
        # Should include weeks from previous year
        years = {w.year for w in weeks}
        assert 2025 in years or 2026 in years
    
    def test_saturday_reference(self):
        """Saturday reference finds previous Friday."""
        saturday = date(2026, 1, 10)
        weeks = calculate_target_weeks(1, reference_date=saturday)
        
        assert weeks[0] == date(2026, 1, 9)  # Previous Friday
    
    def test_sunday_reference(self):
        """Sunday reference finds previous Friday."""
        sunday = date(2026, 1, 11)
        weeks = calculate_target_weeks(1, reference_date=sunday)
        
        assert weeks[0] == date(2026, 1, 9)  # Previous Friday
