"""
Exchange Calendar Domain — Holiday and trading day reference data.

This domain manages:
- Exchange holiday calendars (XNYS, XNAS, etc.)
- Trading day calculations
- Business day utilities

Ingestion cadence: Annual (updated once per year)
Source type: Static JSON reference data
"""

from spine.domains.reference.exchange_calendar.calculations import (
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    trading_days_between,
)
from spine.domains.reference.exchange_calendar.schema import (
    DOMAIN,
    Exchange,
    TABLES,
)

__all__ = [
    "DOMAIN",
    "Exchange",
    "TABLES",
    "is_trading_day",
    "next_trading_day",
    "previous_trading_day",
    "trading_days_between",
]
