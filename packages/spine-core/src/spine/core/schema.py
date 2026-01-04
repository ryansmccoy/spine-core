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
