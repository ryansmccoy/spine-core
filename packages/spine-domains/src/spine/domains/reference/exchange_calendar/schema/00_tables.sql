-- =============================================================================
-- REFERENCE DATA: EXCHANGE CALENDAR DOMAIN - TABLES
-- =============================================================================
-- Owner: spine-domains/reference/exchange_calendar
-- Description: Exchange holiday calendars and computed trading day data
--
-- Ingestion cadence: Annual (updated once per year)
-- Partition key: {"year": 2025, "exchange_code": "XNYS"}
-- =============================================================================


-- Holiday calendar data (raw from JSON files)
CREATE TABLE IF NOT EXISTS reference_exchange_calendar_holidays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    exchange_code TEXT NOT NULL,
    holiday_date TEXT NOT NULL,
    holiday_name TEXT NOT NULL,
    
    -- Capture metadata
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(year, exchange_code, holiday_date)
);


-- Computed trading days by month
CREATE TABLE IF NOT EXISTS reference_exchange_calendar_trading_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    exchange_code TEXT NOT NULL,
    month INTEGER NOT NULL,
    trading_days INTEGER NOT NULL,
    calendar_days INTEGER NOT NULL,
    holidays INTEGER NOT NULL,
    
    -- Calc metadata
    calc_name TEXT NOT NULL,
    calc_version TEXT NOT NULL,
    
    -- Capture metadata
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(year, exchange_code, month)
);
