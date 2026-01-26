"""
Core infrastructure tables.

These tables are shared across all domains. Each domain writes to them
using its domain name as a partition key.

Tables:
- core_manifest: Multi-stage workflow tracking
- core_rejects: Validation failures
- core_quality: Quality check results

Domains do NOT need their own manifest/rejects/quality tables.
"""

# =============================================================================
# TABLE NAMES
# =============================================================================

CORE_TABLES = {
    "manifest": "core_manifest",
    "rejects": "core_rejects",
    "quality": "core_quality",
    "anomalies": "core_anomalies",
    "executions": "core_executions",
    "execution_events": "core_execution_events",
    "dead_letters": "core_dead_letters",
    "concurrency_locks": "core_concurrency_locks",
}


# =============================================================================
# DDL STATEMENTS
# =============================================================================

CORE_DDL = {
    # =========================================================================
    # CORE_MANIFEST: Current-state table (Option A)
    #
    # This is NOT an event log. Each (domain, partition_key, stage) triple
    # represents the current state of that stage for that partition.
    # Upsert semantics: advance_to() overwrites existing row for that stage.
    #
    # Future-proofing: If we need event sourcing (Option B), we'd add
    # core_manifest_events as a separate table, not change this one.
    # =========================================================================
    "manifest": """
        CREATE TABLE IF NOT EXISTS core_manifest (
            -- Domain partition
            domain TEXT NOT NULL,           -- e.g., "otc", "equity", "options"
            
            -- Logical key (JSON for flexibility)
            partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
            
            -- Stage info (one row per stage per partition)
            stage TEXT NOT NULL,
            stage_rank INTEGER,             -- Optional: explicit ordering (0-based)
            
            -- Metrics
            row_count INTEGER,
            metrics_json TEXT,              -- JSON for arbitrary metrics
            
            -- Lineage
            execution_id TEXT,
            batch_id TEXT,
            
            -- Timestamps
            updated_at TEXT NOT NULL,
            
            -- UNIQUE constraint for upsert
            UNIQUE (domain, partition_key, stage)
        )
    """,
    "rejects": """
        CREATE TABLE IF NOT EXISTS core_rejects (
            -- Domain partition
            domain TEXT NOT NULL,           -- e.g., "otc"
            
            -- Logical key (JSON for flexibility)
            partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
            
            -- Reject details
            stage TEXT NOT NULL,            -- INGEST, NORMALIZE, AGGREGATE
            reason_code TEXT NOT NULL,      -- INVALID_SYMBOL, NEGATIVE_VOLUME
            reason_detail TEXT,             -- Human-readable explanation
            
            -- Original data
            raw_json TEXT,                  -- JSON of raw record
            record_key TEXT,                -- Optional: specific record identifier
            
            -- Source tracking
            source_locator TEXT,            -- File path or URL
            line_number INTEGER,
            
            -- Lineage
            execution_id TEXT NOT NULL,
            batch_id TEXT,
            
            -- Timestamps
            created_at TEXT NOT NULL
        )
    """,
    "quality": """
        CREATE TABLE IF NOT EXISTS core_quality (
            -- Domain partition
            domain TEXT NOT NULL,           -- e.g., "otc"
            
            -- Logical key (JSON for flexibility)
            partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
            
            -- Check details
            check_name TEXT NOT NULL,       -- market_share_sum, min_symbols
            category TEXT NOT NULL,         -- INTEGRITY, COMPLETENESS, BUSINESS_RULE
            status TEXT NOT NULL,           -- PASS, WARN, FAIL
            message TEXT,                   -- Human-readable result
            
            -- Values
            actual_value TEXT,
            expected_value TEXT,
            details_json TEXT,              -- Additional structured data
            
            -- Lineage
            execution_id TEXT NOT NULL,
            batch_id TEXT,
            
            -- Timestamps
            created_at TEXT NOT NULL
        )
    """,
    # Indexes for common queries
    "manifest_idx_domain_partition": """
        CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_partition
        ON core_manifest(domain, partition_key)
    """,
    "manifest_idx_domain_stage": """
        CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_stage
        ON core_manifest(domain, stage)
    """,
    "manifest_idx_updated_at": """
        CREATE INDEX IF NOT EXISTS idx_core_manifest_updated_at
        ON core_manifest(updated_at)
    """,
    "rejects_idx": """
        CREATE INDEX IF NOT EXISTS idx_core_rejects_domain_partition
        ON core_rejects(domain, partition_key)
    """,
    "quality_idx": """
        CREATE INDEX IF NOT EXISTS idx_core_quality_domain_partition
        ON core_quality(domain, partition_key)
    """,
    # =========================================================================
    # CORE_ANOMALIES: Error and warning tracking
    #
    # Records issues that should be tracked for observability/audit.
    # Anomalies are NEVER deleted - they form an audit trail.
    # resolved_at NULL means still open.
    # =========================================================================
    "anomalies": """
        CREATE TABLE IF NOT EXISTS core_anomalies (
            -- Identity
            id TEXT PRIMARY KEY,
            
            -- Domain partition
            domain TEXT NOT NULL,           -- e.g., "finra.otc_transparency"
            
            -- Location
            stage TEXT NOT NULL,            -- Stage/step where anomaly occurred
            partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26"}
            
            -- Classification
            severity TEXT NOT NULL,         -- DEBUG, INFO, WARN, ERROR, CRITICAL
            category TEXT NOT NULL,         -- QUALITY_GATE, NETWORK, DATA_QUALITY, etc.
            
            -- Details
            message TEXT NOT NULL,          -- Human-readable description
            metadata_json TEXT,             -- JSON: Additional structured data
            
            -- Timestamps
            detected_at TEXT NOT NULL,
            resolved_at TEXT                -- NULL if still open
        )
    """,
    "anomalies_idx_domain_partition": """
        CREATE INDEX IF NOT EXISTS idx_core_anomalies_domain_partition
        ON core_anomalies(domain, partition_key)
    """,
    "anomalies_idx_severity": """
        CREATE INDEX IF NOT EXISTS idx_core_anomalies_severity
        ON core_anomalies(severity)
    """,
    "anomalies_idx_unresolved": """
        CREATE INDEX IF NOT EXISTS idx_core_anomalies_unresolved
        ON core_anomalies(resolved_at) WHERE resolved_at IS NULL
    """,
    # =========================================================================
    # CORE_EXECUTIONS: Pipeline execution ledger
    #
    # Tracks all pipeline executions with full lifecycle (pending → running
    # → completed/failed). Used by ExecutionLedger.
    # =========================================================================
    "executions": """
        CREATE TABLE IF NOT EXISTS core_executions (
            id TEXT PRIMARY KEY,
            pipeline TEXT NOT NULL,
            params TEXT DEFAULT '{}',           -- JSON
            status TEXT NOT NULL DEFAULT 'pending',
            lane TEXT NOT NULL DEFAULT 'default',
            trigger_source TEXT NOT NULL DEFAULT 'api',
            parent_execution_id TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,                        -- JSON
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            idempotency_key TEXT,
            
            FOREIGN KEY (parent_execution_id) REFERENCES core_executions(id)
        )
    """,
    "executions_idx_status": """
        CREATE INDEX IF NOT EXISTS idx_core_executions_status
        ON core_executions(status)
    """,
    "executions_idx_pipeline": """
        CREATE INDEX IF NOT EXISTS idx_core_executions_pipeline
        ON core_executions(pipeline)
    """,
    "executions_idx_created_at": """
        CREATE INDEX IF NOT EXISTS idx_core_executions_created_at
        ON core_executions(created_at)
    """,
    "executions_idx_idempotency": """
        CREATE INDEX IF NOT EXISTS idx_core_executions_idempotency
        ON core_executions(idempotency_key) WHERE idempotency_key IS NOT NULL
    """,
    # =========================================================================
    # CORE_EXECUTION_EVENTS: Event sourcing for executions
    #
    # Immutable, append-only event log for execution lifecycle.
    # Enables debugging, observability, and replay.
    # =========================================================================
    "execution_events": """
        CREATE TABLE IF NOT EXISTS core_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            data TEXT DEFAULT '{}',             -- JSON
            
            FOREIGN KEY (execution_id) REFERENCES core_executions(id) ON DELETE CASCADE
        )
    """,
    "execution_events_idx_execution_id": """
        CREATE INDEX IF NOT EXISTS idx_core_execution_events_execution_id
        ON core_execution_events(execution_id)
    """,
    "execution_events_idx_timestamp": """
        CREATE INDEX IF NOT EXISTS idx_core_execution_events_timestamp
        ON core_execution_events(timestamp)
    """,
    # =========================================================================
    # CORE_DEAD_LETTERS: Failed execution queue
    #
    # Captures failed executions for manual inspection and retry.
    # Persists until explicitly resolved.
    # =========================================================================
    "dead_letters": """
        CREATE TABLE IF NOT EXISTS core_dead_letters (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            pipeline TEXT NOT NULL,
            params TEXT DEFAULT '{}',           -- JSON
            error TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            created_at TEXT NOT NULL,
            last_retry_at TEXT,
            resolved_at TEXT,
            resolved_by TEXT
        )
    """,
    "dead_letters_idx_resolved": """
        CREATE INDEX IF NOT EXISTS idx_core_dead_letters_resolved
        ON core_dead_letters(resolved_at)
    """,
    "dead_letters_idx_pipeline": """
        CREATE INDEX IF NOT EXISTS idx_core_dead_letters_pipeline
        ON core_dead_letters(pipeline)
    """,
    # =========================================================================
    # CORE_CONCURRENCY_LOCKS: Prevent overlapping executions
    #
    # Database-level locking for pipeline+params combinations.
    # Locks expire automatically after timeout.
    # =========================================================================
    "concurrency_locks": """
        CREATE TABLE IF NOT EXISTS core_concurrency_locks (
            lock_key TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """,
    "concurrency_locks_idx_expires": """
        CREATE INDEX IF NOT EXISTS idx_core_concurrency_locks_expires
        ON core_concurrency_locks(expires_at)
    """,
}


def create_core_tables(conn) -> None:
    """
    Create all core infrastructure tables.

    Call this once at application startup or in migrations.
    Safe to call multiple times (CREATE IF NOT EXISTS).
    """
    for name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
