"""Tests for spine.core.finance — adjustments and corrections."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from spine.core.finance.adjustments import (
    AdjustmentChain,
    AdjustmentFactor,
    AdjustmentMethod,
)
from spine.core.finance.corrections import CorrectionReason, CorrectionRecord


# ======================================================================
# AdjustmentMethod enum
# ======================================================================


class TestAdjustmentMethod:
    """AdjustmentMethod enum basics."""

    def test_all_members_exist(self) -> None:
        expected = {
            "SPLIT", "REVERSE_SPLIT", "STOCK_DIVIDEND", "CASH_DIVIDEND",
            "SPIN_OFF", "RIGHTS_ISSUE", "SPECIAL_DIVIDEND", "MERGER", "OTHER",
        }
        assert set(AdjustmentMethod.__members__) == expected

    def test_str_enum_value(self) -> None:
        assert AdjustmentMethod.SPLIT == "split"
        assert AdjustmentMethod.MERGER.value == "merger"

    def test_from_string(self) -> None:
        assert AdjustmentMethod("split") is AdjustmentMethod.SPLIT


# ======================================================================
# AdjustmentFactor
# ======================================================================


class TestAdjustmentFactor:
    """Single adjustment factor tests."""

    @pytest.fixture()
    def split_2_for_1(self) -> AdjustmentFactor:
        return AdjustmentFactor(
            effective_date=date(2025, 6, 15),
            factor=2.0,
            method=AdjustmentMethod.SPLIT,
            description="2-for-1 stock split",
        )

    def test_creation(self, split_2_for_1: AdjustmentFactor) -> None:
        assert split_2_for_1.effective_date == date(2025, 6, 15)
        assert split_2_for_1.factor == 2.0
        assert split_2_for_1.method is AdjustmentMethod.SPLIT
        assert split_2_for_1.description == "2-for-1 stock split"

    def test_frozen(self, split_2_for_1: AdjustmentFactor) -> None:
        with pytest.raises(AttributeError):
            split_2_for_1.factor = 3.0  # type: ignore[misc]

    def test_defaults(self) -> None:
        f = AdjustmentFactor(
            effective_date=date(2025, 1, 1),
            factor=1.5,
            method=AdjustmentMethod.OTHER,
        )
        assert f.description == ""
        assert f.entity_key == ""
        assert f.metadata == {}

    def test_adjust(self, split_2_for_1: AdjustmentFactor) -> None:
        assert split_2_for_1.adjust(100.0) == 200.0

    def test_unadjust(self, split_2_for_1: AdjustmentFactor) -> None:
        assert split_2_for_1.unadjust(200.0) == 100.0

    def test_inverse_factor(self, split_2_for_1: AdjustmentFactor) -> None:
        assert split_2_for_1.inverse_factor == 0.5

    def test_inverse_factor_zero_raises(self) -> None:
        f = AdjustmentFactor(
            effective_date=date(2025, 1, 1),
            factor=0.0,
            method=AdjustmentMethod.OTHER,
        )
        with pytest.raises(ZeroDivisionError):
            _ = f.inverse_factor

    def test_reverse_split(self) -> None:
        f = AdjustmentFactor(
            effective_date=date(2025, 3, 1),
            factor=0.1,
            method=AdjustmentMethod.REVERSE_SPLIT,
            description="1-for-10 reverse split",
        )
        # $10 pre-reverse → $1 post-reverse
        assert f.adjust(10.0) == pytest.approx(1.0)
        assert f.unadjust(1.0) == pytest.approx(10.0)

    def test_metadata(self) -> None:
        f = AdjustmentFactor(
            effective_date=date(2025, 1, 1),
            factor=2.0,
            method=AdjustmentMethod.SPLIT,
            entity_key="AAPL",
            metadata={"source": "vendor_feed"},
        )
        assert f.entity_key == "AAPL"
        assert f.metadata["source"] == "vendor_feed"


# ======================================================================
# AdjustmentChain
# ======================================================================


class TestAdjustmentChain:
    """Chained adjustment tests."""

    @pytest.fixture()
    def two_splits(self) -> AdjustmentChain:
        return AdjustmentChain(
            factors=[
                AdjustmentFactor(date(2025, 1, 1), 2.0, AdjustmentMethod.SPLIT),
                AdjustmentFactor(date(2025, 6, 1), 4.0, AdjustmentMethod.SPLIT),
            ],
            entity_key="TEST",
        )

    def test_composite_factor(self, two_splits: AdjustmentChain) -> None:
        assert two_splits.composite_factor == 8.0

    def test_inverse_composite(self, two_splits: AdjustmentChain) -> None:
        assert two_splits.inverse_composite_factor == pytest.approx(0.125)

    def test_adjust(self, two_splits: AdjustmentChain) -> None:
        assert two_splits.adjust(100.0) == 800.0

    def test_unadjust(self, two_splits: AdjustmentChain) -> None:
        assert two_splits.unadjust(800.0) == pytest.approx(100.0)

    def test_empty_chain(self) -> None:
        chain = AdjustmentChain()
        assert chain.composite_factor == 1.0
        assert chain.adjust(42.0) == 42.0

    def test_sorted_factors(self) -> None:
        chain = AdjustmentChain(factors=[
            AdjustmentFactor(date(2025, 12, 1), 3.0, AdjustmentMethod.SPLIT),
            AdjustmentFactor(date(2025, 1, 1), 2.0, AdjustmentMethod.SPLIT),
        ])
        sorted_f = chain.sorted_factors
        assert sorted_f[0].effective_date < sorted_f[1].effective_date

    def test_adjust_as_of(self, two_splits: AdjustmentChain) -> None:
        # Only the first split (factor=2) applies before 2025-03-01
        result = two_splits.adjust_as_of(100.0, date(2025, 3, 1))
        assert result == 200.0

    def test_adjust_as_of_all(self, two_splits: AdjustmentChain) -> None:
        # Both splits apply at 2025-12-31
        result = two_splits.adjust_as_of(100.0, date(2025, 12, 31))
        assert result == 800.0

    def test_adjust_as_of_none(self, two_splits: AdjustmentChain) -> None:
        # No splits apply before 2024-01-01
        result = two_splits.adjust_as_of(100.0, date(2024, 1, 1))
        assert result == 100.0

    def test_append(self, two_splits: AdjustmentChain) -> None:
        new_factor = AdjustmentFactor(
            date(2026, 1, 1), 5.0, AdjustmentMethod.SPLIT,
        )
        extended = two_splits.append(new_factor)
        assert len(extended.factors) == 3
        assert extended.composite_factor == 40.0
        # Original is unchanged (frozen)
        assert len(two_splits.factors) == 2

    def test_merge(self) -> None:
        chain_a = AdjustmentChain(
            factors=[AdjustmentFactor(date(2025, 1, 1), 2.0, AdjustmentMethod.SPLIT)],
            entity_key="AAPL",
        )
        chain_b = AdjustmentChain(
            factors=[AdjustmentFactor(date(2025, 6, 1), 3.0, AdjustmentMethod.SPLIT)],
        )
        merged = chain_a.merge(chain_b)
        assert len(merged.factors) == 2
        assert merged.composite_factor == 6.0
        assert merged.entity_key == "AAPL"

    def test_factors_between(self, two_splits: AdjustmentChain) -> None:
        result = two_splits.factors_between(date(2025, 1, 1), date(2025, 3, 1))
        assert len(result) == 1
        assert result[0].factor == 2.0

    def test_factors_between_all(self, two_splits: AdjustmentChain) -> None:
        result = two_splits.factors_between(date(2025, 1, 1), date(2025, 12, 31))
        assert len(result) == 2

    def test_zero_composite_raises(self) -> None:
        chain = AdjustmentChain(factors=[
            AdjustmentFactor(date(2025, 1, 1), 0.0, AdjustmentMethod.OTHER),
        ])
        with pytest.raises(ZeroDivisionError):
            _ = chain.inverse_composite_factor


# ======================================================================
# CorrectionReason enum
# ======================================================================


class TestCorrectionReason:
    """CorrectionReason enum basics."""

    def test_all_members_exist(self) -> None:
        expected = {
            "RESTATEMENT", "DATA_ERROR", "METHODOLOGY_CHANGE",
            "LATE_REPORTING", "ROUNDING", "UNIT_CONVERSION",
            "VENDOR_CORRECTION", "MANUAL", "OTHER",
        }
        assert set(CorrectionReason.__members__) == expected

    def test_str_enum_value(self) -> None:
        assert CorrectionReason.RESTATEMENT == "restatement"
        assert CorrectionReason.DATA_ERROR.value == "data_error"


# ======================================================================
# CorrectionRecord
# ======================================================================


class TestCorrectionRecord:
    """CorrectionRecord tests."""

    @pytest.fixture()
    def eps_correction(self) -> CorrectionRecord:
        return CorrectionRecord.create(
            entity_key="AAPL",
            field_name="eps_diluted",
            original_value=1.52,
            corrected_value=1.46,
            reason=CorrectionReason.RESTATEMENT,
            corrected_by="sec_filing_parser",
            source_ref="10-K/A filed 2025-03-15",
        )

    def test_create_generates_id(self, eps_correction: CorrectionRecord) -> None:
        assert eps_correction.correction_id
        assert len(eps_correction.correction_id) > 10

    def test_create_sets_timestamp(self, eps_correction: CorrectionRecord) -> None:
        assert isinstance(eps_correction.corrected_at, datetime)
        assert eps_correction.corrected_at.tzinfo is not None

    def test_frozen(self, eps_correction: CorrectionRecord) -> None:
        with pytest.raises(AttributeError):
            eps_correction.corrected_value = 9.99  # type: ignore[misc]

    def test_delta(self, eps_correction: CorrectionRecord) -> None:
        assert eps_correction.delta == pytest.approx(-0.06)

    def test_pct_change(self, eps_correction: CorrectionRecord) -> None:
        pct = eps_correction.pct_change
        assert pct is not None
        assert pct == pytest.approx(-0.06 / 1.52)

    def test_abs_pct_change(self, eps_correction: CorrectionRecord) -> None:
        apct = eps_correction.abs_pct_change
        assert apct is not None
        assert apct == pytest.approx(0.06 / 1.52)

    def test_pct_change_zero_original(self) -> None:
        rec = CorrectionRecord.create(
            entity_key="X",
            field_name="metric",
            original_value=0.0,
            corrected_value=5.0,
            reason=CorrectionReason.DATA_ERROR,
        )
        assert rec.pct_change is None
        assert rec.abs_pct_change is None

    def test_to_dict(self, eps_correction: CorrectionRecord) -> None:
        d = eps_correction.to_dict()
        assert d["entity_key"] == "AAPL"
        assert d["field_name"] == "eps_diluted"
        assert d["reason"] == "restatement"
        assert d["corrected_by"] == "sec_filing_parser"
        assert isinstance(d["corrected_at"], str)

    def test_create_with_notes_and_metadata(self) -> None:
        rec = CorrectionRecord.create(
            entity_key="MSFT",
            field_name="revenue",
            original_value=56_189e6,
            corrected_value=56_517e6,
            reason=CorrectionReason.RESTATEMENT,
            notes="Restated per amended 10-K",
            metadata={"filing_id": "0001564590-25-012345"},
        )
        assert rec.notes == "Restated per amended 10-K"
        assert rec.metadata["filing_id"] == "0001564590-25-012345"

    def test_positive_correction(self) -> None:
        rec = CorrectionRecord.create(
            entity_key="GOOG",
            field_name="shares_outstanding",
            original_value=1_000_000,
            corrected_value=1_200_000,
            reason=CorrectionReason.LATE_REPORTING,
        )
        assert rec.delta == 200_000
        pct = rec.pct_change
        assert pct is not None
        assert pct == pytest.approx(0.2)

    def test_to_dict_roundtrip_keys(self, eps_correction: CorrectionRecord) -> None:
        d = eps_correction.to_dict()
        expected_keys = {
            "correction_id", "entity_key", "field_name",
            "original_value", "corrected_value", "reason",
            "corrected_at", "corrected_by", "source_ref",
            "notes", "metadata",
        }
        assert set(d.keys()) == expected_keys


# ======================================================================
# Package-level imports
# ======================================================================


class TestPackageImports:
    """Verify spine.core.finance re‐exports work."""

    def test_import_from_package(self) -> None:
        from spine.core.finance import (
            AdjustmentChain,
            AdjustmentFactor,
            AdjustmentMethod,
            CorrectionReason,
            CorrectionRecord,
        )
        assert AdjustmentChain is not None
        assert AdjustmentFactor is not None
        assert AdjustmentMethod is not None
        assert CorrectionReason is not None
        assert CorrectionRecord is not None
