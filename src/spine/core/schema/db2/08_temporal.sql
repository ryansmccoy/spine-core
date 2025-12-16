-- =============================================================================
-- SPINE CORE - TEMPORAL / WATERMARK / BACKFILL TABLES (IBM DB2)
-- =============================================================================
-- Uses: TIMESTAMP, CLOB, VARCHAR, DOUBLE.
-- DB2 does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_watermarks (
    domain VARCHAR(255) NOT NULL,
    source VARCHAR(255) NOT NULL,
    partition_key VARCHAR(255) NOT NULL,
    high_water VARCHAR(255) NOT NULL,
    low_water VARCHAR(255),
    metadata_json CLOB,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_watermarks UNIQUE (domain, source, partition_key)
);

CREATE INDEX idx_core_watermarks_domain ON core_watermarks(domain);
CREATE INDEX idx_core_watermarks_domain_source ON core_watermarks(domain, source);


CREATE TABLE core_backfill_plans (
    plan_id VARCHAR(255) NOT NULL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    source VARCHAR(255) NOT NULL,
    partition_keys_json CLOB NOT NULL,
    reason VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    range_start VARCHAR(255),
    range_end VARCHAR(255),
    completed_keys_json CLOB DEFAULT '[]',
    failed_keys_json CLOB DEFAULT '{}',
    checkpoint CLOB,
    metadata_json CLOB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',
    progress_pct DOUBLE DEFAULT 0.0
);

CREATE INDEX idx_core_backfill_plans_domain_source ON core_backfill_plans(domain, source);
CREATE INDEX idx_core_backfill_plans_status ON core_backfill_plans(status);


CREATE TABLE core_bitemporal_facts (
    record_id VARCHAR(255) NOT NULL PRIMARY KEY,
    entity_key VARCHAR(255) NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    system_from TIMESTAMP NOT NULL,
    system_to TIMESTAMP,
    payload_json CLOB DEFAULT '{}',
    provenance VARCHAR(255) DEFAULT '',
    domain VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_core_bitemporal_entity ON core_bitemporal_facts(entity_key);
CREATE INDEX idx_core_bitemporal_valid ON core_bitemporal_facts(valid_from, valid_to);
CREATE INDEX idx_core_bitemporal_system ON core_bitemporal_facts(system_from, system_to);
