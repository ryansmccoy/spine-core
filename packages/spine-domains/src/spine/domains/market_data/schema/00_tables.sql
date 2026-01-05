-- =============================================================================
-- Market Data Domain: Price Tables
-- =============================================================================
-- Following spine patterns:
--   - capture_id for lineage
--   - captured_at for temporal ordering
--   - execution_id/batch_id for grouping
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Raw price data (as-fetched from source)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_data_prices_raw (
    -- Primary key fields
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,                    -- YYYY-MM-DD
    source TEXT NOT NULL DEFAULT 'alpha_vantage',
    
    -- OHLCV data
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    
    -- Capture lineage (REQUIRED per spine patterns)
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,             -- ISO timestamp
    execution_id TEXT,
    batch_id TEXT,
    
    PRIMARY KEY (symbol, date, source, capture_id)
);

CREATE INDEX IF NOT EXISTS idx_market_data_prices_raw_symbol_date 
    ON market_data_prices_raw(symbol, date DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_prices_raw_capture 
    ON market_data_prices_raw(capture_id);


-- -----------------------------------------------------------------------------
-- Normalized/validated price data (deduplicated, cleaned)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_data_prices_daily (
    -- Primary key fields
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,                    -- YYYY-MM-DD
    
    -- OHLCV data
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    
    -- Derived fields
    change REAL,                           -- close - previous close
    change_percent REAL,                   -- (change / previous close) * 100
    
    -- Source tracking
    source TEXT NOT NULL DEFAULT 'alpha_vantage',
    
    -- Capture lineage (REQUIRED per spine patterns)
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    execution_id TEXT,
    batch_id TEXT,
    
    -- Provenance (for rolled-up/aggregated data)
    input_capture_id TEXT,                 -- Which raw capture this came from
    
    -- Quality indicator
    is_valid INTEGER DEFAULT 1,            -- 0 if data has known issues
    
    PRIMARY KEY (symbol, date, capture_id)
);

CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_symbol_date 
    ON market_data_prices_daily(symbol, date DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_lookup 
    ON market_data_prices_daily(symbol, date);
