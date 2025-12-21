-- =============================================================================
-- SPINE CORE - FRAMEWORK TABLES (PostgreSQL)
-- =============================================================================
-- Auto-generated PostgreSQL-compatible schema.
-- Uses: SERIAL, TIMESTAMP, BOOLEAN, JSONB, partial indexes.
-- =============================================================================


-- =============================================================================
-- MIGRATIONS TRACKING
-- =============================================================================

CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- EXECUTION & MANIFEST
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_executions (
    id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    lane TEXT NOT NULL DEFAULT 'normal',
    trigger_source TEXT NOT NULL DEFAULT 'api',
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    parent_execution_id TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    idempotency_key TEXT,

    FOREIGN KEY (parent_execution_id) REFERENCES core_executions(id)
);

CREATE INDEX IF NOT EXISTS idx_core_executions_status ON core_executions(status);
CREATE INDEX IF NOT EXISTS idx_core_executions_workflow ON core_executions(workflow);
CREATE INDEX IF NOT EXISTS idx_core_executions_created_at ON core_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_core_executions_idempotency ON core_executions(idempotency_key) WHERE idempotency_key IS NOT NULL;


CREATE TABLE IF NOT EXISTS core_manifest (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    stage TEXT NOT NULL,
    stage_rank INTEGER,
    row_count INTEGER,
    metrics_json JSONB,
    execution_id TEXT,
    batch_id TEXT,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (domain, partition_key, stage)
);

CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_partition ON core_manifest(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_stage ON core_manifest(domain, stage);
CREATE INDEX IF NOT EXISTS idx_core_manifest_updated_at ON core_manifest(updated_at);


-- =============================================================================
-- QUALITY & REJECTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_rejects (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_detail TEXT,
    raw_json JSONB,
    record_key TEXT,
    source_locator TEXT,
    line_number INTEGER,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_rejects_domain_partition ON core_rejects(domain, partition_key);


CREATE TABLE IF NOT EXISTS core_quality (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    check_name TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    actual_value TEXT,
    expected_value TEXT,
    details_json JSONB,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_quality_domain_partition ON core_quality(domain, partition_key);


CREATE TABLE IF NOT EXISTS core_anomalies (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    workflow TEXT,
    partition_key TEXT,
    stage TEXT,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json JSONB,
    affected_records INTEGER,
    sample_records JSONB,
    execution_id TEXT,
    batch_id TEXT,
    capture_id TEXT,
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_core_anomalies_domain_partition ON core_anomalies(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_severity ON core_anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_category ON core_anomalies(category);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_detected_at ON core_anomalies(detected_at);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_unresolved ON core_anomalies(resolved_at) WHERE resolved_at IS NULL;


-- =============================================================================
-- WORK SCHEDULING & OPERATIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_work_items (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    workflow TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    params_json JSONB,
    desired_at TIMESTAMP NOT NULL,
    priority INTEGER DEFAULT 100,
    state TEXT NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    last_error_at TIMESTAMP,
    next_attempt_at TIMESTAMP,
    current_execution_id TEXT,
    latest_execution_id TEXT,
    locked_by TEXT,
    locked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    UNIQUE(domain, workflow, partition_key)
);

CREATE INDEX IF NOT EXISTS idx_core_work_items_state ON core_work_items(state);
CREATE INDEX IF NOT EXISTS idx_core_work_items_desired_at ON core_work_items(desired_at);
CREATE INDEX IF NOT EXISTS idx_core_work_items_next_attempt ON core_work_items(state, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_core_work_items_domain_workflow ON core_work_items(domain, workflow);
CREATE INDEX IF NOT EXISTS idx_core_work_items_partition ON core_work_items(domain, partition_key);


CREATE TABLE IF NOT EXISTS core_calc_dependencies (
    id SERIAL PRIMARY KEY,
    calc_domain TEXT NOT NULL,
    calc_operation TEXT NOT NULL,
    calc_table TEXT,
    depends_on_domain TEXT NOT NULL,
    depends_on_table TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_core_calc_dependencies_calc ON core_calc_dependencies(calc_domain, calc_operation);
CREATE INDEX IF NOT EXISTS idx_core_calc_dependencies_upstream ON core_calc_dependencies(depends_on_domain, depends_on_table);


CREATE TABLE IF NOT EXISTS core_expected_schedules (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    workflow TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    cron_expression TEXT,
    partition_template TEXT NOT NULL,
    partition_values TEXT,
    expected_delay_hours INTEGER,
    preliminary_hours INTEGER,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_core_expected_schedules_domain ON core_expected_schedules(domain, workflow);
CREATE INDEX IF NOT EXISTS idx_core_expected_schedules_active ON core_expected_schedules(is_active);


CREATE TABLE IF NOT EXISTS core_data_readiness (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    is_ready BOOLEAN DEFAULT FALSE,
    ready_for TEXT,
    all_partitions_present BOOLEAN DEFAULT FALSE,
    all_stages_complete BOOLEAN DEFAULT FALSE,
    no_critical_anomalies BOOLEAN DEFAULT FALSE,
    dependencies_current BOOLEAN DEFAULT FALSE,
    age_exceeds_preliminary BOOLEAN DEFAULT FALSE,
    blocking_issues JSONB,
    certified_at TIMESTAMP,
    certified_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(domain, partition_key, ready_for)
);

CREATE INDEX IF NOT EXISTS idx_core_data_readiness_domain ON core_data_readiness(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_data_readiness_status ON core_data_readiness(is_ready, ready_for);


-- =============================================================================
-- EXECUTION EVENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_execution_events (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES core_executions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    data JSONB DEFAULT '{}',
    CONSTRAINT fk_execution FOREIGN KEY (execution_id) REFERENCES core_executions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_core_execution_events_execution_id ON core_execution_events(execution_id);
CREATE INDEX IF NOT EXISTS idx_core_execution_events_timestamp ON core_execution_events(timestamp);


-- =============================================================================
-- DEAD LETTERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_dead_letters (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    workflow TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    error TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP NOT NULL,
    last_retry_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_core_dead_letters_resolved ON core_dead_letters(resolved_at);
CREATE INDEX IF NOT EXISTS idx_core_dead_letters_workflow ON core_dead_letters(workflow);


-- =============================================================================
-- CONCURRENCY LOCKS
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_concurrency_locks (
    lock_key TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    acquired_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_concurrency_locks_expires ON core_concurrency_locks(expires_at);
