-- =============================================================================
-- SPINE CORE - SOURCE TRACKING TABLES (IBM DB2)
-- =============================================================================
-- Uses: GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR, SMALLINT, BLOB.
-- DB2 does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_sources (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    config_json CLOB NOT NULL,
    domain VARCHAR(255),
    enabled SMALLINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    created_by VARCHAR(255),
    CONSTRAINT uq_sources_name UNIQUE (name)
);

CREATE INDEX idx_sources_type ON core_sources(source_type);
CREATE INDEX idx_sources_domain ON core_sources(domain);
CREATE INDEX idx_sources_enabled ON core_sources(enabled);


CREATE TABLE core_source_fetches (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    source_id VARCHAR(255),
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_locator CLOB NOT NULL,
    status VARCHAR(50) NOT NULL,
    record_count INTEGER,
    byte_count INTEGER,
    content_hash VARCHAR(255),
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    error CLOB,
    error_category VARCHAR(100),
    retry_count INTEGER NOT NULL DEFAULT 0,
    execution_id VARCHAR(255),
    run_id VARCHAR(255),
    capture_id VARCHAR(255),
    metadata_json CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_source_fetches_source ON core_source_fetches(source_id);
CREATE INDEX idx_source_fetches_status ON core_source_fetches(status);
CREATE INDEX idx_source_fetches_hash ON core_source_fetches(content_hash);
CREATE INDEX idx_source_fetches_started ON core_source_fetches(started_at);
CREATE INDEX idx_source_fetches_execution ON core_source_fetches(execution_id);
CREATE INDEX idx_source_fetches_run ON core_source_fetches(run_id);


CREATE TABLE core_source_cache (
    cache_key VARCHAR(255) NOT NULL PRIMARY KEY,
    source_id VARCHAR(255),
    source_type VARCHAR(100) NOT NULL,
    source_locator CLOB NOT NULL,
    content_hash VARCHAR(255) NOT NULL,
    content_size INTEGER NOT NULL,
    content_path CLOB,
    content_blob BLOB,
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    metadata_json CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    last_accessed_at TIMESTAMP
);

CREATE INDEX idx_source_cache_source ON core_source_cache(source_id);
CREATE INDEX idx_source_cache_expires ON core_source_cache(expires_at);
CREATE INDEX idx_source_cache_accessed ON core_source_cache(last_accessed_at);


CREATE TABLE core_database_connections (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    dialect VARCHAR(100) NOT NULL,
    host VARCHAR(255),
    port INTEGER,
    database_name VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    password_ref VARCHAR(255),
    pool_size INTEGER NOT NULL DEFAULT 5,
    max_overflow INTEGER NOT NULL DEFAULT 10,
    pool_timeout INTEGER NOT NULL DEFAULT 30,
    enabled SMALLINT NOT NULL DEFAULT 1,
    last_connected_at TIMESTAMP,
    last_error CLOB,
    last_error_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    created_by VARCHAR(255),
    CONSTRAINT uq_db_connections_name UNIQUE (name)
);

CREATE INDEX idx_db_connections_dialect ON core_database_connections(dialect);
CREATE INDEX idx_db_connections_enabled ON core_database_connections(enabled);
