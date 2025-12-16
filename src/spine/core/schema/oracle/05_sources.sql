-- =============================================================================
-- SPINE CORE - SOURCE TRACKING TABLES (Oracle)
-- =============================================================================
-- Uses: NUMBER GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR2, NUMBER(1), BLOB.
-- Oracle does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_sources (
    id VARCHAR2(255) PRIMARY KEY,
    name VARCHAR2(255) NOT NULL UNIQUE,
    source_type VARCHAR2(100) NOT NULL,
    config_json CLOB NOT NULL,
    domain VARCHAR2(255),
    enabled NUMBER(1) DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    created_by VARCHAR2(255)
);

CREATE INDEX idx_sources_type ON core_sources(source_type);
CREATE INDEX idx_sources_domain ON core_sources(domain);
CREATE INDEX idx_sources_enabled ON core_sources(enabled);


CREATE TABLE core_source_fetches (
    id VARCHAR2(255) PRIMARY KEY,
    source_id VARCHAR2(255),
    source_name VARCHAR2(255) NOT NULL,
    source_type VARCHAR2(100) NOT NULL,
    source_locator CLOB NOT NULL,
    status VARCHAR2(50) NOT NULL,
    record_count NUMBER,
    byte_count NUMBER,
    content_hash VARCHAR2(255),
    etag VARCHAR2(255),
    last_modified VARCHAR2(255),
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms NUMBER,
    error CLOB,
    error_category VARCHAR2(100),
    retry_count NUMBER DEFAULT 0 NOT NULL,
    execution_id VARCHAR2(255),
    run_id VARCHAR2(255),
    capture_id VARCHAR2(255),
    metadata_json CLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_source_fetches_source ON core_source_fetches(source_id);
CREATE INDEX idx_source_fetches_status ON core_source_fetches(status);
CREATE INDEX idx_source_fetches_hash ON core_source_fetches(content_hash);
CREATE INDEX idx_source_fetches_started ON core_source_fetches(started_at);
CREATE INDEX idx_source_fetches_execution ON core_source_fetches(execution_id);
CREATE INDEX idx_source_fetches_run ON core_source_fetches(run_id);


CREATE TABLE core_source_cache (
    cache_key VARCHAR2(255) PRIMARY KEY,
    source_id VARCHAR2(255),
    source_type VARCHAR2(100) NOT NULL,
    source_locator CLOB NOT NULL,
    content_hash VARCHAR2(255) NOT NULL,
    content_size NUMBER NOT NULL,
    content_path CLOB,
    content_blob BLOB,
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    etag VARCHAR2(255),
    last_modified VARCHAR2(255),
    metadata_json CLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP
);

CREATE INDEX idx_source_cache_source ON core_source_cache(source_id);
CREATE INDEX idx_source_cache_expires ON core_source_cache(expires_at);
CREATE INDEX idx_source_cache_accessed ON core_source_cache(last_accessed_at);


CREATE TABLE core_database_connections (
    id VARCHAR2(255) PRIMARY KEY,
    name VARCHAR2(255) NOT NULL UNIQUE,
    dialect VARCHAR2(100) NOT NULL,
    host VARCHAR2(255),
    port NUMBER,
    database_name VARCHAR2(255) NOT NULL,
    username VARCHAR2(255),
    password_ref VARCHAR2(255),
    pool_size NUMBER DEFAULT 5 NOT NULL,
    max_overflow NUMBER DEFAULT 10 NOT NULL,
    pool_timeout NUMBER DEFAULT 30 NOT NULL,
    enabled NUMBER(1) DEFAULT 1 NOT NULL,
    last_connected_at TIMESTAMP,
    last_error CLOB,
    last_error_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    created_by VARCHAR2(255)
);

CREATE INDEX idx_db_connections_dialect ON core_database_connections(dialect);
CREATE INDEX idx_db_connections_enabled ON core_database_connections(enabled);
