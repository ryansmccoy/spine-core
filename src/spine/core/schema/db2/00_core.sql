-- =============================================================================
-- SPINE CORE - FRAMEWORK TABLES (IBM DB2)
-- =============================================================================
-- Uses: GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR.
-- DB2 does not support IF NOT EXISTS on CREATE TABLE; use exception handling
-- or check SYSCAT.TABLES before creating.
-- =============================================================================


CREATE TABLE _migrations (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    CONSTRAINT uq_migrations_filename UNIQUE (filename)
);


CREATE TABLE core_executions (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    workflow VARCHAR(255) NOT NULL,
    params CLOB DEFAULT '{}',
    lane VARCHAR(50) NOT NULL DEFAULT 'normal',
    trigger_source VARCHAR(100) NOT NULL DEFAULT 'api',
    logical_key VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    parent_execution_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result CLOB,
    error CLOB,
    retry_count INTEGER DEFAULT 0,
    idempotency_key VARCHAR(255),
    CONSTRAINT fk_exec_parent FOREIGN KEY (parent_execution_id) REFERENCES core_executions(id)
);

CREATE INDEX idx_core_executions_status ON core_executions(status);
CREATE INDEX idx_core_executions_workflow ON core_executions(workflow);
CREATE INDEX idx_core_executions_created_at ON core_executions(created_at);


CREATE TABLE core_manifest (
    domain VARCHAR(255) NOT NULL,
    partition_key VARCHAR(2000) NOT NULL,
    stage VARCHAR(255) NOT NULL,
    stage_rank INTEGER,
    row_count INTEGER,
    metrics_json CLOB,
    execution_id VARCHAR(255),
    batch_id VARCHAR(255),
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_core_manifest UNIQUE (domain, partition_key, stage)
);

CREATE INDEX idx_core_manifest_domain_part ON core_manifest(domain);
CREATE INDEX idx_core_manifest_domain_stage ON core_manifest(domain, stage);
CREATE INDEX idx_core_manifest_updated_at ON core_manifest(updated_at);


CREATE TABLE core_rejects (
    domain VARCHAR(255) NOT NULL,
    partition_key VARCHAR(2000) NOT NULL,
    stage VARCHAR(255) NOT NULL,
    reason_code VARCHAR(255) NOT NULL,
    reason_detail CLOB,
    raw_json CLOB,
    record_key VARCHAR(255),
    source_locator VARCHAR(500),
    line_number INTEGER,
    execution_id VARCHAR(255) NOT NULL,
    batch_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_core_rejects_domain ON core_rejects(domain);


CREATE TABLE core_quality (
    domain VARCHAR(255) NOT NULL,
    partition_key VARCHAR(2000) NOT NULL,
    check_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    message CLOB,
    actual_value CLOB,
    expected_value CLOB,
    details_json CLOB,
    execution_id VARCHAR(255) NOT NULL,
    batch_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_core_quality_domain ON core_quality(domain);


CREATE TABLE core_anomalies (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    workflow VARCHAR(255),
    partition_key VARCHAR(2000),
    stage VARCHAR(255),
    severity VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL,
    message CLOB NOT NULL,
    details_json CLOB,
    affected_records INTEGER,
    sample_records CLOB,
    execution_id VARCHAR(255),
    batch_id VARCHAR(255),
    capture_id VARCHAR(255),
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_note CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_core_anomalies_domain ON core_anomalies(domain);
CREATE INDEX idx_core_anomalies_severity ON core_anomalies(severity);
CREATE INDEX idx_core_anomalies_category ON core_anomalies(category);
CREATE INDEX idx_core_anomalies_detected ON core_anomalies(detected_at);


CREATE TABLE core_work_items (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    workflow VARCHAR(255) NOT NULL,
    partition_key VARCHAR(2000) NOT NULL,
    params_json CLOB,
    desired_at TIMESTAMP NOT NULL,
    priority INTEGER DEFAULT 100,
    state VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error CLOB,
    last_error_at TIMESTAMP,
    next_attempt_at TIMESTAMP,
    current_execution_id VARCHAR(255),
    latest_execution_id VARCHAR(255),
    locked_by VARCHAR(255),
    locked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    completed_at TIMESTAMP,
    CONSTRAINT uq_core_work_items UNIQUE (domain, workflow, partition_key)
);

CREATE INDEX idx_core_work_items_state ON core_work_items(state);
CREATE INDEX idx_core_work_items_desired ON core_work_items(desired_at);
CREATE INDEX idx_core_work_items_domain ON core_work_items(domain, workflow);


CREATE TABLE core_execution_events (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    data CLOB DEFAULT '{}',
    CONSTRAINT fk_exec_events FOREIGN KEY (execution_id) REFERENCES core_executions(id) ON DELETE CASCADE
);

CREATE INDEX idx_core_exec_events_eid ON core_execution_events(execution_id);
CREATE INDEX idx_core_exec_events_ts ON core_execution_events(timestamp);


CREATE TABLE core_dead_letters (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,
    workflow VARCHAR(255) NOT NULL,
    params CLOB DEFAULT '{}',
    error CLOB NOT NULL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP NOT NULL,
    last_retry_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(255)
);

CREATE INDEX idx_core_dl_resolved ON core_dead_letters(resolved_at);
CREATE INDEX idx_core_dl_workflow ON core_dead_letters(workflow);


CREATE TABLE core_concurrency_locks (
    lock_key VARCHAR(255) NOT NULL PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,
    acquired_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_core_conc_locks_exp ON core_concurrency_locks(expires_at);


CREATE TABLE core_schedules (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    target_type VARCHAR(50) NOT NULL DEFAULT 'operation',
    target_name VARCHAR(255) NOT NULL,
    params CLOB,
    schedule_type VARCHAR(50) NOT NULL DEFAULT 'cron',
    cron_expression VARCHAR(100),
    interval_seconds INTEGER,
    run_at VARCHAR(50),
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    enabled SMALLINT NOT NULL DEFAULT 1,
    max_instances INTEGER NOT NULL DEFAULT 1,
    misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    created_by VARCHAR(255),
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_schedules_name UNIQUE (name)
);

CREATE INDEX idx_schedules_enabled ON core_schedules(enabled);
CREATE INDEX idx_schedules_target ON core_schedules(target_type, target_name);


CREATE TABLE core_schedule_runs (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    schedule_id VARCHAR(255) NOT NULL,
    schedule_name VARCHAR(255) NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    run_id VARCHAR(255),
    execution_id VARCHAR(255),
    error CLOB,
    skip_reason CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_sched_runs_sid ON core_schedule_runs(schedule_id);
CREATE INDEX idx_sched_runs_status ON core_schedule_runs(status);
CREATE INDEX idx_sched_runs_sched_at ON core_schedule_runs(scheduled_at);


CREATE TABLE core_schedule_locks (
    schedule_id VARCHAR(255) NOT NULL PRIMARY KEY,
    locked_by VARCHAR(255) NOT NULL,
    locked_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_sched_locks_exp ON core_schedule_locks(expires_at);


-- =============================================================================
-- CALC DEPENDENCIES, EXPECTED SCHEDULES, DATA READINESS
-- =============================================================================

CREATE TABLE core_calc_dependencies (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calc_domain VARCHAR(255) NOT NULL,
    calc_operation VARCHAR(255) NOT NULL,
    calc_table VARCHAR(255),
    depends_on_domain VARCHAR(255) NOT NULL,
    depends_on_table VARCHAR(255) NOT NULL,
    dependency_type VARCHAR(50) NOT NULL,
    description CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_core_calc_deps_calc ON core_calc_dependencies(calc_domain, calc_operation);
CREATE INDEX idx_core_calc_deps_upstream ON core_calc_dependencies(depends_on_domain, depends_on_table);


CREATE TABLE core_expected_schedules (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    workflow VARCHAR(255) NOT NULL,
    schedule_type VARCHAR(50) NOT NULL,
    cron_expression VARCHAR(100),
    partition_template VARCHAR(2000) NOT NULL,
    partition_values CLOB,
    expected_delay_hours INTEGER,
    preliminary_hours INTEGER,
    description CLOB,
    is_active SMALLINT DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_core_exp_sched_domain ON core_expected_schedules(domain, workflow);
CREATE INDEX idx_core_exp_sched_active ON core_expected_schedules(is_active);


CREATE TABLE core_data_readiness (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    partition_key VARCHAR(2000) NOT NULL,
    is_ready SMALLINT DEFAULT 0,
    ready_for VARCHAR(100),
    all_partitions_present SMALLINT DEFAULT 0,
    all_stages_complete SMALLINT DEFAULT 0,
    no_critical_anomalies SMALLINT DEFAULT 0,
    dependencies_current SMALLINT DEFAULT 0,
    age_exceeds_preliminary SMALLINT DEFAULT 0,
    blocking_issues CLOB,
    certified_at TIMESTAMP,
    certified_by VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    CONSTRAINT uq_core_data_readiness UNIQUE (domain, partition_key, ready_for)
);

CREATE INDEX idx_core_data_readiness_domain ON core_data_readiness(domain);
CREATE INDEX idx_core_data_readiness_status ON core_data_readiness(is_ready);
