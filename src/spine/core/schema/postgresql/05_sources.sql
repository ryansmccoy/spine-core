-- =============================================================================
-- SPINE CORE - SOURCE TRACKING TABLES (PostgreSQL)
-- =============================================================================
-- Uses: SERIAL, TIMESTAMP, BOOLEAN, JSONB, BYTEA, partial indexes.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    config_json JSONB NOT NULL,
    domain TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_type ON core_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON core_sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_enabled ON core_sources(enabled);


CREATE TABLE IF NOT EXISTS core_source_fetches (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    status TEXT NOT NULL,
    record_count INTEGER,
    byte_count INTEGER,
    content_hash TEXT,
    etag TEXT,
    last_modified TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    error TEXT,
    error_category TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    execution_id TEXT,
    run_id TEXT,
    capture_id TEXT,
    metadata_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_fetches_source ON core_source_fetches(source_id);
CREATE INDEX IF NOT EXISTS idx_source_fetches_status ON core_source_fetches(status);
CREATE INDEX IF NOT EXISTS idx_source_fetches_hash ON core_source_fetches(content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_source_fetches_started ON core_source_fetches(started_at);
CREATE INDEX IF NOT EXISTS idx_source_fetches_execution ON core_source_fetches(execution_id) WHERE execution_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_source_fetches_run ON core_source_fetches(run_id) WHERE run_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS core_source_cache (
    cache_key TEXT PRIMARY KEY,
    source_id TEXT,
    source_type TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_size INTEGER NOT NULL,
    content_path TEXT,
    content_blob BYTEA,
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    etag TEXT,
    last_modified TEXT,
    metadata_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_accessed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_source_cache_source ON core_source_cache(source_id);
CREATE INDEX IF NOT EXISTS idx_source_cache_expires ON core_source_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_source_cache_accessed ON core_source_cache(last_accessed_at);


CREATE TABLE IF NOT EXISTS core_database_connections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    dialect TEXT NOT NULL,
    host TEXT,
    port INTEGER,
    database TEXT NOT NULL,
    username TEXT,
    password_ref TEXT,
    pool_size INTEGER NOT NULL DEFAULT 5,
    max_overflow INTEGER NOT NULL DEFAULT 10,
    pool_timeout INTEGER NOT NULL DEFAULT 30,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_connected_at TIMESTAMP,
    last_error TEXT,
    last_error_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_db_connections_dialect ON core_database_connections(dialect);
CREATE INDEX IF NOT EXISTS idx_db_connections_enabled ON core_database_connections(enabled);
