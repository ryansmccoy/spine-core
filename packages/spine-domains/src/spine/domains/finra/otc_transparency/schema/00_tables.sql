-- =============================================================================
-- FINRA OTC TRANSPARENCY DOMAIN - TABLES
-- =============================================================================
-- Owner: spine-domains/finra/otc_transparency
-- Description: FINRA OTC Transparency weekly trading data
--
-- 3-CLOCK TEMPORAL MODEL:
--   Clock 1: week_ending (business time - when trading occurred)
--   Clock 2: source_last_update_date (FINRA system time - when FINRA updated)
--   Clock 3: captured_at + capture_id (platform time - when we ingested)
--
-- UNIQUE constraints include capture_id to allow multiple captures of same week.
-- This enables point-in-time queries and correction tracking.
-- =============================================================================


-- =============================================================================
-- RAW & NORMALIZED LAYERS
-- =============================================================================

-- Raw data from FINRA files (source of truth for all 3 clocks)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    
    -- Clock 1: Business time
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_name TEXT,
    venue_name TEXT,
    mpid TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    
    -- Clock 2: Source system time (from FINRA lastUpdateDate)
    source_last_update_date TEXT,
    
    -- Clock 3: Platform capture time
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    source_file TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- Normalized table (cleaned, standardized data from raw)
-- This is the "source of truth" for downstream calculations
CREATE TABLE IF NOT EXISTS finra_otc_transparency_normalized (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    -- Business keys
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    
    -- Metrics
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    
    -- Additional attributes
    issue_name TEXT,
    venue_name TEXT,
    source_last_update_date TEXT,
    
    -- Capture identity (Clock 3)
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    -- Lineage
    source_raw_id INTEGER,
    normalized_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- =============================================================================
-- SILVER LAYER - AGGREGATIONS & SUMMARIES
-- =============================================================================

-- Normalized venue volumes (propagates capture identity from raw)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_venue_volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    avg_trade_size TEXT,
    record_hash TEXT NOT NULL,
    
    -- Clock 3: Propagated from raw
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    normalized_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- Symbol weekly summaries (propagates capture identity)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_symbol_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    
    -- Clock 3: Propagated from normalized
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- Venue market share (propagates capture identity)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_venue_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,
    market_share_pct TEXT NOT NULL,
    rank INTEGER NOT NULL,
    
    -- Clock 3: Propagated from normalized
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, mpid, capture_id)
);


-- Rolling 6-week symbol statistics
CREATE TABLE IF NOT EXISTS finra_otc_transparency_symbol_rolling_6w (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    avg_volume TEXT NOT NULL,
    avg_trades TEXT NOT NULL,
    min_volume INTEGER NOT NULL,
    max_volume INTEGER NOT NULL,
    trend_direction TEXT,
    trend_pct TEXT,
    weeks_in_window INTEGER NOT NULL,
    is_complete INTEGER NOT NULL,
    
    -- Clock 3: From current week's capture
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- Liquidity scores
CREATE TABLE IF NOT EXISTS finra_otc_transparency_liquidity_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,

    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    liquidity_score TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT NOT NULL,

    -- Clock 3: Propagated from summary
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,

    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- Research snapshot (wide denormalized table for analysts)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_research_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    
    -- Current week stats
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    
    -- Rolling stats
    rolling_avg_volume TEXT,
    rolling_avg_trades TEXT,
    rolling_min_volume INTEGER,
    rolling_max_volume INTEGER,
    trend_direction TEXT,
    trend_pct TEXT,
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- =============================================================================
-- GOLD LAYER - REAL TRADING ANALYTICS CALCULATIONS
-- =============================================================================
-- These tables support institutional-grade trading analytics:
-- - Venue-level volume tracking
-- - Venue market share analysis
-- - Market concentration metrics (HHI)
-- - Tier split analytics

-- Base venue volume (gold layer foundation)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    venue_name TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_venue_volume',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- Venue market share
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    venue_name TEXT NOT NULL,
    venue_volume INTEGER NOT NULL,
    total_symbol_volume INTEGER NOT NULL,
    venue_share REAL NOT NULL,  -- 0.0 to 1.0
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_venue_share',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id),
    CHECK(venue_share >= 0.0 AND venue_share <= 1.0)
);


-- Venue concentration (HHI)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_concentration_hhi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    hhi REAL NOT NULL,  -- 0.0 to 1.0
    venue_count INTEGER NOT NULL,
    total_symbol_volume INTEGER NOT NULL,
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_venue_concentration_hhi',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id),
    CHECK(hhi >= 0.0 AND hhi <= 1.0),
    CHECK(venue_count > 0)
);


-- Tier volume share
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_tier_volume_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    tier_volume INTEGER NOT NULL,
    total_symbol_volume_all_tiers INTEGER NOT NULL,
    tier_volume_share REAL NOT NULL,  -- 0.0 to 1.0
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_tier_volume_share',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id),
    CHECK(tier_volume_share >= 0.0 AND tier_volume_share <= 1.0)
);
