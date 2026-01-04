# tests/finra/otc_transparency/test_connector.py

"""Tests for FINRA OTC Transparency connector, file parsing, and date derivation."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from spine.domains.finra.otc_transparency.connector import (
    RawOTCRecord,
    derive_week_ending_from_publish_date,
    extract_file_date_from_filename,
    extract_tier_from_filename,
    get_file_metadata,
    parse_finra_content,
)


class TestConnector:
    """Tests for FINRA file connector."""

    def test_raw_record_hash(self):
        """Test that raw records generate deterministic hashes."""
        r1 = RawOTCRecord(
            week_ending=date(2026, 1, 3),
            tier="NMS Tier 1",
            symbol="AAPL",
            mpid="VENA",
            total_shares=1000000,
            total_trades=5000,
        )
        r2 = RawOTCRecord(
            week_ending=date(2026, 1, 3),
            tier="NMS Tier 1",
            symbol="AAPL",
            mpid="VENA",
            total_shares=1000000,
            total_trades=5000,
        )
        assert r1.record_hash == r2.record_hash
        assert len(r1.record_hash) == 32  # SHA256 first 32 chars

    def test_parse_finra_content(self):
        """Test parsing FINRA PSV content."""
        content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2026-01-03
NMS Tier 2|MSFT|Microsoft Corp.|VENUE B|VENB|500000|2500|2026-01-03
"""
        records = list(parse_finra_content(content))

        assert len(records) == 2
        assert records[0].symbol == "AAPL"
        assert records[0].mpid == "VENA"
        assert records[0].total_shares == 1000000
        assert records[1].symbol == "MSFT"
        assert records[1].mpid == "VENB"


class TestWeekEndingDerivation:
    """
    Tests for FINRA week_ending date derivation.

    FINRA publishes OTC weekly data on Mondays.
    The data reflects trading activity from the prior Mon-Fri week.

    Rule: week_ending = file_date - 3 days (previous Friday)
    """

    @pytest.mark.parametrize(
        "file_date,expected_friday",
        [
            # Standard Monday publications
            (date(2025, 12, 15), date(2025, 12, 12)),  # Mon -> Fri
            (date(2025, 12, 22), date(2025, 12, 19)),  # Mon -> Fri
            (date(2025, 12, 29), date(2025, 12, 26)),  # Mon -> Fri
            # Edge case: if file_date is not Monday (should still work)
            (date(2025, 12, 16), date(2025, 12, 12)),  # Tue -> Fri (previous)
            (date(2025, 12, 19), date(2025, 12, 12)),  # Fri -> Fri (previous week)
        ],
    )
    def test_derive_week_ending_from_publish_date(self, file_date, expected_friday):
        """Test that week_ending is correctly derived from file/publish date."""
        result = derive_week_ending_from_publish_date(file_date)
        assert result == expected_friday
        # Verify it's actually a Friday
        assert result.weekday() == 4, f"Expected Friday, got {result.strftime('%A')}"

    @pytest.mark.parametrize(
        "filename,expected_date",
        [
            # Pattern: YYYYMMDD at end
            ("finra_otc_weekly_tier1_20251222.csv", date(2025, 12, 22)),
            ("finra_otc_weekly_otc_20251215.csv", date(2025, 12, 15)),
            ("finra_otc_weekly_tier2_20251229.csv", date(2025, 12, 29)),
            # Pattern: YYYY-MM-DD anywhere
            ("nms_tier1_2025-12-26.psv", date(2025, 12, 26)),
            ("data_2025-01-03_tier1.csv", date(2025, 1, 3)),
            # No date pattern
            ("random_file.csv", None),
            ("tier1_data.psv", None),
        ],
    )
    def test_extract_file_date_from_filename(self, filename, expected_date):
        """Test extracting file/publish date from filename patterns."""
        result = extract_file_date_from_filename(filename)
        assert result == expected_date

    @pytest.mark.parametrize(
        "filename,expected_tier",
        [
            ("finra_otc_weekly_tier1_20251222.csv", "NMS_TIER_1"),
            ("finra_otc_weekly_tier2_20251222.csv", "NMS_TIER_2"),
            ("finra_otc_weekly_otc_20251222.csv", "OTC"),
            ("nms_tier_1_2025-12-26.psv", "NMS_TIER_1"),
            ("random_file.csv", None),
        ],
    )
    def test_extract_tier_from_filename(self, filename, expected_tier):
        """Test extracting tier hint from filename."""
        result = extract_tier_from_filename(filename)
        assert result == expected_tier

    def test_get_file_metadata_from_content(self):
        """Test that get_file_metadata derives week_ending from file content."""
        content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-22
"""
        # Create temp file with content
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            metadata = get_file_metadata(temp_path)

            # lastUpdateDate is 2025-12-22 (Monday)
            # week_ending should be 2025-12-19 (previous Friday)
            assert metadata.file_date == date(2025, 12, 22)
            assert metadata.week_ending == date(2025, 12, 19)
            assert metadata.source == "content"
        finally:
            Path(temp_path).unlink()

    def test_get_file_metadata_from_filename(self):
        """Test that get_file_metadata extracts date from filename first."""
        content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-22
"""
        # Create temp file with specific filename pattern
        temp_dir = Path(tempfile.mkdtemp())
        temp_path = temp_dir / "finra_otc_weekly_tier1_20251222.csv"

        try:
            temp_path.write_text(content, encoding="utf-8")

            metadata = get_file_metadata(str(temp_path))

            # Should extract from filename, not content
            assert metadata.file_date == date(2025, 12, 22)
            assert metadata.week_ending == date(2025, 12, 19)
            assert metadata.source == "filename"
            assert metadata.tier_hint == "NMS_TIER_1"
        finally:
            temp_path.unlink()
            temp_dir.rmdir()

    def test_get_file_metadata_with_override(self):
        """Test that explicit overrides take precedence."""
        content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-22
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            # Override week_ending explicitly
            metadata = get_file_metadata(
                temp_path,
                week_ending_override=date(2025, 12, 26),
            )

            # Override should win
            assert metadata.week_ending == date(2025, 12, 26)
            assert metadata.source == "override"
        finally:
            Path(temp_path).unlink()

    def test_stored_week_ending_matches_derivation(self):
        """
        Integration test: Given lastUpdateDate = 2025-12-22,
        the stored week_ending should = 2025-12-19.
        """
        # Parse content with lastUpdateDate
        content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-22
"""
        records = list(parse_finra_content(content))

        # Record should have derived week_ending (not the lastUpdateDate)
        assert len(records) == 1
        assert records[0].week_ending == date(2025, 12, 19)
        assert records[0].source_last_update_date == date(2025, 12, 22)
