"""Tests for spine.domain.finance.enums — financial observation enums.

These tests exercise all enum classes to ensure they are importable,
have the expected values, and are str-based for JSON serialization.
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


# =============================================================================
# MetricCode
# =============================================================================


class TestMetricCode:
    """MetricCode enum tests."""

    def test_is_str_enum(self):
        assert isinstance(MetricCode.REVENUE, str)

    def test_income_statement_metrics(self):
        assert MetricCode.REVENUE.value == "revenue"
        assert MetricCode.NET_INCOME.value == "net_income"
        assert MetricCode.EBITDA.value == "ebitda"
        assert MetricCode.EBIT.value == "ebit"
        assert MetricCode.GROSS_PROFIT.value == "gross_profit"
        assert MetricCode.OPERATING_INCOME.value == "operating_income"
        assert MetricCode.PRETAX_INCOME.value == "pretax_income"
        assert MetricCode.COST_OF_REVENUE.value == "cost_of_revenue"
        assert MetricCode.RD_EXPENSE.value == "rd_expense"
        assert MetricCode.SGA_EXPENSE.value == "sga_expense"
        assert MetricCode.INTEREST_EXPENSE.value == "interest_expense"
        assert MetricCode.INTEREST_INCOME.value == "interest_income"
        assert MetricCode.OTHER_INCOME.value == "other_income"
        assert MetricCode.INCOME_TAX.value == "income_tax"
        assert MetricCode.NET_INCOME_COMMON.value == "net_income_common"

    def test_per_share_metrics(self):
        assert MetricCode.EPS.value == "eps"
        assert MetricCode.EPS_BASIC.value == "eps_basic"
        assert MetricCode.EPS_DILUTED.value == "eps_diluted"
        assert MetricCode.DPS.value == "dps"
        assert MetricCode.BPS.value == "bps"
        assert MetricCode.CFPS.value == "cfps"
        assert MetricCode.BVPS.value == "bvps"
        assert MetricCode.FCF.value == "fcf"

    def test_balance_sheet_assets(self):
        assert MetricCode.CASH.value == "cash"
        assert MetricCode.TOTAL_ASSETS.value == "total_assets"
        assert MetricCode.TOTAL_CURRENT_ASSETS.value == "total_current_assets"
        assert MetricCode.ACCOUNTS_RECEIVABLE.value == "accounts_receivable"
        assert MetricCode.INVENTORY.value == "inventory"
        assert MetricCode.GOODWILL.value == "goodwill"
        assert MetricCode.INTANGIBLES.value == "intangibles"
        assert MetricCode.PP_AND_E.value == "pp_and_e"

    def test_balance_sheet_liabilities(self):
        assert MetricCode.TOTAL_LIABILITIES.value == "total_liabilities"
        assert MetricCode.ACCOUNTS_PAYABLE.value == "accounts_payable"
        assert MetricCode.LONG_TERM_DEBT.value == "long_term_debt"
        assert MetricCode.SHORT_TERM_DEBT.value == "short_term_debt"
        assert MetricCode.DEFERRED_REVENUE.value == "deferred_revenue"

    def test_balance_sheet_equity(self):
        assert MetricCode.TOTAL_EQUITY.value == "total_equity"
        assert MetricCode.RETAINED_EARNINGS.value == "retained_earnings"
        assert MetricCode.COMMON_STOCK.value == "common_stock"
        assert MetricCode.PREFERRED_STOCK.value == "preferred_stock"
        assert MetricCode.TREASURY_STOCK.value == "treasury_stock"

    def test_cash_flow_metrics(self):
        assert MetricCode.CFO.value == "cfo"
        assert MetricCode.CFI.value == "cfi"
        assert MetricCode.CFF.value == "cff"
        assert MetricCode.CAPEX.value == "capex"
        assert MetricCode.FREE_CASH_FLOW.value == "free_cash_flow"
        assert MetricCode.DEPRECIATION.value == "depreciation"
        assert MetricCode.DIVIDENDS_PAID.value == "dividends_paid"

    def test_ratios(self):
        assert MetricCode.GROSS_MARGIN.value == "gross_margin"
        assert MetricCode.ROE.value == "roe"
        assert MetricCode.ROA.value == "roa"
        assert MetricCode.CURRENT_RATIO.value == "current_ratio"
        assert MetricCode.DEBT_TO_EQUITY.value == "debt_to_equity"

    def test_share_statistics(self):
        assert MetricCode.SHARES_OUTSTANDING.value == "shares_outstanding"
        assert MetricCode.MARKET_CAP.value == "market_cap"
        assert MetricCode.ENTERPRISE_VALUE.value == "enterprise_value"

    def test_special_codes(self):
        assert MetricCode.CUSTOM.value == "custom"
        assert MetricCode.OTHER.value == "other"

    def test_roundtrip_from_value(self):
        """Enum can be constructed from its string value."""
        assert MetricCode("revenue") is MetricCode.REVENUE
        assert MetricCode("eps") is MetricCode.EPS

    def test_member_count(self):
        """Sanity check — at least 70 metrics defined."""
        assert len(MetricCode) >= 70


# =============================================================================
# MetricCategory
# =============================================================================


class TestMetricCategory:
    def test_values(self):
        assert MetricCategory.INCOME_STATEMENT.value == "income_statement"
        assert MetricCategory.BALANCE_SHEET.value == "balance_sheet"
        assert MetricCategory.CASH_FLOW.value == "cash_flow"
        assert MetricCategory.PER_SHARE.value == "per_share"
        assert MetricCategory.RATIO.value == "ratio"
        assert MetricCategory.SHARE_COUNT.value == "share_count"
        assert MetricCategory.OTHER.value == "other"

    def test_is_str_enum(self):
        assert isinstance(MetricCategory.INCOME_STATEMENT, str)


# =============================================================================
# AccountingBasis
# =============================================================================


class TestAccountingBasis:
    def test_values(self):
        assert AccountingBasis.GAAP.value == "gaap"
        assert AccountingBasis.IFRS.value == "ifrs"
        assert AccountingBasis.STATUTORY.value == "statutory"
        assert AccountingBasis.REGULATORY.value == "regulatory"
        assert AccountingBasis.OTHER.value == "other"


# =============================================================================
# Presentation
# =============================================================================


class TestPresentation:
    def test_values(self):
        assert Presentation.REPORTED.value == "reported"
        assert Presentation.COMPANY_ADJUSTED.value == "company_adjusted"
        assert Presentation.VENDOR_NORMALIZED.value == "vendor_normalized"
        assert Presentation.PRO_FORMA.value == "pro_forma"


# =============================================================================
# PerShareType
# =============================================================================


class TestPerShareType:
    def test_values(self):
        assert PerShareType.BASIC.value == "basic"
        assert PerShareType.DILUTED.value == "diluted"


# =============================================================================
# ScopeType
# =============================================================================


class TestScopeType:
    def test_values(self):
        assert ScopeType.TOTAL.value == "total"
        assert ScopeType.CONTINUING.value == "continuing"
        assert ScopeType.DISCONTINUED.value == "discontinued"


# =============================================================================
# PeriodType
# =============================================================================


class TestPeriodType:
    def test_values(self):
        assert PeriodType.ANNUAL.value == "annual"
        assert PeriodType.QUARTERLY.value == "quarterly"
        assert PeriodType.SEMI_ANNUAL.value == "semi_annual"
        assert PeriodType.TTM.value == "ttm"
        assert PeriodType.YTD.value == "ytd"
        assert PeriodType.LTM.value == "ltm"
        assert PeriodType.NTM.value == "ntm"
        assert PeriodType.MONTHLY.value == "monthly"
        assert PeriodType.WEEKLY.value == "weekly"
        assert PeriodType.DAILY.value == "daily"

    def test_count(self):
        assert len(PeriodType) == 10


# =============================================================================
# ObservationType
# =============================================================================


class TestObservationType:
    def test_values(self):
        assert ObservationType.ACTUAL.value == "actual"
        assert ObservationType.ESTIMATE.value == "estimate"
        assert ObservationType.CONSENSUS.value == "consensus"
        assert ObservationType.GUIDANCE.value == "guidance"
        assert ObservationType.PRELIMINARY.value == "preliminary"

    def test_is_str_enum(self):
        assert isinstance(ObservationType.ACTUAL, str)
        assert f"{ObservationType.ACTUAL}" == "ObservationType.ACTUAL" or ObservationType.ACTUAL == "actual"
