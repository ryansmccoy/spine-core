-- migrations/020_otc_tables.sql (PostgreSQL)

CREATE SCHEMA IF NOT EXISTS otc;

-- Raw data from FINRA files
CREATE TABLE IF NOT EXISTS otc.raw (
    id BIGSERIAL PRIMARY KEY,
    batch_id TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_name TEXT,
    venue_name TEXT,
    mpid TEXT NOT NULL,
    share_volume BIGINT NOT NULL,
    trade_count INTEGER NOT NULL,
    
    source_file TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_otc_raw_week ON otc.raw(week_ending);
CREATE INDEX IF NOT EXISTS idx_otc_raw_symbol ON otc.raw(symbol);


-- Normalized venue volumes
CREATE TABLE IF NOT EXISTS otc.venue_volume (
    id BIGSERIAL PRIMARY KEY,
    
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    share_volume BIGINT NOT NULL,
    trade_count INTEGER NOT NULL,
    avg_trade_size NUMERIC(18, 4),
    record_hash TEXT NOT NULL,
    
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(week_ending, tier, symbol, mpid)
);

CREATE INDEX IF NOT EXISTS idx_venue_week ON otc.venue_volume(week_ending);
CREATE INDEX IF NOT EXISTS idx_venue_symbol ON otc.venue_volume(symbol);


-- Symbol weekly summaries
CREATE TABLE IF NOT EXISTS otc.symbol_summary (
    id BIGSERIAL PRIMARY KEY,
    
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume BIGINT NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size NUMERIC(18, 4),
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(week_ending, tier, symbol)
);


-- Venue market share
CREATE TABLE IF NOT EXISTS otc.venue_share (
    id BIGSERIAL PRIMARY KEY,
    
    week_ending DATE NOT NULL,
    mpid TEXT NOT NULL,
    total_volume BIGINT NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,
    market_share_pct NUMERIC(5, 2) NOT NULL,
    rank INTEGER NOT NULL,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(week_ending, mpid)
);
