"""
Shared domain enums for the spine ecosystem.

Enums in this module are used by multiple spines and should not
be owned by any single domain spine. Import from here to avoid
cross-spine coupling.

STDLIB ONLY - NO PYDANTIC.
"""

from enum import Enum


class VendorNamespace(str, Enum):
    """
    Vendor/source namespaces for identifier claims.

    Enables multi-vendor crosswalks (Bloomberg vs FactSet vs Reuters, etc.)
    Used by: data loaders, claims, vendor adapters,
    and any spine package that tracks data provenance.
    """

    # Regulatory sources
    SEC = "sec"
    GLEIF = "gleif"

    # Market data vendors
    BLOOMBERG = "bloomberg"
    FACTSET = "factset"
    REUTERS = "reuters"
    OPENFIGI = "openfigi"

    # Exchanges
    EXCHANGE = "exchange"

    # Internal
    USER = "user"
    INTERNAL = "internal"

    # Other
    OTHER = "other"


class EventType(str, Enum):
    """
    Type of discrete business event.

    Used in Event nodes for graph-native events.
    Maps loosely to SEC 8-K event categories and FactSet Events Calendar.
    """

    # Corporate Action Events
    MERGER_ACQUISITION = "m&a"
    DIVESTITURE = "divestiture"
    RESTRUCTURING = "restructuring"
    BANKRUPTCY = "bankruptcy"
    DELISTING = "delisting"
    SPINOFF = "spinoff"
    TENDER_OFFER = "tender_offer"

    # Calendar Events - Earnings
    EARNINGS_RELEASE = "earnings_release"
    EARNINGS_CALL = "earnings_call"
    EARNINGS_GUIDANCE = "earnings_guidance"
    EARNINGS_REVISION = "earnings_revision"

    # Calendar Events - Dividends
    DIVIDEND_DECLARED = "dividend_declared"
    DIVIDEND_EX_DATE = "dividend_ex_date"
    DIVIDEND_RECORD = "dividend_record"
    DIVIDEND_PAYMENT = "dividend_payment"
    SPECIAL_DIVIDEND = "special_dividend"

    # Calendar Events - Corporate
    ANNUAL_MEETING = "annual_meeting"
    ANALYST_DAY = "analyst_day"
    INVESTOR_CONFERENCE = "investor_conference"
    GUIDANCE_UPDATE = "guidance_update"

    # Stock Events
    STOCK_SPLIT = "stock_split"
    REVERSE_SPLIT = "reverse_split"
    SHARE_BUYBACK = "share_buyback"

    # Legal/Compliance Events
    LEGAL = "legal"
    REGULATORY = "regulatory"
    INVESTIGATION = "investigation"
    ENFORCEMENT = "enforcement"

    # Sanctions & Compliance
    SANCTION_DESIGNATION = "sanction_designation"
    SANCTION_REMOVAL = "sanction_removal"
    SANCTION_UPDATE = "sanction_update"
    COMPLIANCE_VIOLATION = "compliance_violation"
    AUDIT_FINDING = "audit_finding"

    # Risk Events
    CYBER = "cyber"
    DATA_BREACH = "data_breach"
    OPERATIONAL = "operational"
    ESG_INCIDENT = "esg_incident"
    SUPPLY_CHAIN = "supply_chain"

    # Financial Events
    FINANCIAL = "financial"
    CAPITAL = "capital"
    DIVIDEND = "dividend"
    RESTATEMENT = "restatement"
    CREDIT_RATING = "credit_rating"

    # Private Equity / Venture Events
    FUNDING_ROUND = "funding_round"
    IPO = "ipo"
    IPO_FILING = "ipo_filing"
    DIRECT_LISTING = "direct_listing"
    SPAC_MERGER = "spac_merger"
    PRIVATE_PLACEMENT = "private_placement"
    SECONDARY_OFFERING = "secondary_offering"
    LBO = "lbo"
    EXIT = "exit"

    # Management Events
    MANAGEMENT = "mgmt"
    CEO_CHANGE = "ceo_change"
    CFO_CHANGE = "cfo_change"
    BOARD = "board"
    EXECUTIVE_COMP = "executive_comp"

    # Product Events
    PRODUCT_LAUNCH = "product_launch"
    PRODUCT_RECALL = "product_recall"
    FDA_APPROVAL = "fda_approval"
    FDA_REJECTION = "fda_rejection"
    PATENT = "patent"

    # Other
    OTHER = "other"


class EventStatus(str, Enum):
    """Status of a business event."""

    ANNOUNCED = "announced"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PENDING = "pending"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    """
    Status of a resolution or processing run.

    Used in ResolutionRun to track batch execution state.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DataQualitySeverity(str, Enum):
    """
    Severity level for data quality rules and results.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CaseType(str, Enum):
    """Type of legal case/proceeding."""

    LAWSUIT = "lawsuit"
    INVESTIGATION = "investigation"
    ENFORCEMENT = "enforcement"
    ARBITRATION = "arbitration"
    BANKRUPTCY = "bankruptcy"
    ADMINISTRATIVE = "administrative"
    CRIMINAL = "criminal"
    OTHER = "other"


class CaseStatus(str, Enum):
    """Status of a legal case."""

    OPEN = "open"
    PENDING = "pending"
    CLOSED = "closed"
    SETTLED = "settled"
    DISMISSED = "dismissed"
    APPEALED = "appealed"
    UNKNOWN = "unknown"


class DecisionType(str, Enum):
    """
    Type of resolution decision for audit explanations.
    """

    MATCH = "match"
    REJECT = "reject"
    MERGE = "merge"
    SPLIT = "split"
    CREATE = "create"
    UPDATE = "update"
    MANUAL = "manual"


class ProvenanceKind(str, Enum):
    """
    Type of data provenance.

    Tracks how data was acquired/generated for audit trail purposes.
    Used by: provenance tracking, observations,
    document artifacts, and any spine tracking data lineage.
    """

    # Generic provenance
    FILE = "file"  # Ingested from filesystem
    API = "api"  # Fetched from API
    MANUAL = "manual"  # Human input
    DERIVED = "derived"  # Computed from other data
    LLM_GENERATED = "llm_generated"  # Generated by LLM

    # Financial data provenance
    SEC_FILING = "sec_filing"  # 10-K, 10-Q, 8-K, etc.
    VENDOR_SNAPSHOT = "vendor_snapshot"  # FactSet, Bloomberg data pull
    PRESS_RELEASE = "press_release"  # Company press release
    BROKER_NOTE = "broker_note"  # Analyst research note
    COMPANY_WEBSITE = "company_website"  # Company IR page
    EARNINGS_CALL = "earnings_call"  # Earnings call transcript
    INVESTOR_PRESENTATION = "investor_presentation"  # Investor deck
    OTHER = "other"
