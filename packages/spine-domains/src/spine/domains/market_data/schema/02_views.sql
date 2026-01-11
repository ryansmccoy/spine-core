-- =============================================================================
-- Market Data Domain: Price Views
-- =============================================================================
-- Views follow the spine pattern:
--   - _latest: Most recent capture per partition (ROW_NUMBER pattern)
--   - _clean: Excludes rows with unresolved errors
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Latest daily prices (one row per symbol/date, most recent capture)
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS market_data_prices_daily_latest AS
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY symbol, date 
               ORDER BY captured_at DESC
           ) as rn
    FROM market_data_prices_daily
    WHERE is_valid = 1
) WHERE rn = 1;


-- -----------------------------------------------------------------------------
-- Clean daily prices (excludes partitions with unresolved errors)
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS market_data_prices_daily_clean AS
SELECT p.* FROM market_data_prices_daily_latest p
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.domain = 'market_data'
      AND a.stage = 'INGEST'
      AND a.partition_key LIKE p.symbol || '|%'
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
);


-- -----------------------------------------------------------------------------
-- Latest prices per symbol (most recent available date)
-- Useful for "current price" queries
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS market_data_prices_current AS
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY symbol 
               ORDER BY date DESC, captured_at DESC
           ) as rn
    FROM market_data_prices_daily
    WHERE is_valid = 1
) WHERE rn = 1;


-- -----------------------------------------------------------------------------
-- Price history for charting (last N days per symbol)
-- Use with: WHERE symbol = ? ORDER BY date DESC LIMIT N
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS market_data_prices_chart AS
SELECT 
    symbol,
    date,
    open,
    high,
    low,
    close,
    volume,
    change,
    change_percent,
    source,
    captured_at
FROM market_data_prices_daily_latest
ORDER BY symbol, date DESC;
