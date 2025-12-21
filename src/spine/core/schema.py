"""
Core infrastructure tables shared across all domains.

Defines table names and DDL statements for the shared infrastructure
tables that support manifest tracking, rejects, quality checks,
anomalies, executions, and concurrency locks.

Manifesto:
    Financial data workflows share common infrastructure needs:
    - **Manifest:** Track workflow stage progression
    - **Rejects:** Store validation failures for audit
    - **Quality:** Record quality check results
    - **Anomalies:** Log errors and warnings
    - **Executions:** Workflow execution ledger

    Rather than each domain creating its own tables, we share
    infrastructure tables partitioned by domain name. This:
    - Reduces schema proliferation
    - Enables cross-domain queries (all rejects, all anomalies)
    - Simplifies maintenance and migrations

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                  Core Infrastructure Schema                  │
        └─────────────────────────────────────────────────────────────┘

        Table Registry (CORE_TABLES):
        ┌────────────────────────────────────────────────────────────┐
        │ manifest         → core_manifest                           │
        │ rejects          → core_rejects                            │
        │ quality          → core_quality                            │
        │ anomalies        → core_anomalies                          │
        │ executions       → core_executions                         │
        │ execution_events → core_execution_events                   │
        │ dead_letters     → core_dead_letters                       │
        │ concurrency_locks→ core_concurrency_locks                  │
        └────────────────────────────────────────────────────────────┘

        Partitioning:
        ┌────────────────────────────────────────────────────────────┐
        │ All tables have 'domain' column for partitioning:          │
        │                                                             │
        │ SELECT * FROM core_manifest WHERE domain = 'otc'           │
        │ SELECT * FROM core_rejects  WHERE domain = 'equity'        │
        │                                                             │
        │ Domains: otc, equity, options, finra.*, etc.               │
        └────────────────────────────────────────────────────────────┘

        Key-Value Pattern:
        ┌────────────────────────────────────────────────────────────┐
        │ partition_key is JSON for flexible logical keys:           │
        │                                                             │
        │ {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}        │
        │ {"date": "2025-12-26", "symbol": "AAPL"}                   │
        │                                                             │
        │ Enables arbitrary key combinations per domain.              │
        └────────────────────────────────────────────────────────────┘

Features:
    - **CORE_TABLES:** Dict mapping logical names to table names
    - **CORE_DDL:** Dict of CREATE TABLE statements
    - **Indexes:** Pre-defined for common query patterns
    - **create_tables():** Helper to create all tables

Examples:
    Get table name:

    >>> from spine.core.schema import CORE_TABLES
    >>> CORE_TABLES["manifest"]
    'core_manifest'

    Create all tables:

    >>> from spine.core.schema import create_tables
    >>> create_tables(conn)

Tables:
    - **core_manifest:** Multi-stage workflow tracking (UPSERT per stage)
    - **core_rejects:** Validation failures (append-only audit log)
    - **core_quality:** Quality check results (append-only)
    - **core_anomalies:** Error/warning tracking (append-only, resolvable)
    - **core_executions:** Workflow execution ledger
    - **core_execution_events:** Execution lifecycle events
    - **core_dead_letters:** Failed messages for retry
    - **core_concurrency_locks:** Distributed locking

Context:
    - Domain: Infrastructure, schema management
    - Used By: All Spine primitives (WorkManifest, RejectSink, etc.)
    - Storage: Shared across all domains
    - Paired With: Primitives that read/write these tables

Performance:
    - create_tables(): One-time DDL execution, O(n) where n = table count
    - Index creation: Included in DDL for common query patterns
    - Table lookups: CORE_TABLES dict access is O(1)

Guardrails:
    ❌ DON'T: Create domain-specific infrastructure tables (manifest, rejects, etc.)
    ✅ DO: Use shared core tables with domain column as partition key

    ❌ DON'T: Modify DDL without a migration (see spine.core.migrations)
    ✅ DO: Use the migrations framework for schema changes

    ❌ DON'T: Query across domains without explicit WHERE domain = X
    ✅ DO: Always filter by domain to prevent cross-contamination

Tags:
    schema, ddl, infrastructure, tables, spine-core, database,
    manifest, rejects, quality, anomalies

Doc-Types:
    - API Reference
    - Schema Documentation
    - Database Design

Note: Domains do NOT need their own manifest/rejects/quality tables.
"""

# =============================================================================
# TABLE NAMES
# =============================================================================

CORE_TABLES = {
    # --- 00_core.sql ---
    "migrations": "_migrations",
    "manifest": "core_manifest",
    "rejects": "core_rejects",
    "quality": "core_quality",
    "anomalies": "core_anomalies",
    "executions": "core_executions",
    "execution_events": "core_execution_events",
    "dead_letters": "core_dead_letters",
    "concurrency_locks": "core_concurrency_locks",
    "work_items": "core_work_items",
    "calc_dependencies": "core_calc_dependencies",
    "expected_schedules": "core_expected_schedules",
    "data_readiness": "core_data_readiness",
    # --- 02_workflow_history.sql ---
    "workflow_runs": "core_workflow_runs",
    "workflow_steps": "core_workflow_steps",
    "workflow_events": "core_workflow_events",
    # --- 03_scheduler.sql ---
    "schedules": "core_schedules",
    "schedule_runs": "core_schedule_runs",
    "schedule_locks": "core_schedule_locks",
    # --- 04_alerting.sql ---
    "alert_channels": "core_alert_channels",
    "alerts": "core_alerts",
    "alert_deliveries": "core_alert_deliveries",
    "alert_throttle": "core_alert_throttle",
    # --- 05_sources.sql ---
    "sources": "core_sources",
    "source_fetches": "core_source_fetches",
    "source_cache": "core_source_cache",
    "database_connections": "core_database_connections",
    # --- 08_temporal.sql ---
    "watermarks": "core_watermarks",
    "backfill_plans": "core_backfill_plans",
    "bitemporal_facts": "core_bitemporal_facts",
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Scope
            domain TEXT NOT NULL,
            workflow TEXT,
            partition_key TEXT,
            stage TEXT,

            -- Classification
            severity TEXT NOT NULL,
            category TEXT NOT NULL,

            -- Details
            message TEXT NOT NULL,
            details_json TEXT,

            -- Affected data
            affected_records INTEGER,
            sample_records TEXT,

            -- Context
            execution_id TEXT,
            batch_id TEXT,
            capture_id TEXT,

            -- Lifecycle
            detected_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution_note TEXT,

            created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    # CORE_EXECUTIONS: Workflow execution ledger
    #
    # Tracks all workflow executions with full lifecycle (pending → running
    # → completed/failed). Used by ExecutionLedger.
    # =========================================================================
    "executions": """
        CREATE TABLE IF NOT EXISTS core_executions (
            id TEXT PRIMARY KEY,
            workflow TEXT NOT NULL,
            params TEXT DEFAULT '{}',           -- JSON
            lane TEXT NOT NULL DEFAULT 'normal',
            trigger_source TEXT NOT NULL DEFAULT 'api',
            logical_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
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
    "executions_idx_workflow": """
        CREATE INDEX IF NOT EXISTS idx_core_executions_workflow
        ON core_executions(workflow)
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
            workflow TEXT NOT NULL,
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
    "dead_letters_idx_workflow": """
        CREATE INDEX IF NOT EXISTS idx_core_dead_letters_workflow
        ON core_dead_letters(workflow)
    """,
    # =========================================================================
    # CORE_CONCURRENCY_LOCKS: Prevent overlapping executions
    #
    # Database-level locking for workflow+params combinations.
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
    # =========================================================================
    # CORE_SCHEDULES: Recurring workflow execution schedules
    #
    # Tracks cron-based and interval-based schedule definitions.
    # Each schedule targets a workflow by name with optional parameters.
    # =========================================================================
    "schedules": """
        CREATE TABLE IF NOT EXISTS core_schedules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            target_type TEXT NOT NULL DEFAULT 'operation',
            target_name TEXT NOT NULL,
            params TEXT,
            schedule_type TEXT NOT NULL DEFAULT 'cron',
            cron_expression TEXT,
            interval_seconds INTEGER,
            run_at TEXT,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            enabled INTEGER NOT NULL DEFAULT 1,
            max_instances INTEGER NOT NULL DEFAULT 1,
            misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,
            last_run_at TEXT,
            next_run_at TEXT,
            last_run_status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT,
            version INTEGER NOT NULL DEFAULT 1
        )
    """,
    "schedules_idx_enabled": """
        CREATE INDEX IF NOT EXISTS idx_schedules_enabled
        ON core_schedules(enabled)
    """,
    "schedules_idx_next_run": """
        CREATE INDEX IF NOT EXISTS idx_schedules_next_run
        ON core_schedules(next_run_at) WHERE enabled = 1
    """,
    "schedules_idx_target": """
        CREATE INDEX IF NOT EXISTS idx_schedules_target
        ON core_schedules(target_type, target_name)
    """,
    "schedules_idx_name": """
        CREATE INDEX IF NOT EXISTS idx_schedules_name
        ON core_schedules(name)
    """,
}


def create_core_tables(conn) -> None:
    """
    Create all core infrastructure tables.

    Call this once at application startup or in migrations.
    Safe to call multiple times (CREATE IF NOT EXISTS).
    """
    for _name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
