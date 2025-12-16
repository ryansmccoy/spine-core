-- =============================================================================
-- SPINE CORE - TEMPORAL / WATERMARK / BACKFILL TABLES (PostgreSQL)
-- =============================================================================
-- Uses: TIMESTAMP, JSONB, DOUBLE PRECISION.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_watermarks (
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    high_water TEXT NOT NULL,
    low_water TEXT,
    metadata_json JSONB,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (domain, source, partition_key)
);

CREATE INDEX IF NOT EXISTS idx_core_watermarks_domain ON core_watermarks(domain);
CREATE INDEX IF NOT EXISTS idx_core_watermarks_domain_source ON core_watermarks(domain, source);


CREATE TABLE IF NOT EXISTS core_backfill_plans (
    plan_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    partition_keys_json JSONB NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    range_start TEXT,
    range_end TEXT,
    completed_keys_json JSONB DEFAULT '[]',
    failed_keys_json JSONB DEFAULT '{}',
    checkpoint TEXT,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by TEXT DEFAULT 'system',
    progress_pct DOUBLE PRECISION DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_core_backfill_plans_domain_source ON core_backfill_plans(domain, source);
CREATE INDEX IF NOT EXISTS idx_core_backfill_plans_status ON core_backfill_plans(status);


CREATE TABLE IF NOT EXISTS core_bitemporal_facts (
    record_id TEXT PRIMARY KEY,
    entity_key TEXT NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    system_from TIMESTAMP NOT NULL,
    system_to TIMESTAMP,
    payload_json JSONB DEFAULT '{}',
    provenance TEXT DEFAULT '',
    domain TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_core_bitemporal_entity ON core_bitemporal_facts(entity_key);
CREATE INDEX IF NOT EXISTS idx_core_bitemporal_valid ON core_bitemporal_facts(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_core_bitemporal_system ON core_bitemporal_facts(system_from, system_to);
