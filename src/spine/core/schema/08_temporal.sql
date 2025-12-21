-- =============================================================================
-- SPINE CORE - TEMPORAL / WATERMARK / BACKFILL TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Infrastructure tables for temporal envelopes, watermark
--              tracking, backfill plans, and bi-temporal fact storage.
--
-- These tables support incremental operation resumption (watermarks),
-- gap-filling orchestration (backfill plans), and point-in-time-correct
-- bi-temporal storage (bitemporal facts).
-- =============================================================================


-- =============================================================================
-- WATERMARKS
-- =============================================================================
-- Track "how far have I read from this source?" for incremental operations.
-- Each (domain, source, partition_key) triple has a single high-water mark.

CREATE TABLE IF NOT EXISTS core_watermarks (
    domain          TEXT NOT NULL,
    source          TEXT NOT NULL,
    partition_key   TEXT NOT NULL,
    high_water      TEXT NOT NULL,
    low_water       TEXT,
    metadata_json   TEXT,               -- JSON: arbitrary extras
    updated_at      TEXT NOT NULL,

    UNIQUE (domain, source, partition_key)
);

CREATE INDEX IF NOT EXISTS idx_core_watermarks_domain
    ON core_watermarks(domain);

CREATE INDEX IF NOT EXISTS idx_core_watermarks_domain_source
    ON core_watermarks(domain, source);


-- =============================================================================
-- BACKFILL PLANS
-- =============================================================================
-- Track multi-partition gap-filling with checkpoint-based resume.

CREATE TABLE IF NOT EXISTS core_backfill_plans (
    plan_id             TEXT PRIMARY KEY,
    domain              TEXT NOT NULL,
    source              TEXT NOT NULL,
    partition_keys_json TEXT NOT NULL,       -- JSON array of partition keys
    reason              TEXT NOT NULL,       -- gap, correction, quality_failure, schema_change, manual
    status              TEXT NOT NULL DEFAULT 'planned',  -- planned, running, completed, failed, cancelled
    range_start         TEXT,
    range_end           TEXT,
    completed_keys_json TEXT DEFAULT '[]',   -- JSON array of done keys
    failed_keys_json    TEXT DEFAULT '{}',   -- JSON object: key → error
    checkpoint          TEXT,               -- opaque resume token
    metadata_json       TEXT DEFAULT '{}',  -- JSON: arbitrary extras
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    completed_at        TEXT,
    created_by          TEXT DEFAULT 'system',
    progress_pct        REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_core_backfill_plans_domain_source
    ON core_backfill_plans(domain, source);

CREATE INDEX IF NOT EXISTS idx_core_backfill_plans_status
    ON core_backfill_plans(status);


-- =============================================================================
-- BI-TEMPORAL FACTS
-- =============================================================================
-- Generic bi-temporal fact table for auditable, PIT-correct storage.
-- Two independent time axes:
--   valid_from / valid_to   → business reality (when was this fact true?)
--   system_from / system_to → bookkeeping (when did we record it?)

CREATE TABLE IF NOT EXISTS core_bitemporal_facts (
    record_id       TEXT PRIMARY KEY,
    entity_key      TEXT NOT NULL,
    valid_from      TEXT NOT NULL,
    valid_to        TEXT,               -- NULL = currently valid
    system_from     TEXT NOT NULL,
    system_to       TEXT,               -- NULL = latest system version
    payload_json    TEXT DEFAULT '{}',   -- JSON: the actual fact data
    provenance      TEXT DEFAULT '',

    domain          TEXT NOT NULL DEFAULT 'default',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_bitemporal_entity
    ON core_bitemporal_facts(entity_key);

CREATE INDEX IF NOT EXISTS idx_core_bitemporal_valid
    ON core_bitemporal_facts(valid_from, valid_to);

CREATE INDEX IF NOT EXISTS idx_core_bitemporal_system
    ON core_bitemporal_facts(system_from, system_to);
