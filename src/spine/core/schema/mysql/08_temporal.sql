-- =============================================================================
-- SPINE CORE - TEMPORAL / WATERMARK / BACKFILL TABLES (MySQL / MariaDB)
-- =============================================================================
-- Uses: DATETIME, JSON type, DOUBLE.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_watermarks (
    domain VARCHAR(255) NOT NULL,
    source VARCHAR(255) NOT NULL,
    partition_key VARCHAR(255) NOT NULL,
    high_water VARCHAR(255) NOT NULL,
    low_water VARCHAR(255),
    metadata_json JSON,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_watermarks (domain, source, partition_key),
    INDEX idx_core_watermarks_domain (domain),
    INDEX idx_core_watermarks_domain_source (domain, source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_backfill_plans (
    plan_id VARCHAR(255) PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    source VARCHAR(255) NOT NULL,
    partition_keys_json JSON NOT NULL,
    reason VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    range_start VARCHAR(255),
    range_end VARCHAR(255),
    completed_keys_json JSON DEFAULT (JSON_ARRAY()),
    failed_keys_json JSON DEFAULT (JSON_OBJECT()),
    checkpoint TEXT,
    metadata_json JSON DEFAULT (JSON_OBJECT()),
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    completed_at DATETIME,
    created_by VARCHAR(255) DEFAULT 'system',
    progress_pct DOUBLE DEFAULT 0.0,
    INDEX idx_core_backfill_plans_domain_source (domain, source),
    INDEX idx_core_backfill_plans_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_bitemporal_facts (
    record_id VARCHAR(255) PRIMARY KEY,
    entity_key VARCHAR(255) NOT NULL,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    system_from DATETIME NOT NULL,
    system_to DATETIME,
    payload_json JSON DEFAULT (JSON_OBJECT()),
    provenance VARCHAR(255) DEFAULT '',
    domain VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at DATETIME NOT NULL DEFAULT NOW(),
    INDEX idx_core_bitemporal_entity (entity_key),
    INDEX idx_core_bitemporal_valid (valid_from, valid_to),
    INDEX idx_core_bitemporal_system (system_from, system_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
