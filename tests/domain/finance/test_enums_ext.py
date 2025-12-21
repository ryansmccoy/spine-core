"""Tests for domain finance enums — all enum classes with full member coverage.

Uses parametrized tests for bulk enum member instantiation coverage.
"""

from __future__ import annotations

import pytest

from spine.domain.finance.enums import (
    AccountingBasis,
    MetricCategory,
    MetricCode,
    ObservationType,
    PeriodType,
    PerShareType,
    Presentation,
    ScopeType,
)


class TestMetricCode:
    def test_member_count(self):
        assert len(MetricCode) > 50  # Has ~89 members

    def test_revenue(self):
        assert MetricCode.REVENUE.value == "revenue"

    def test_value_access(self):
        m = MetricCode("revenue")
        assert m == MetricCode.REVENUE

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            MetricCode("nonexistent_metric")

    @pytest.mark.parametrize("member", list(MetricCode))
    def test_all_members_are_strings(self, member):
        assert isinstance(member.value, str)
        assert len(member.value) > 0


class TestMetricCategory:
    @pytest.mark.parametrize("member", list(MetricCategory))
    def test_all_members(self, member):
        assert isinstance(member.value, str)

    def test_income_statement(self):
        assert MetricCategory("income_statement") == MetricCategory.INCOME_STATEMENT

    def test_balance_sheet(self):
        assert MetricCategory("balance_sheet") == MetricCategory.BALANCE_SHEET


class TestAccountingBasis:
    @pytest.mark.parametrize("member", list(AccountingBasis))
    def test_all_members(self, member):
        assert isinstance(member.value, str)

    def test_gaap(self):
        assert AccountingBasis.GAAP.value == "gaap"

    def test_ifrs(self):
        assert AccountingBasis.IFRS.value == "ifrs"


class TestPresentation:
    @pytest.mark.parametrize("member", list(Presentation))
    def test_all_members(self, member):
        assert isinstance(member.value, str)

    def test_reported(self):
        assert Presentation.REPORTED.value == "reported"


class TestPerShareType:
    @pytest.mark.parametrize("member", list(PerShareType))
    def test_all_members(self, member):
        assert isinstance(member.value, str)

    def test_basic(self):
        assert PerShareType.BASIC.value == "basic"


class TestScopeType:
    @pytest.mark.parametrize("member", list(ScopeType))
    def test_all_members(self, member):
        assert isinstance(member.value, str)


class TestPeriodType:
    @pytest.mark.parametrize("member", list(PeriodType))
    def test_all_members(self, member):
        assert isinstance(member.value, str)

    def test_annual(self):
        assert PeriodType.ANNUAL.value == "annual"


class TestObservationType:
    @pytest.mark.parametrize("member", list(ObservationType))
    def test_all_members(self, member):
        assert isinstance(member.value, str)

    def test_actual(self):
        assert ObservationType.ACTUAL.value == "actual"
