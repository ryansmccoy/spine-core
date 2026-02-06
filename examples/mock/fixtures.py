"""Mock data fixtures for spine-core examples.

This module provides sample data that mimics real SEC EDGAR and
feed data for offline example execution.
"""
from __future__ import annotations

from datetime import datetime, timezone

# =============================================================================
# Company Data (matches SEC company_tickers.json format)
# =============================================================================

MOCK_COMPANIES = {
    "0000320193": {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "ticker": "AAPL",
        "exchange": "NASDAQ",
        "sic": "3571",
        "sic_description": "Electronic Computers",
        "state": "CA",
        "lei": "HWUPKR0MPOU8FGXBT394",
    },
    "0000789019": {
        "cik": "0000789019",
        "name": "Microsoft Corporation",
        "ticker": "MSFT",
        "exchange": "NASDAQ",
        "sic": "7372",
        "sic_description": "Prepackaged Software",
        "state": "WA",
        "lei": "INR2EJN1ERAN0W5ZP974",
    },
    "0001318605": {
        "cik": "0001318605",
        "name": "Tesla, Inc.",
        "ticker": "TSLA",
        "exchange": "NASDAQ",
        "sic": "3711",
        "sic_description": "Motor Vehicles & Passenger Car Bodies",
        "state": "TX",
    },
    "0001045810": {
        "cik": "0001045810",
        "name": "NVIDIA Corporation",
        "ticker": "NVDA",
        "exchange": "NASDAQ",
        "sic": "3674",
        "sic_description": "Semiconductors and Related Devices",
        "state": "DE",
    },
    "0001652044": {
        "cik": "0001652044",
        "name": "Alphabet Inc.",
        "ticker": "GOOGL",
        "exchange": "NASDAQ",
        "sic": "7370",
        "sic_description": "Computer Programming Services",
        "state": "DE",
    },
}

# =============================================================================
# SEC Filing Data
# =============================================================================

MOCK_FILINGS = {
    "0000320193": [
        {
            "accession": "0000320193-24-000081",
            "form": "10-K",
            "filed": "2024-11-01",
            "period": "2024-09-28",
            "primaryDocument": "aapl-20240928.htm",
        },
        {
            "accession": "0000320193-24-000069",
            "form": "10-Q",
            "filed": "2024-08-01",
            "period": "2024-06-29",
            "primaryDocument": "aapl-20240629.htm",
        },
        {
            "accession": "0000320193-24-000057",
            "form": "10-Q",
            "filed": "2024-05-02",
            "period": "2024-03-30",
            "primaryDocument": "aapl-20240330.htm",
        },
    ],
    "0000789019": [
        {
            "accession": "0000789019-24-000066",
            "form": "10-K",
            "filed": "2024-07-30",
            "period": "2024-06-30",
            "primaryDocument": "msft-20240630.htm",
        },
        {
            "accession": "0000789019-24-000053",
            "form": "10-Q",
            "filed": "2024-04-25",
            "period": "2024-03-31",
            "primaryDocument": "msft-20240331.htm",
        },
    ],
    "0001318605": [
        {
            "accession": "0001318605-24-000064",
            "form": "10-Q",
            "filed": "2024-10-23",
            "period": "2024-09-30",
            "primaryDocument": "tsla-20240930.htm",
        },
    ],
}

# =============================================================================
# Feed Record Data (RSS-style articles)
# =============================================================================

MOCK_FEED_RECORDS = {
    "sec_filings": [
        {
            "id": "sec-001",
            "title": "Apple Inc. Files Form 10-K Annual Report",
            "cik": "0000320193",
            "form_type": "10-K",
            "filed_date": "2024-11-01",
            "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193",
        },
        {
            "id": "sec-002",
            "title": "Microsoft Corporation Files Form 10-Q",
            "cik": "0000789019",
            "form_type": "10-Q",
            "filed_date": "2024-04-25",
            "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000789019",
        },
        {
            "id": "sec-003",
            "title": "Tesla, Inc. Files Form 8-K",
            "cik": "0001318605",
            "form_type": "8-K",
            "filed_date": "2024-10-15",
            "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605",
        },
    ],
    "market_data": [
        {
            "id": "mkt-001",
            "symbol": "AAPL",
            "price": 185.50,
            "volume": 45_000_000,
            "change_pct": 1.25,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": "mkt-002",
            "symbol": "MSFT",
            "price": 415.75,
            "volume": 22_000_000,
            "change_pct": 0.85,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": "mkt-003",
            "symbol": "NVDA",
            "price": 875.25,
            "volume": 35_000_000,
            "change_pct": 2.15,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    ],
    "news": [
        {
            "id": "news-001",
            "title": "Tech Stocks Rally on AI Optimism",
            "source": "financial-times",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "tickers": ["AAPL", "MSFT", "NVDA"],
        },
        {
            "id": "news-002",
            "title": "Federal Reserve Signals Rate Pause",
            "source": "reuters",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "tickers": [],
        },
    ],
}

# =============================================================================
# Identifier Claims
# =============================================================================

MOCK_IDENTIFIER_CLAIMS = {
    "0000320193": {
        "CIK": "0000320193",
        "LEI": "HWUPKR0MPOU8FGXBT394",
        "EIN": "94-2404110",
        "TICKER": "AAPL",
        "CUSIP": "037833100",
        "ISIN": "US0378331005",
    },
    "0000789019": {
        "CIK": "0000789019",
        "LEI": "INR2EJN1ERAN0W5ZP974",
        "TICKER": "MSFT",
        "CUSIP": "594918104",
        "ISIN": "US5949181045",
    },
}

# =============================================================================
# Executive Data
# =============================================================================

MOCK_EXECUTIVES = {
    "0000320193": [
        {"name": "Tim Cook", "title": "Chief Executive Officer", "since": "2011-08-24"},
        {"name": "Luca Maestri", "title": "Chief Financial Officer", "since": "2014-05-01"},
        {"name": "Jeff Williams", "title": "Chief Operating Officer", "since": "2015-12-01"},
    ],
    "0001045810": [
        {"name": "Jensen Huang", "title": "President and CEO", "since": "1993-01-01"},
        {"name": "Colette Kress", "title": "EVP and CFO", "since": "2013-09-01"},
    ],
}
