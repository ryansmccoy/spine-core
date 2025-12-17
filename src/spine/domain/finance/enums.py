"""
Financial observation and metric enums.

STDLIB ONLY - NO PYDANTIC.

These enums support the financial observation model with precise semantics
for metric identification, accounting basis, presentation, and provenance.

Originally from market-spine; promoted to spine-core for cross-spine reuse.
"""

from enum import Enum


class MetricCode(str, Enum):
    """
    Standardized metric codes for financial observations.

    Maps to standard financial statement line items.
    """

    # =========================================================================
    # Income Statement
    # =========================================================================
    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    RD_EXPENSE = "rd_expense"
    SGA_EXPENSE = "sga_expense"
    OPERATING_INCOME = "operating_income"
    INTEREST_EXPENSE = "interest_expense"
    INTEREST_INCOME = "interest_income"
    OTHER_INCOME = "other_income"
    PRETAX_INCOME = "pretax_income"
    INCOME_TAX = "income_tax"
    NET_INCOME = "net_income"
    NET_INCOME_COMMON = "net_income_common"
    EBITDA = "ebitda"
    EBIT = "ebit"

    # Per-share metrics
    EPS = "eps"
    EPS_BASIC = "eps_basic"
    EPS_DILUTED = "eps_diluted"
    DPS = "dps"  # Dividends per share
    BPS = "bps"  # Book value per share
    CFPS = "cfps"  # Cash flow per share
    BVPS = "bvps"  # Book value per share (alias)
    FCF = "fcf"  # Free cash flow

    # =========================================================================
    # Balance Sheet - Assets
    # =========================================================================
    CASH = "cash"
    CASH_EQUIVALENTS = "cash_equivalents"
    CASH_AND_EQUIVALENTS = "cash_and_equivalents"
    SHORT_TERM_INVESTMENTS = "short_term_investments"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    INVENTORY = "inventory"
    PREPAID_EXPENSES = "prepaid_expenses"
    OTHER_CURRENT_ASSETS = "other_current_assets"
    TOTAL_CURRENT_ASSETS = "total_current_assets"

    PP_AND_E = "pp_and_e"
    PP_AND_E_NET = "pp_and_e_net"
    GOODWILL = "goodwill"
    INTANGIBLES = "intangibles"
    OTHER_LONG_TERM_ASSETS = "other_long_term_assets"
    TOTAL_ASSETS = "total_assets"

    # =========================================================================
    # Balance Sheet - Liabilities
    # =========================================================================
    ACCOUNTS_PAYABLE = "accounts_payable"
    SHORT_TERM_DEBT = "short_term_debt"
    CURRENT_PORTION_LT_DEBT = "current_portion_lt_debt"
    ACCRUED_LIABILITIES = "accrued_liabilities"
    DEFERRED_REVENUE = "deferred_revenue"
    OTHER_CURRENT_LIABILITIES = "other_current_liabilities"
    TOTAL_CURRENT_LIABILITIES = "total_current_liabilities"

    LONG_TERM_DEBT = "long_term_debt"
    DEFERRED_TAX_LIABILITY = "deferred_tax_liability"
    OTHER_LONG_TERM_LIABILITIES = "other_long_term_liabilities"
    TOTAL_LIABILITIES = "total_liabilities"

    # =========================================================================
    # Balance Sheet - Equity
    # =========================================================================
    COMMON_STOCK = "common_stock"
    PREFERRED_STOCK = "preferred_stock"
    ADDITIONAL_PAID_IN_CAPITAL = "additional_paid_in_capital"
    RETAINED_EARNINGS = "retained_earnings"
    TREASURY_STOCK = "treasury_stock"
    ACCUMULATED_OCI = "accumulated_oci"
    TOTAL_EQUITY = "total_equity"
    TOTAL_LIABILITIES_AND_EQUITY = "total_liabilities_and_equity"
    MINORITY_INTEREST = "minority_interest"

    # =========================================================================
    # Cash Flow Statement
    # =========================================================================
    CFO = "cfo"  # Cash from operations
    CFI = "cfi"  # Cash from investing
    CFF = "cff"  # Cash from financing
    CAPEX = "capex"
    DEPRECIATION = "depreciation"
    AMORTIZATION = "amortization"
    STOCK_BASED_COMPENSATION = "stock_based_compensation"
    FREE_CASH_FLOW = "free_cash_flow"
    DIVIDENDS_PAID = "dividends_paid"
    SHARE_REPURCHASES = "share_repurchases"
    DEBT_ISSUED = "debt_issued"
    DEBT_REPAID = "debt_repaid"

    # =========================================================================
    # Ratios and Metrics
    # =========================================================================
    GROSS_MARGIN = "gross_margin"
    OPERATING_MARGIN = "operating_margin"
    NET_MARGIN = "net_margin"
    ROE = "roe"
    ROA = "roa"
    ROIC = "roic"
    CURRENT_RATIO = "current_ratio"
    QUICK_RATIO = "quick_ratio"
    DEBT_EQUITY = "debt_equity"
    DEBT_TO_EQUITY = "debt_to_equity"
    DEBT_TO_EBITDA = "debt_to_ebitda"
    INTEREST_COVERAGE = "interest_coverage"
    ASSET_TURNOVER = "asset_turnover"
    INVENTORY_TURNOVER = "inventory_turnover"
    RECEIVABLES_TURNOVER = "receivables_turnover"
    DAYS_SALES_OUTSTANDING = "days_sales_outstanding"
    DAYS_INVENTORY = "days_inventory"
    DAYS_PAYABLE = "days_payable"

    # =========================================================================
    # Share statistics
    # =========================================================================
    SHARES_OUTSTANDING = "shares_outstanding"
    WEIGHTED_AVG_SHARES_BASIC = "weighted_avg_shares_basic"
    WEIGHTED_AVG_SHARES_DILUTED = "weighted_avg_shares_diluted"
    MARKET_CAP = "market_cap"
    ENTERPRISE_VALUE = "enterprise_value"

    # =========================================================================
    # Segment/Geographic
    # =========================================================================
    SEGMENT_REVENUE = "segment_revenue"
    SEGMENT_OPERATING_INCOME = "segment_operating_income"
    SEGMENT_ASSETS = "segment_assets"
    GEOGRAPHIC_REVENUE = "geographic_revenue"

    # Custom/unmapped
    CUSTOM = "custom"
    OTHER = "other"


class MetricCategory(str, Enum):
    """
    Financial statement category for a metric.

    Groups metrics by their source statement.
    """

    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    PER_SHARE = "per_share"
    RATIO = "ratio"
    SHARE_COUNT = "share_count"
    OTHER = "other"


class AccountingBasis(str, Enum):
    """
    Accounting standard used.

    GAAP vs IFRS affects how many metrics are calculated.
    """

    GAAP = "gaap"
    IFRS = "ifrs"
    STATUTORY = "statutory"
    REGULATORY = "regulatory"
    OTHER = "other"


class Presentation(str, Enum):
    """
    How the metric is adjusted/presented.

    This is the key axis for comparing apples-to-apples:
    - REPORTED: As filed with regulators (GAAP/IFRS)
    - COMPANY_ADJUSTED: Company's "adjusted" or "non-GAAP" number
    - VENDOR_NORMALIZED: Vendor's adjustment (FactSet, Bloomberg)
    """

    REPORTED = "reported"
    COMPANY_ADJUSTED = "company_adjusted"
    VENDOR_NORMALIZED = "vendor_normalized"
    PRO_FORMA = "pro_forma"


class PerShareType(str, Enum):
    """
    Share count basis for per-share metrics.

    BASIC: Uses weighted average shares outstanding
    DILUTED: Includes potential dilution from options, convertibles
    """

    BASIC = "basic"
    DILUTED = "diluted"


class ScopeType(str, Enum):
    """
    Operations scope for the metric.

    TOTAL: All operations
    CONTINUING: Continuing operations only (excludes discontinued)
    DISCONTINUED: Discontinued operations only
    """

    TOTAL = "total"
    CONTINUING = "continuing"
    DISCONTINUED = "discontinued"


class PeriodType(str, Enum):
    """
    Type of fiscal period.

    Examples:
        ANNUAL = FY2025
        QUARTERLY = Q4 FY2025
        TTM = Trailing 12 months
    """

    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    TTM = "ttm"
    YTD = "ytd"
    LTM = "ltm"
    NTM = "ntm"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"


class ObservationType(str, Enum):
    """
    Type of observation.

    ACTUAL: Reported actual (from SEC filing)
    ESTIMATE: Analyst estimate (individual broker)
    CONSENSUS: Consensus estimate (aggregated)
    GUIDANCE: Company guidance
    PRELIMINARY: Preliminary/flash estimate
    """

    ACTUAL = "actual"
    ESTIMATE = "estimate"
    CONSENSUS = "consensus"
    GUIDANCE = "guidance"
    PRELIMINARY = "preliminary"
