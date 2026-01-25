-- =============================================================================
-- SPINE CORE - SOURCE TRACKING TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Tables for tracking data sources and fetch history.
--              Enables change detection, caching, and audit.
--
-- Tier Usage:
--   Basic: Optional (basic source tracking)
--   Intermediate: Required (full history)
--   Advanced/Full: Required (+ caching, change detection)
--
-- Design Principles Applied:
--   #3 Registry-Driven: Sources registered by type
--   #8 Idempotency: Content hash enables deduplication
--   #13 Observable: All fetches tracked
--
-- Dependencies: None
-- =============================================================================


-- =============================================================================
-- SOURCE REGISTRY (Source Definitions)
-- =============================================================================

-- Stores registered source configurations
-- Enables discovery and management of data sources
CREATE TABLE IF NOT EXISTS core_sources (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    name TEXT NOT NULL UNIQUE,              -- e.g., "finra.otc_transparency.weekly"
    
    -- Type
    source_type TEXT NOT NULL,              -- file, http, database, s3, sftp
    
    -- Configuration (type-specific)
    config_json TEXT NOT NULL,              -- JSON: Type-specific config
    -- file: {"path": "data/*.psv", "format": "psv"}
    -- http: {"url": "https://api.example.com", "auth": {...}}
    -- database: {"connection": "...", "query": "..."}
    
    -- Domain
    domain TEXT,                            -- e.g., "finra.otc_transparency"
    
    -- State
    enabled INTEGER NOT NULL DEFAULT 1,     -- 1=enabled, 0=disabled
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sources_type ON core_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON core_sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_enabled ON core_sources(enabled);


-- =============================================================================
-- SOURCE FETCHES (Fetch History)
-- =============================================================================

-- Tracks all source fetch operations
-- Enables debugging, audit, and change detection
CREATE TABLE IF NOT EXISTS core_source_fetches (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    source_id TEXT,                         -- FK to core_sources (NULL for ad-hoc)
    source_name TEXT NOT NULL,              -- Source identifier
    source_type TEXT NOT NULL,              -- file, http, database
    
    -- What was fetched
    source_locator TEXT NOT NULL,           -- Path, URL, or query
    
    -- Results
    status TEXT NOT NULL,                   -- SUCCESS, FAILED, NOT_FOUND, UNCHANGED
    record_count INTEGER,                   -- Number of records fetched
    byte_count INTEGER,                     -- Size in bytes
    
    -- Change detection
    content_hash TEXT,                      -- Hash of content (for deduplication)
    etag TEXT,                              -- HTTP ETag (for conditional fetching)
    last_modified TEXT,                     -- HTTP Last-Modified or file mtime
    
    -- Timing
    started_at TEXT NOT NULL,               -- When fetch started
    completed_at TEXT,                      -- When fetch completed
    duration_ms INTEGER,                    -- Fetch duration
    
    -- Error handling
    error TEXT,                             -- Error message if failed
    error_category TEXT,                    -- NETWORK, AUTH, NOT_FOUND, PARSE, etc.
    retry_count INTEGER NOT NULL DEFAULT 0, -- Number of retries
    
    -- Context
    execution_id TEXT,                      -- FK to execution (if applicable)
    run_id TEXT,                            -- FK to workflow run (if applicable)
    capture_id TEXT,                        -- Resulting capture ID
    
    -- Metadata
    metadata_json TEXT,                     -- JSON: Additional source metadata
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_source_fetches_source ON core_source_fetches(source_id);
CREATE INDEX IF NOT EXISTS idx_source_fetches_status ON core_source_fetches(status);
CREATE INDEX IF NOT EXISTS idx_source_fetches_hash ON core_source_fetches(content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_source_fetches_started ON core_source_fetches(started_at);
CREATE INDEX IF NOT EXISTS idx_source_fetches_execution ON core_source_fetches(execution_id) WHERE execution_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_source_fetches_run ON core_source_fetches(run_id) WHERE run_id IS NOT NULL;


-- =============================================================================
-- SOURCE CACHE (Optional - Advanced Tier)
-- =============================================================================

-- Caches source content for repeated access
-- Reduces network calls and enables offline mode
CREATE TABLE IF NOT EXISTS core_source_cache (
    -- Identity
    cache_key TEXT PRIMARY KEY,             -- Hash of source+params
    source_id TEXT,                         -- FK to core_sources
    source_type TEXT NOT NULL,
    source_locator TEXT NOT NULL,           -- Original path/URL
    
    -- Content
    content_hash TEXT NOT NULL,             -- Hash of cached content
    content_size INTEGER NOT NULL,          -- Size in bytes
    content_path TEXT,                      -- Local file path (if stored on disk)
    content_blob BLOB,                      -- Inline content (if small)
    
    -- Validity
    fetched_at TEXT NOT NULL,               -- When content was fetched
    expires_at TEXT,                        -- When cache expires
    etag TEXT,                              -- For conditional revalidation
    last_modified TEXT,                     -- For conditional revalidation
    
    -- Metadata
    metadata_json TEXT,                     -- JSON: Source metadata
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_accessed_at TEXT                   -- For LRU eviction
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_source_cache_source ON core_source_cache(source_id);
CREATE INDEX IF NOT EXISTS idx_source_cache_expires ON core_source_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_source_cache_accessed ON core_source_cache(last_accessed_at);


-- =============================================================================
-- DATABASE CONNECTIONS (Database Source Configuration)
-- =============================================================================

-- Stores database connection configurations
-- Used by DatabaseSource for cross-database queries
CREATE TABLE IF NOT EXISTS core_database_connections (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    name TEXT NOT NULL UNIQUE,              -- e.g., "prod-postgres", "legacy-db2"
    
    -- Connection
    dialect TEXT NOT NULL,                  -- sqlite, postgresql, db2
    host TEXT,                              -- Hostname (NULL for SQLite)
    port INTEGER,                           -- Port (NULL for SQLite)
    database TEXT NOT NULL,                 -- Database name or path
    
    -- Authentication (stored securely - consider external secret store)
    username TEXT,                          -- Database username
    password_ref TEXT,                      -- Reference to secret store (not plaintext!)
    
    -- Pool settings
    pool_size INTEGER NOT NULL DEFAULT 5,
    max_overflow INTEGER NOT NULL DEFAULT 10,
    pool_timeout INTEGER NOT NULL DEFAULT 30,
    
    -- State
    enabled INTEGER NOT NULL DEFAULT 1,     -- 1=enabled, 0=disabled
    
    -- Health
    last_connected_at TEXT,                 -- Last successful connection
    last_error TEXT,                        -- Last connection error
    last_error_at TEXT,                     -- When error occurred
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_db_connections_dialect ON core_database_connections(dialect);
CREATE INDEX IF NOT EXISTS idx_db_connections_enabled ON core_database_connections(enabled);
