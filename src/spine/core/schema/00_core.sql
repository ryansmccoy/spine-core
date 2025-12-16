-- =============================================================================
-- SPINE CORE - FRAMEWORK TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Core framework tables for execution tracking, manifest, quality,
--              work scheduling, anomalies, and operational metadata.
--
-- This module must NOT contain domain-specific tables (finra_*, reference_*, etc.)
-- =============================================================================


-- =============================================================================
-- MIGRATIONS TRACKING
-- =============================================================================

CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);


-- =============================================================================
-- EXECUTION & MANIFEST
-- =============================================================================

-- Core executions (placeholder for Intermediate tier)
-- NOTE: NOT USED in Basic tier. Basic keeps executions in memory.
CREATE TABLE IF NOT EXISTS core_executions (
    id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    params TEXT DEFAULT '{}',      -- JSON
    lane TEXT NOT NULL DEFAULT 'normal',
    trigger_source TEXT NOT NULL DEFAULT 'api',
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    parent_execution_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    result TEXT,                    -- JSON
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    idempotency_key TEXT,

    FOREIGN KEY (parent_execution_id) REFERENCES core_executions(id)
);

CREATE INDEX IF NOT EXISTS idx_core_executions_status ON core_executions(status);
CREATE INDEX IF NOT EXISTS idx_core_executions_workflow ON core_executions(workflow);
CREATE INDEX IF NOT EXISTS idx_core_executions_created_at ON core_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_core_executions_idempotency ON core_executions(idempotency_key) WHERE idempotency_key IS NOT NULL;


-- Core manifest (tracks pipeline execution state per domain/partition/stage)
CREATE TABLE IF NOT EXISTS core_manifest (
    domain TEXT NOT NULL,           -- e.g., "finra.otc_transparency"
    partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "OTC"}
    stage TEXT NOT NULL,
    stage_rank INTEGER,
    row_count INTEGER,
    metrics_json TEXT,
    execution_id TEXT,
    batch_id TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (domain, partition_key, stage)
);

CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_partition ON core_manifest(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_stage ON core_manifest(domain, stage);
CREATE INDEX IF NOT EXISTS idx_core_manifest_updated_at ON core_manifest(updated_at);


-- =============================================================================
-- QUALITY & REJECTS
-- =============================================================================

-- Core rejects (tracks rejected records during pipeline processing)
CREATE TABLE IF NOT EXISTS core_rejects (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_detail TEXT,
    raw_json TEXT,
    record_key TEXT,
    source_locator TEXT,
    line_number INTEGER,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_rejects_domain_partition ON core_rejects(domain, partition_key);


-- Core quality (tracks quality check results)
CREATE TABLE IF NOT EXISTS core_quality (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    check_name TEXT NOT NULL,
    category TEXT NOT NULL,         -- INTEGRITY, COMPLETENESS, BUSINESS_RULE
    status TEXT NOT NULL,           -- PASS, WARN, FAIL
    message TEXT,
    actual_value TEXT,
    expected_value TEXT,
    details_json TEXT,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_quality_domain_partition ON core_quality(domain, partition_key);


-- Core anomalies (tracks data quality issues, business rule violations, and operational warnings)
-- Lightweight persistence for failures and warnings without blocking workflow execution
CREATE TABLE IF NOT EXISTS core_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Scope
    domain TEXT NOT NULL,
    workflow TEXT,                  -- Workflow that detected anomaly (NULL for system-level)
    partition_key TEXT,             -- Affected partition (JSON)
    stage TEXT,                     -- Workflow stage where detected
    
    -- Classification
    severity TEXT NOT NULL,         -- INFO, WARN, ERROR, CRITICAL
    category TEXT NOT NULL,         -- INCOMPLETE_INPUT, BUSINESS_RULE, COMPLETENESS, CONSISTENCY, FRESHNESS, DEPENDENCY
    
    -- Details
    message TEXT NOT NULL,          -- Human-readable description
    details_json TEXT,              -- Additional context (expected vs actual, sample records, etc.)
    
    -- Affected data
    affected_records INTEGER,       -- Count of records impacted
    sample_records TEXT,            -- JSON: Sample of affected records for investigation
    
    -- Context
    execution_id TEXT,              -- Execution that detected this anomaly
    batch_id TEXT,
    capture_id TEXT,                -- Capture this anomaly applies to (if applicable)
    
    -- Lifecycle
    detected_at TEXT NOT NULL,
    resolved_at TEXT,               -- When anomaly was addressed (NULL if unresolved)
    resolution_note TEXT,           -- How it was resolved
    
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_anomalies_domain_partition ON core_anomalies(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_severity ON core_anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_category ON core_anomalies(category);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_detected_at ON core_anomalies(detected_at);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_unresolved ON core_anomalies(resolved_at) WHERE resolved_at IS NULL;


-- =============================================================================
-- WORK SCHEDULING & OPERATIONS
-- =============================================================================

-- Core work items (tracks scheduled/expected pipeline runs for operational automation)
-- Used by cron jobs, Kubernetes CronJobs, and schedulers to manage work queues
CREATE TABLE IF NOT EXISTS core_work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Work definition
    domain TEXT NOT NULL,           -- e.g., "finra.otc_transparency"
    pipeline TEXT NOT NULL,         -- e.g., "ingest_week", "normalize_week"
    partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "OTC"}
    params_json TEXT,               -- Additional pipeline parameters (JSON)
    
    -- Scheduling
    desired_at TEXT NOT NULL,       -- When this work should be done (ISO 8601)
    priority INTEGER DEFAULT 100,   -- Higher = more urgent (for queuing)
    
    -- State machine: PENDING → RUNNING → COMPLETE (or FAILED → RETRY_WAIT → PENDING)
    state TEXT NOT NULL DEFAULT 'PENDING',
    -- States: PENDING, RUNNING, COMPLETE, FAILED, RETRY_WAIT, CANCELLED
    
    -- Retry and failure handling
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,                -- Error message from most recent attempt
    last_error_at TEXT,             -- When error occurred
    next_attempt_at TEXT,           -- For exponential backoff (NULL if not retrying)
    
    -- Execution tracking
    current_execution_id TEXT,      -- execution_id of RUNNING attempt
    latest_execution_id TEXT,       -- execution_id of last COMPLETE attempt
    locked_by TEXT,                 -- Worker ID that claimed this work (optional)
    locked_at TEXT,                 -- When work was claimed
    
    -- Audit trail
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,              -- When state became COMPLETE
    
    UNIQUE(domain, pipeline, partition_key)
);

CREATE INDEX IF NOT EXISTS idx_core_work_items_state ON core_work_items(state);
CREATE INDEX IF NOT EXISTS idx_core_work_items_desired_at ON core_work_items(desired_at);
CREATE INDEX IF NOT EXISTS idx_core_work_items_next_attempt ON core_work_items(state, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_core_work_items_domain_pipeline ON core_work_items(domain, pipeline);
CREATE INDEX IF NOT EXISTS idx_core_work_items_partition ON core_work_items(domain, partition_key);


-- Core calculation dependencies (tracks lineage between calculations and their data sources)
-- Enables automatic invalidation when upstream data is revised
CREATE TABLE IF NOT EXISTS core_calc_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Downstream calculation
    calc_domain TEXT NOT NULL,
    calc_pipeline TEXT NOT NULL,
    calc_table TEXT,                -- Specific table (if applicable)
    
    -- Upstream dependency
    depends_on_domain TEXT NOT NULL,
    depends_on_table TEXT NOT NULL,
    
    -- Dependency metadata
    dependency_type TEXT NOT NULL,  -- REQUIRED, OPTIONAL, REFERENCE
    description TEXT,               -- Why this dependency exists
    
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_calc_dependencies_calc ON core_calc_dependencies(calc_domain, calc_pipeline);
CREATE INDEX IF NOT EXISTS idx_core_calc_dependencies_upstream ON core_calc_dependencies(depends_on_domain, depends_on_table);


-- Core expected schedules (declarative specification of pipeline execution cadence)
-- Used for detecting missed runs, late data, and validating completeness
CREATE TABLE IF NOT EXISTS core_expected_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Pipeline identification
    domain TEXT NOT NULL,
    pipeline TEXT NOT NULL,
    
    -- Schedule specification
    schedule_type TEXT NOT NULL,    -- WEEKLY, DAILY, MONTHLY, ANNUAL, TRIGGERED
    cron_expression TEXT,           -- Optional: Cron format for complex schedules
    
    -- Partition template
    partition_template TEXT NOT NULL, -- JSON: {"week_ending": "${MONDAY}", "tier": "${TIER}"}
    partition_values TEXT,          -- JSON: Expected values for template variables
    
    -- SLA and expectations
    expected_delay_hours INTEGER,   -- How long after business date should data arrive
    preliminary_hours INTEGER,      -- Hours before data is considered stable/final
    
    -- Metadata
    description TEXT,
    is_active INTEGER DEFAULT 1,    -- 0 to temporarily disable schedule
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_expected_schedules_domain ON core_expected_schedules(domain, pipeline);
CREATE INDEX IF NOT EXISTS idx_core_expected_schedules_active ON core_expected_schedules(is_active);


-- Core data readiness (tracks certification status for data products)
-- Indicates when data is "ready for trading" or "ready for compliance reporting"
CREATE TABLE IF NOT EXISTS core_data_readiness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Data product identification
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"}
    
    -- Readiness status
    is_ready INTEGER DEFAULT 0,     -- 1 when all criteria satisfied
    ready_for TEXT,                 -- USE_CASE: "trading", "compliance", "research"
    
    -- Certification criteria results
    all_partitions_present INTEGER DEFAULT 0,
    all_stages_complete INTEGER DEFAULT 0,
    no_critical_anomalies INTEGER DEFAULT 0,
    dependencies_current INTEGER DEFAULT 0,
    age_exceeds_preliminary INTEGER DEFAULT 0,
    
    -- Details
    blocking_issues TEXT,           -- JSON: List of issues preventing readiness
    certified_at TEXT,              -- When readiness criteria were met
    certified_by TEXT,              -- System or user who certified
    
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(domain, partition_key, ready_for)
);

CREATE INDEX IF NOT EXISTS idx_core_data_readiness_domain ON core_data_readiness(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_data_readiness_status ON core_data_readiness(is_ready, ready_for);


-- =============================================================================
-- EXECUTION EVENTS (Event Sourcing)
-- =============================================================================

-- Immutable, append-only event log for execution lifecycle.
-- Enables debugging, observability, and replay.
CREATE TABLE IF NOT EXISTS core_execution_events (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    event_type TEXT NOT NULL,               -- created, started, completed, failed, retried
    timestamp TEXT NOT NULL,
    data TEXT DEFAULT '{}',                 -- JSON payload

    FOREIGN KEY (execution_id) REFERENCES core_executions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_core_execution_events_execution_id
    ON core_execution_events(execution_id);
CREATE INDEX IF NOT EXISTS idx_core_execution_events_timestamp
    ON core_execution_events(timestamp);


-- =============================================================================
-- DEAD LETTERS (Failed Execution Queue)
-- =============================================================================

-- Captures failed executions for manual inspection and retry.
-- Persists until explicitly resolved.
CREATE TABLE IF NOT EXISTS core_dead_letters (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    workflow TEXT NOT NULL,
    params TEXT DEFAULT '{}',               -- JSON
    error TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TEXT NOT NULL,
    last_retry_at TEXT,
    resolved_at TEXT,
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_core_dead_letters_resolved
    ON core_dead_letters(resolved_at);
CREATE INDEX IF NOT EXISTS idx_core_dead_letters_workflow
    ON core_dead_letters(workflow);


-- =============================================================================
-- CONCURRENCY LOCKS (Prevent Overlapping Executions)
-- =============================================================================

-- Database-level locking for workflow+params combinations.
-- Locks expire automatically after timeout.
CREATE TABLE IF NOT EXISTS core_concurrency_locks (
    lock_key TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_concurrency_locks_expires
    ON core_concurrency_locks(expires_at);
