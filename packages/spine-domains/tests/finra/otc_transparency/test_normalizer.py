# tests/finra/otc_transparency/test_normalizer.py

"""Tests for FINRA OTC Transparency normalizer and validation."""

from datetime import date

from spine.domains.finra.otc_transparency.connector import RawOTCRecord
from spine.domains.finra.otc_transparency.normalizer import normalize_records
from spine.domains.finra.otc_transparency.schema import Tier


class TestNormalizer:
    """Tests for record normalization and validation."""

    def test_normalize_valid_record(self):
        """Test normalizing a valid raw record."""
        raw = RawOTCRecord(
            week_ending=date(2026, 1, 3),
            tier="NMS Tier 1",
            symbol="AAPL",
            mpid="VENA",
            total_shares=1000000,
            total_trades=5000,
        )

        result = normalize_records([raw])

        assert result.accepted_count == 1
        assert result.rejected_count == 0
        assert result.accepted[0].symbol == "AAPL"
        assert result.accepted[0].tier == Tier.NMS_TIER_1
        assert result.accepted[0].mpid == "VENA"

    def test_normalize_rejects_invalid_symbol(self):
        """Test that empty symbols are rejected."""
        raw = RawOTCRecord(
            week_ending=date(2026, 1, 3),
            tier="NMS Tier 1",
            symbol="",  # Invalid: empty symbol
            mpid="VENA",
            total_shares=1000000,
            total_trades=5000,
        )

        result = normalize_records([raw])

        assert result.accepted_count == 0
        assert result.rejected_count == 1
        assert "symbol" in " ".join(result.rejected[0].reasons).lower()

    def test_normalize_rejects_negative_volume(self):
        """Test that negative volumes are rejected."""
        raw = RawOTCRecord(
            week_ending=date(2026, 1, 3),
            tier="NMS Tier 1",
            symbol="AAPL",
            mpid="VENA",
            total_shares=-100,  # Invalid: negative
            total_trades=5000,
        )

        result = normalize_records([raw])

        assert result.accepted_count == 0
        assert result.rejected_count == 1
        assert "negative" in " ".join(result.rejected[0].reasons).lower()

    def test_normalize_multiple_records(self):
        """Test normalizing multiple records with mixed validity."""
        records = [
            RawOTCRecord(
                week_ending=date(2026, 1, 3),
                tier="NMS Tier 1",
                symbol="AAPL",
                mpid="VENA",
                total_shares=1000000,
                total_trades=5000,
            ),
            RawOTCRecord(
                week_ending=date(2026, 1, 3),
                tier="NMS Tier 1",
                symbol="",  # Invalid
                mpid="VENB",
                total_shares=500000,
                total_trades=2500,
            ),
            RawOTCRecord(
                week_ending=date(2026, 1, 3),
                tier="NMS Tier 2",
                symbol="MSFT",
                mpid="VENC",
                total_shares=750000,
                total_trades=3000,
            ),
        ]

        result = normalize_records(records)

        assert result.accepted_count == 2
        assert result.rejected_count == 1
        assert result.accepted[0].symbol == "AAPL"
        assert result.accepted[1].symbol == "MSFT"
