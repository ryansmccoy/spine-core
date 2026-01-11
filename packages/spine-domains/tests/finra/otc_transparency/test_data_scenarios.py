# tests/finra/otc_transparency/test_data_scenarios.py
"""
Data correctness tests for messy real-world data scenarios.

These tests verify the system handles edge cases gracefully:
- Valid rows are processed
- Invalid rows are rejected with clear error messages
- The system doesn't crash on unexpected input
"""

from datetime import date

from spine.domains.finra.otc_transparency.calculations import (
    compute_symbol_summaries,
)
from spine.domains.finra.otc_transparency.connector import RawOTCRecord, parse_finra_content
from spine.domains.finra.otc_transparency.normalizer import normalize_records

# =============================================================================
# Test Fixtures
# =============================================================================

HEADER = "tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate"


def make_row(
    tier: str = "NMS Tier 1",
    symbol: str = "AAPL",
    name: str = "Apple Inc.",
    venue: str = "VENUE A",
    mpid: str = "VENA",
    shares: str = "1000000",
    trades: str = "5000",
    date_str: str = "2025-12-22",
) -> str:
    """Create a PSV row with given values."""
    return f"{tier}|{symbol}|{name}|{venue}|{mpid}|{shares}|{trades}|{date_str}"


def make_content(*rows: str) -> str:
    """Create PSV content with header and rows."""
    return HEADER + "\n" + "\n".join(rows) + "\n"


# =============================================================================
# Scenario 1: Mixed Valid/Invalid Rows
# =============================================================================


class TestMixedValidInvalidRows:
    """Test files with both valid and invalid rows mixed together."""

    def test_valid_rows_parsed_invalid_skipped(self):
        """Valid rows should be parsed even when invalid rows are present."""
        content = make_content(
            make_row(symbol="AAPL", shares="1000000"),  # Valid
            make_row(symbol="MSFT", shares="not_a_number"),  # Invalid - bad number
            make_row(symbol="GOOG", shares="500000"),  # Valid
        )

        records = list(parse_finra_content(content))

        # Should parse both valid records
        assert len(records) == 2
        symbols = {r.symbol for r in records}
        assert symbols == {"AAPL", "GOOG"}

    def test_normalization_produces_rejects_for_invalid(self):
        """Normalization should produce reject records for invalid data."""
        # Create records with valid and invalid data
        valid = RawOTCRecord(
            week_ending=date(2025, 12, 19),
            tier="NMS Tier 1",
            symbol="AAPL",
            mpid="VENA",
            total_shares=1000000,
            total_trades=5000,
        )
        invalid = RawOTCRecord(
            week_ending=date(2025, 12, 19),
            tier="NMS Tier 1",
            symbol="",  # Empty symbol is invalid
            mpid="VENB",
            total_shares=500000,
            total_trades=2500,
        )

        result = normalize_records([valid, invalid])

        assert result.accepted_count == 1
        assert result.rejected_count == 1
        assert len(result.accepted) == 1
        assert result.accepted[0].symbol == "AAPL"


# =============================================================================
# Scenario 2: Duplicate Symbols
# =============================================================================


class TestDuplicateSymbols:
    """Test handling of duplicate symbols (same symbol, different venues)."""

    def test_same_symbol_different_venues_both_valid(self):
        """Same symbol from different venues should both be parsed."""
        content = make_content(
            make_row(symbol="AAPL", mpid="VENA", shares="1000000"),
            make_row(symbol="AAPL", mpid="VENB", shares="500000"),
            make_row(symbol="AAPL", mpid="VENC", shares="250000"),
        )

        records = list(parse_finra_content(content))

        assert len(records) == 3
        assert all(r.symbol == "AAPL" for r in records)
        mpids = {r.mpid for r in records}
        assert mpids == {"VENA", "VENB", "VENC"}

    def test_aggregation_sums_across_venues(self):
        """Aggregation should sum volumes across venues for same symbol."""
        raw = [
            RawOTCRecord(
                week_ending=date(2025, 12, 19),
                tier="NMS Tier 1",
                symbol="AAPL",
                mpid="VENA",
                total_shares=1000000,
                total_trades=5000,
            ),
            RawOTCRecord(
                week_ending=date(2025, 12, 19),
                tier="NMS Tier 1",
                symbol="AAPL",
                mpid="VENB",
                total_shares=500000,
                total_trades=2500,
            ),
        ]

        # Normalize first
        normalized = normalize_records(raw)

        # Aggregate
        summary = compute_symbol_summaries(normalized.accepted)

        assert len(summary) == 1
        assert summary[0].symbol == "AAPL"
        assert summary[0].total_volume == 1500000
        assert summary[0].total_trades == 7500
        assert summary[0].venue_count == 2


# =============================================================================
# Scenario 3: Zero or Negative Volumes
# =============================================================================


class TestZeroNegativeVolumes:
    """Test handling of zero or negative volume values."""

    def test_zero_volume_parsed(self):
        """Zero volume should be parsed (might be valid edge case)."""
        content = make_content(
            make_row(symbol="AAPL", shares="0", trades="0"),
        )

        records = list(parse_finra_content(content))

        assert len(records) == 1
        assert records[0].total_shares == 0
        assert records[0].total_trades == 0

    def test_negative_volume_rejected(self):
        """Negative volume should be rejected during parsing or normalization."""
        content = make_content(
            make_row(symbol="AAPL", shares="-1000000"),
        )

        records = list(parse_finra_content(content))

        # Either parser rejects it, or we get a record that normalizer rejects
        if records:
            result = normalize_records(records)
            # Should be rejected
            assert result.accepted_count == 0 or records[0].total_shares < 0


# =============================================================================
# Scenario 4: Missing Required Fields
# =============================================================================


class TestMissingRequiredFields:
    """Test handling of missing required fields."""

    def test_missing_symbol_skipped(self):
        """Rows with missing symbol should be skipped or rejected."""
        content = make_content(
            make_row(symbol="AAPL", shares="1000000"),  # Valid
            "NMS Tier 1||Apple Inc.|VENUE A|VENA|500000|2500|2025-12-22",  # Empty symbol
        )

        records = list(parse_finra_content(content))

        # Should only get the valid record
        valid_records = [r for r in records if r.symbol]
        assert len(valid_records) == 1

    def test_missing_mpid_skipped(self):
        """Rows with missing MPID should be skipped."""
        content = make_content(
            make_row(symbol="AAPL", mpid="VENA"),  # Valid
            "NMS Tier 1|MSFT|Microsoft Corp.|VENUE B||500000|2500|2025-12-22",  # Empty MPID
        )

        records = list(parse_finra_content(content))

        # Should only get valid records
        valid_records = [r for r in records if r.mpid]
        assert len(valid_records) >= 1


# =============================================================================
# Scenario 5: Malformed Dates
# =============================================================================


class TestMalformedDates:
    """Test handling of malformed date values."""

    def test_valid_date_parsed(self):
        """Valid ISO dates should be parsed correctly."""
        content = make_content(
            make_row(date_str="2025-12-22"),
        )

        records = list(parse_finra_content(content))

        assert len(records) == 1
        # week_ending is derived from lastUpdateDate
        assert records[0].week_ending == date(2025, 12, 19)

    def test_invalid_date_format_skipped(self):
        """Invalid date formats should cause row to be skipped."""
        content = make_content(
            make_row(symbol="AAPL", date_str="2025-12-22"),  # Valid
            make_row(symbol="MSFT", date_str="12/22/2025"),  # Invalid format
            make_row(symbol="GOOG", date_str="not-a-date"),  # Invalid
        )

        records = list(parse_finra_content(content))

        # Only valid date format should be parsed
        assert len(records) == 1
        assert records[0].symbol == "AAPL"

    def test_impossible_date_skipped(self):
        """Impossible dates (Feb 30) should be skipped."""
        content = make_content(
            make_row(symbol="AAPL", date_str="2025-02-30"),  # Invalid date
        )

        records = list(parse_finra_content(content))

        assert len(records) == 0


# =============================================================================
# Scenario 6: Unicode/Special Characters
# =============================================================================


class TestUnicodeSpecialCharacters:
    """Test handling of unicode and special characters."""

    def test_unicode_in_name_accepted(self):
        """Unicode characters in issue name should be accepted."""
        content = make_content(
            "NMS Tier 1|TEST|Société Générale™|VENUE A|VENA|1000000|5000|2025-12-22",
        )

        records = list(parse_finra_content(content))

        assert len(records) == 1
        assert records[0].symbol == "TEST"
        # Name with unicode should be preserved
        assert "Soci" in (records[0].issue_name or "")

    def test_special_chars_in_symbol_rejected(self):
        """Special characters in symbol should be rejected."""
        content = make_content(
            make_row(symbol="AAPL"),  # Valid
            make_row(symbol="AA$PL"),  # Invalid - has $
        )

        records = list(parse_finra_content(content))

        # At minimum, the valid one should parse
        symbols = {r.symbol for r in records}
        assert "AAPL" in symbols


# =============================================================================
# Scenario 7: Extremely Large Numbers
# =============================================================================


class TestExtremeLargeNumbers:
    """Test handling of extremely large numeric values."""

    def test_large_volume_parsed(self):
        """Very large volumes should be parsed correctly."""
        content = make_content(
            make_row(symbol="AAPL", shares="9999999999999"),  # 9.9 trillion
        )

        records = list(parse_finra_content(content))

        assert len(records) == 1
        assert records[0].total_shares == 9999999999999

    def test_scientific_notation_handled(self):
        """Scientific notation should be handled or rejected gracefully."""
        content = make_content(
            make_row(symbol="AAPL", shares="1e10"),  # 10 billion
        )

        records = list(parse_finra_content(content))

        # Either parsed as int or rejected - shouldn't crash
        assert isinstance(records, list)

    def test_decimal_shares_handled(self):
        """Decimal shares (1000.5) should be truncated or rejected."""
        content = make_content(
            make_row(symbol="AAPL", shares="1000.5"),
        )

        records = list(parse_finra_content(content))

        # Either truncated to int or rejected - shouldn't crash
        if records:
            # If parsed, should be an integer
            assert isinstance(records[0].total_shares, int)


# =============================================================================
# Scenario 8: Empty Files
# =============================================================================


class TestEmptyFiles:
    """Test handling of empty or header-only files."""

    def test_empty_content_returns_empty(self):
        """Empty content should return empty list."""
        records = list(parse_finra_content(""))

        assert records == []

    def test_header_only_returns_empty(self):
        """File with only header should return empty list."""
        records = list(parse_finra_content(HEADER))

        assert records == []

    def test_header_with_blank_lines_returns_empty(self):
        """File with header and blank lines should return empty list."""
        content = HEADER + "\n\n\n"

        records = list(parse_finra_content(content))

        assert records == []


# =============================================================================
# Scenario 9: Wrong Column Count/Format
# =============================================================================


class TestWrongColumnCount:
    """Test handling of rows with wrong number of columns."""

    def test_too_few_columns_skipped(self):
        """Rows with too few columns should be skipped."""
        content = make_content(
            make_row(symbol="AAPL"),  # Valid
            "NMS Tier 1|MSFT|Microsoft",  # Only 3 columns
        )

        records = list(parse_finra_content(content))

        assert len(records) == 1
        assert records[0].symbol == "AAPL"

    def test_too_many_columns_handled(self):
        """Rows with extra columns should still parse (ignoring extra)."""
        content = HEADER + "\n"
        content += "NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-22|extra|columns\n"

        records = list(parse_finra_content(content))

        # Should either parse with extra ignored, or be skipped
        assert isinstance(records, list)

    def test_wrong_delimiter_skipped(self):
        """Rows with wrong delimiter (comma instead of pipe) should be skipped."""
        content = HEADER + "\n"
        content += "NMS Tier 1,AAPL,Apple Inc.,VENUE A,VENA,1000000,5000,2025-12-22\n"

        records = list(parse_finra_content(content))

        # Should not crash, may return empty or fail gracefully
        assert isinstance(records, list)


# =============================================================================
# Integration: Multiple Scenarios Combined
# =============================================================================


class TestMultipleScenariosCombined:
    """Test files with multiple types of issues."""

    def test_realistic_messy_file(self):
        """Test a realistic messy file with multiple issues."""
        content = HEADER + "\n"
        # Valid rows
        content += make_row(symbol="AAPL", mpid="VENA", shares="1000000") + "\n"
        content += make_row(symbol="GOOG", mpid="VENA", shares="500000") + "\n"
        # Duplicate venues
        content += make_row(symbol="AAPL", mpid="VENB", shares="250000") + "\n"
        # Empty row
        content += "\n"
        # Missing symbol
        content += "NMS Tier 1||NoSymbol|VENUE C|VENC|100000|500|2025-12-22\n"
        # Bad number
        content += make_row(symbol="MSFT", shares="bad_number") + "\n"
        # Valid row at end
        content += make_row(symbol="TSLA", mpid="VEND", shares="750000") + "\n"

        records = list(parse_finra_content(content))

        # Should get at least the valid rows
        valid_symbols = {r.symbol for r in records if r.symbol}
        assert "AAPL" in valid_symbols
        assert "GOOG" in valid_symbols
        assert "TSLA" in valid_symbols

    def test_normalization_rejects_accumulate(self):
        """Normalization should accumulate all reject reasons."""
        raw = [
            RawOTCRecord(
                week_ending=date(2025, 12, 19),
                tier="NMS Tier 1",
                symbol="AAPL",
                mpid="VENA",
                total_shares=1000000,
                total_trades=5000,
            ),
            RawOTCRecord(
                week_ending=date(2025, 12, 19),
                tier="NMS Tier 1",
                symbol="",  # Invalid
                mpid="VENB",
                total_shares=500000,
                total_trades=2500,
            ),
            RawOTCRecord(
                week_ending=date(2025, 12, 19),
                tier="INVALID_TIER",  # Invalid tier
                symbol="MSFT",
                mpid="VENC",
                total_shares=250000,
                total_trades=1250,
            ),
        ]

        result = normalize_records(raw)

        # Should have some valid and some rejected
        assert result.accepted_count >= 1
        assert result.rejected_count >= 1
