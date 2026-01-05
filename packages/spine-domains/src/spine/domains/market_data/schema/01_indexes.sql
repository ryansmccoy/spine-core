-- =============================================================================
-- Market Data Domain: Additional Indexes
-- =============================================================================
-- Indexes for efficient queries including:
--   - Symbol + date range filters
--   - Latest queries (captured_at ordering)
--   - As-of queries (capture_id lookups)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Indexes for as-of queries (point-in-time by capture_id)
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_capture_id
    ON market_data_prices_daily(capture_id);

CREATE INDEX IF NOT EXISTS idx_market_data_prices_raw_capture_id
    ON market_data_prices_raw(capture_id);

-- -----------------------------------------------------------------------------
-- Indexes for latest queries (most recent by captured_at)
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_captured_at
    ON market_data_prices_daily(captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_symbol_captured
    ON market_data_prices_daily(symbol, captured_at DESC);

-- -----------------------------------------------------------------------------
-- Indexes for date range queries
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_date_range
    ON market_data_prices_daily(symbol, date DESC, captured_at DESC);

-- -----------------------------------------------------------------------------
-- Indexes for source-specific queries
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_source
    ON market_data_prices_daily(source, symbol);

-- -----------------------------------------------------------------------------
-- Covering index for common query pattern (symbol + date + latest)
-- Includes is_valid for filtering
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_query_cover
    ON market_data_prices_daily(symbol, date DESC, is_valid)
    WHERE is_valid = 1;
