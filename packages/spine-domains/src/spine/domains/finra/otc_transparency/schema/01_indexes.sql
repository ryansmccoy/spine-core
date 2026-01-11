-- =============================================================================
-- FINRA OTC TRANSPARENCY DOMAIN - INDEXES
-- =============================================================================
-- Owner: spine-domains/finra/otc_transparency
-- Description: Performance indexes for FINRA OTC Transparency tables
-- =============================================================================


-- =============================================================================
-- RAW & NORMALIZED INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_week ON finra_otc_transparency_raw(week_ending);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_symbol ON finra_otc_transparency_raw(symbol);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_capture ON finra_otc_transparency_raw(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_pit ON finra_otc_transparency_raw(week_ending, tier, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_week ON finra_otc_transparency_normalized(week_ending);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_symbol ON finra_otc_transparency_normalized(symbol);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_capture ON finra_otc_transparency_normalized(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_latest ON finra_otc_transparency_normalized(week_ending, tier, symbol, captured_at DESC);


-- =============================================================================
-- SILVER LAYER INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_volume_week ON finra_otc_transparency_venue_volume(week_ending);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_volume_symbol ON finra_otc_transparency_venue_volume(symbol);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_volume_capture ON finra_otc_transparency_venue_volume(week_ending, tier, capture_id);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_symbol_summary_capture ON finra_otc_transparency_symbol_summary(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_symbol_summary_pit ON finra_otc_transparency_symbol_summary(week_ending, tier, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_share_capture ON finra_otc_transparency_venue_share(week_ending, tier, capture_id);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_symbol_rolling_6w_capture ON finra_otc_transparency_symbol_rolling_6w(week_ending, tier, capture_id);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_liquidity_score_capture ON finra_otc_transparency_liquidity_score(week_ending, tier, capture_id);


-- =============================================================================
-- GOLD LAYER INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_volume_capture 
    ON finra_otc_transparency_weekly_symbol_venue_volume(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_volume_symbol 
    ON finra_otc_transparency_weekly_symbol_venue_volume(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_volume_latest 
    ON finra_otc_transparency_weekly_symbol_venue_volume(week_ending, tier, symbol, mpid, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_share_capture 
    ON finra_otc_transparency_weekly_symbol_venue_share(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_share_symbol 
    ON finra_otc_transparency_weekly_symbol_venue_share(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_share_latest 
    ON finra_otc_transparency_weekly_symbol_venue_share(week_ending, tier, symbol, mpid, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_concentration_hhi_capture 
    ON finra_otc_transparency_weekly_symbol_venue_concentration_hhi(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_concentration_hhi_symbol 
    ON finra_otc_transparency_weekly_symbol_venue_concentration_hhi(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_concentration_hhi_latest 
    ON finra_otc_transparency_weekly_symbol_venue_concentration_hhi(week_ending, tier, symbol, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_tier_volume_share_capture 
    ON finra_otc_transparency_weekly_symbol_tier_volume_share(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_tier_volume_share_symbol 
    ON finra_otc_transparency_weekly_symbol_tier_volume_share(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_tier_volume_share_latest 
    ON finra_otc_transparency_weekly_symbol_tier_volume_share(week_ending, tier, symbol, captured_at DESC);
