-- =============================================================================
-- REFERENCE DATA: EXCHANGE CALENDAR DOMAIN - INDEXES
-- =============================================================================
-- Owner: spine-domains/reference/exchange_calendar
-- Description: Performance indexes for exchange calendar tables
-- =============================================================================


CREATE INDEX IF NOT EXISTS idx_reference_exchange_calendar_holidays_year 
    ON reference_exchange_calendar_holidays(year, exchange_code);

CREATE INDEX IF NOT EXISTS idx_reference_exchange_calendar_trading_days_year
    ON reference_exchange_calendar_trading_days(year, exchange_code);
