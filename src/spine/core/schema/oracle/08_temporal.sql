-- =============================================================================
-- SPINE CORE - TEMPORAL / WATERMARK / BACKFILL TABLES (Oracle)
-- =============================================================================
-- Uses: TIMESTAMP, CLOB, VARCHAR2, NUMBER.
-- Oracle does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_watermarks (
    domain VARCHAR2(255) NOT NULL,
    source VARCHAR2(255) NOT NULL,
    partition_key VARCHAR2(255) NOT NULL,
    high_water VARCHAR2(255) NOT NULL,
    low_water VARCHAR2(255),
    metadata_json CLOB,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_watermarks UNIQUE (domain, source, partition_key)
);

CREATE INDEX idx_core_watermarks_domain ON core_watermarks(domain);
CREATE INDEX idx_core_watermarks_domain_source ON core_watermarks(domain, source);


CREATE TABLE core_backfill_plans (
    plan_id VARCHAR2(255) PRIMARY KEY,
    domain VARCHAR2(255) NOT NULL,
    source VARCHAR2(255) NOT NULL,
    partition_keys_json CLOB NOT NULL,
    reason VARCHAR2(100) NOT NULL,
    status VARCHAR2(50) DEFAULT 'planned' NOT NULL,
    range_start VARCHAR2(255),
    range_end VARCHAR2(255),
    completed_keys_json CLOB DEFAULT '[]',
    failed_keys_json CLOB DEFAULT '{}',
    checkpoint CLOB,
    metadata_json CLOB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR2(255) DEFAULT 'system',
    progress_pct NUMBER DEFAULT 0.0
);

CREATE INDEX idx_core_backfill_plans_domain_source ON core_backfill_plans(domain, source);
CREATE INDEX idx_core_backfill_plans_status ON core_backfill_plans(status);


CREATE TABLE core_bitemporal_facts (
    record_id VARCHAR2(255) PRIMARY KEY,
    entity_key VARCHAR2(255) NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    system_from TIMESTAMP NOT NULL,
    system_to TIMESTAMP,
    payload_json CLOB DEFAULT '{}',
    provenance VARCHAR2(255) DEFAULT '',
    domain VARCHAR2(255) DEFAULT 'default' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_core_bitemporal_entity ON core_bitemporal_facts(entity_key);
CREATE INDEX idx_core_bitemporal_valid ON core_bitemporal_facts(valid_from, valid_to);
CREATE INDEX idx_core_bitemporal_system ON core_bitemporal_facts(system_from, system_to);
