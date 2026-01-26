"""
Schema definitions for Earnings domain.

Follows spine-core conventions:
- DOMAIN constant for manifest/rejects/quality tracking
- TABLES dict for database table names
- Enums for constrained values
"""

from enum import Enum
import json


# Domain identifier for core_manifest, core_rejects, core_quality
DOMAIN = "earnings"


class MetricCode(str, Enum):
    """Supported earnings metrics."""
    
    EPS = "eps"                    # Earnings per share
    REVENUE = "revenue"            # Total revenue
    EPS_ADJUSTED = "eps_adjusted"  # Non-GAAP EPS
    REVENUE_ADJUSTED = "revenue_adjusted"
    
    @classmethod
    def values(cls) -> list[str]:
        return [e.value for e in cls]


class ReportTime(str, Enum):
    """When earnings are reported relative to market hours."""
    
    BMO = "bmo"        # Before market open
    AMC = "amc"        # After market close
    DMH = "dmh"        # During market hours
    UNKNOWN = "unknown"
    
    @classmethod
    def values(cls) -> list[str]:
        return [e.value for e in cls]


class SurpriseDirection(str, Enum):
    """Direction of earnings surprise."""
    
    BEAT = "beat"
    MISS = "miss"
    INLINE = "inline"
    NO_ESTIMATE = "no_estimate"


class SurpriseMagnitude(str, Enum):
    """Magnitude of earnings surprise."""
    
    SMALL = "small"       # < 3%
    MODERATE = "moderate"  # 3-10%
    LARGE = "large"        # > 10%


class Stage(str, Enum):
    """Processing stages for earnings data."""
    
    RAW = "raw"                    # Raw calendar data from source
    ESTIMATES = "estimates"        # Consensus estimates
    ACTUALS = "actuals"            # Reported actuals
    SURPRISES = "surprises"        # Computed surprise metrics


# Table names following convention: {domain}_{entity}
TABLES = {
    "events": "earnings_events",           # Earnings calendar events
    "estimates": "earnings_estimates",     # Consensus estimates snapshots
    "actuals": "earnings_actuals",         # Reported actual values
    "surprises": "earnings_surprises",     # Computed surprise metrics
}


# DDL for earnings tables
DDL = {
    "events": """
        CREATE TABLE IF NOT EXISTS earnings_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            report_date DATE NOT NULL,
            report_time TEXT,
            fiscal_year INTEGER NOT NULL,
            fiscal_quarter INTEGER,
            fiscal_period TEXT NOT NULL,
            company_name TEXT,
            source_vendor TEXT NOT NULL,
            source_feed TEXT,
            natural_key TEXT NOT NULL UNIQUE,
            captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            batch_id TEXT,
            UNIQUE(ticker, fiscal_year, fiscal_period)
        )
    """,
    "estimates": """
        CREATE TABLE IF NOT EXISTS earnings_estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            fiscal_period TEXT NOT NULL,
            metric_code TEXT NOT NULL,
            estimate_value DECIMAL(20, 6),
            num_analysts INTEGER,
            captured_at TIMESTAMP NOT NULL,
            source_vendor TEXT NOT NULL,
            natural_key TEXT NOT NULL UNIQUE,
            batch_id TEXT
        )
    """,
    "actuals": """
        CREATE TABLE IF NOT EXISTS earnings_actuals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            fiscal_period TEXT NOT NULL,
            metric_code TEXT NOT NULL,
            actual_value DECIMAL(20, 6) NOT NULL,
            reported_at TIMESTAMP NOT NULL,
            source_vendor TEXT NOT NULL,
            natural_key TEXT NOT NULL UNIQUE,
            batch_id TEXT,
            UNIQUE(ticker, fiscal_period, metric_code)
        )
    """,
    "surprises": """
        CREATE TABLE IF NOT EXISTS earnings_surprises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            fiscal_period TEXT NOT NULL,
            metric_code TEXT NOT NULL,
            estimate_value DECIMAL(20, 6),
            actual_value DECIMAL(20, 6) NOT NULL,
            surprise_amount DECIMAL(20, 6),
            surprise_pct DECIMAL(10, 6),
            direction TEXT NOT NULL,
            magnitude TEXT,
            estimate_as_of TIMESTAMP,
            actual_reported_at TIMESTAMP NOT NULL,
            estimate_source TEXT,
            actual_source TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            natural_key TEXT NOT NULL UNIQUE,
            batch_id TEXT,
            UNIQUE(ticker, fiscal_period, metric_code)
        )
    """,
}


def create_earnings_tables(conn) -> None:
    """Create all earnings domain tables."""
    cursor = conn.cursor()
    for ddl in DDL.values():
        cursor.execute(ddl)
    conn.commit()


def partition_key(report_date: str, ticker: str | None = None) -> str:
    """
    Generate partition key for manifest tracking.
    
    Format: {"report_date": "2026-01-30"} or {"report_date": "2026-01-30", "ticker": "AAPL"}
    """
    data = {"report_date": report_date}
    if ticker:
        data["ticker"] = ticker
    return json.dumps(data, sort_keys=True)
