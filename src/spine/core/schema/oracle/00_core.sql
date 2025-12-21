-- =============================================================================
-- SPINE CORE - FRAMEWORK TABLES (Oracle)
-- =============================================================================
-- Uses: NUMBER GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR2.
-- Oracle uses SYSTIMESTAMP for current timestamp, NUMBER(1) for booleans.
-- Oracle does not support IF NOT EXISTS; use exception blocks in PL/SQL
-- or check USER_TABLES before creating.
-- =============================================================================


-- =============================================================================
-- MIGRATIONS TRACKING
-- =============================================================================

CREATE TABLE _migrations (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename VARCHAR2(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);


-- =============================================================================
-- EXECUTION & MANIFEST
-- =============================================================================

CREATE TABLE core_executions (
    id VARCHAR2(255) PRIMARY KEY,
    workflow VARCHAR2(255) NOT NULL,
    params CLOB DEFAULT '{}',
    lane VARCHAR2(50) DEFAULT 'normal' NOT NULL,
    trigger_source VARCHAR2(100) DEFAULT 'api' NOT NULL,
    logical_key VARCHAR2(255),
    status VARCHAR2(50) DEFAULT 'pending' NOT NULL,
    parent_execution_id VARCHAR2(255),
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result CLOB,
    error CLOB,
    retry_count NUMBER DEFAULT 0,
    idempotency_key VARCHAR2(255),
    CONSTRAINT fk_exec_parent FOREIGN KEY (parent_execution_id) REFERENCES core_executions(id)
);

CREATE INDEX idx_core_executions_status ON core_executions(status);
CREATE INDEX idx_core_executions_workflow ON core_executions(workflow);
CREATE INDEX idx_core_executions_created_at ON core_executions(created_at);


CREATE TABLE core_manifest (
    domain VARCHAR2(255) NOT NULL,
    partition_key VARCHAR2(2000) NOT NULL,
    stage VARCHAR2(255) NOT NULL,
    stage_rank NUMBER,
    row_count NUMBER,
    metrics_json CLOB,
    execution_id VARCHAR2(255),
    batch_id VARCHAR2(255),
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_core_manifest UNIQUE (domain, partition_key, stage)
);

CREATE INDEX idx_core_manifest_domain ON core_manifest(domain, partition_key);
CREATE INDEX idx_core_manifest_stage ON core_manifest(domain, stage);
CREATE INDEX idx_core_manifest_updated ON core_manifest(updated_at);


-- =============================================================================
-- DATA QUALITY
-- =============================================================================

CREATE TABLE core_rejects (
    domain VARCHAR2(255) NOT NULL,
    partition_key VARCHAR2(2000) NOT NULL,
    stage VARCHAR2(255) NOT NULL,
    reason_code VARCHAR2(255) NOT NULL,
    reason_detail CLOB,
    raw_json CLOB,
    record_key VARCHAR2(255),
    source_locator VARCHAR2(500),
    line_number NUMBER,
    execution_id VARCHAR2(255) NOT NULL,
    batch_id VARCHAR2(255),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_core_rejects_domain ON core_rejects(domain);


CREATE TABLE core_quality (
    domain VARCHAR2(255) NOT NULL,
    partition_key VARCHAR2(2000) NOT NULL,
    check_name VARCHAR2(255) NOT NULL,
    category VARCHAR2(100) NOT NULL,
    status VARCHAR2(50) NOT NULL,
    message CLOB,
    actual_value CLOB,
    expected_value CLOB,
    details_json CLOB,
    execution_id VARCHAR2(255) NOT NULL,
    batch_id VARCHAR2(255),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_core_quality_domain ON core_quality(domain);


-- =============================================================================
-- ANOMALIES
-- =============================================================================

CREATE TABLE core_anomalies (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR2(255) NOT NULL,
    workflow VARCHAR2(255),
    partition_key VARCHAR2(2000),
    stage VARCHAR2(255),
    severity VARCHAR2(50) NOT NULL,
    category VARCHAR2(100) NOT NULL,
    message CLOB NOT NULL,
    details_json CLOB,
    affected_records NUMBER,
    sample_records CLOB,
    execution_id VARCHAR2(255),
    batch_id VARCHAR2(255),
    capture_id VARCHAR2(255),
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_note CLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_core_anomalies_domain ON core_anomalies(domain);
CREATE INDEX idx_core_anomalies_severity ON core_anomalies(severity);
CREATE INDEX idx_core_anomalies_category ON core_anomalies(category);
CREATE INDEX idx_core_anomalies_detected ON core_anomalies(detected_at);


-- =============================================================================
-- WORK ITEMS
-- =============================================================================

CREATE TABLE core_work_items (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR2(255) NOT NULL,
    workflow VARCHAR2(255) NOT NULL,
    partition_key VARCHAR2(2000) NOT NULL,
    params_json CLOB,
    desired_at TIMESTAMP NOT NULL,
    priority NUMBER DEFAULT 100,
    state VARCHAR2(50) DEFAULT 'PENDING' NOT NULL,
    attempt_count NUMBER DEFAULT 0,
    max_attempts NUMBER DEFAULT 3,
    last_error CLOB,
    last_error_at TIMESTAMP,
    next_attempt_at TIMESTAMP,
    current_execution_id VARCHAR2(255),
    latest_execution_id VARCHAR2(255),
    locked_by VARCHAR2(255),
    locked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uq_core_work_items UNIQUE (domain, workflow, partition_key)
);

CREATE INDEX idx_core_work_items_state ON core_work_items(state);
CREATE INDEX idx_core_work_items_desired ON core_work_items(desired_at);
CREATE INDEX idx_core_work_items_domain ON core_work_items(domain, workflow);


-- =============================================================================
-- EXECUTION EVENTS & DEAD LETTERS
-- =============================================================================

CREATE TABLE core_execution_events (
    id VARCHAR2(255) PRIMARY KEY,
    execution_id VARCHAR2(255) NOT NULL,
    event_type VARCHAR2(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    data CLOB DEFAULT '{}',
    CONSTRAINT fk_exec_events FOREIGN KEY (execution_id)
        REFERENCES core_executions(id) ON DELETE CASCADE
);

CREATE INDEX idx_core_exec_events_eid ON core_execution_events(execution_id);
CREATE INDEX idx_core_exec_events_ts ON core_execution_events(timestamp);


CREATE TABLE core_dead_letters (
    id VARCHAR2(255) PRIMARY KEY,
    execution_id VARCHAR2(255) NOT NULL,
    workflow VARCHAR2(255) NOT NULL,
    params CLOB DEFAULT '{}',
    error CLOB NOT NULL,
    retry_count NUMBER DEFAULT 0,
    max_retries NUMBER DEFAULT 3,
    created_at TIMESTAMP NOT NULL,
    last_retry_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR2(255)
);

CREATE INDEX idx_core_dl_resolved ON core_dead_letters(resolved_at);
CREATE INDEX idx_core_dl_workflow ON core_dead_letters(workflow);


-- =============================================================================
-- CONCURRENCY
-- =============================================================================

CREATE TABLE core_concurrency_locks (
    lock_key VARCHAR2(255) PRIMARY KEY,
    execution_id VARCHAR2(255) NOT NULL,
    acquired_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_core_conc_locks_exp ON core_concurrency_locks(expires_at);


-- =============================================================================
-- SCHEDULER
-- =============================================================================

CREATE TABLE core_schedules (
    id VARCHAR2(255) PRIMARY KEY,
    name VARCHAR2(255) NOT NULL UNIQUE,
    target_type VARCHAR2(50) DEFAULT 'operation' NOT NULL,
    target_name VARCHAR2(255) NOT NULL,
    params CLOB,
    schedule_type VARCHAR2(50) DEFAULT 'cron' NOT NULL,
    cron_expression VARCHAR2(100),
    interval_seconds NUMBER,
    run_at VARCHAR2(50),
    timezone VARCHAR2(50) DEFAULT 'UTC' NOT NULL,
    enabled NUMBER(1) DEFAULT 1 NOT NULL,
    max_instances NUMBER DEFAULT 1 NOT NULL,
    misfire_grace_seconds NUMBER DEFAULT 60 NOT NULL,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status VARCHAR2(50),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    created_by VARCHAR2(255),
    version NUMBER DEFAULT 1 NOT NULL
);

CREATE INDEX idx_schedules_enabled ON core_schedules(enabled);
CREATE INDEX idx_schedules_target ON core_schedules(target_type, target_name);


CREATE TABLE core_schedule_runs (
    id VARCHAR2(255) PRIMARY KEY,
    schedule_id VARCHAR2(255) NOT NULL,
    schedule_name VARCHAR2(255) NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR2(50) DEFAULT 'PENDING' NOT NULL,
    run_id VARCHAR2(255),
    execution_id VARCHAR2(255),
    error CLOB,
    skip_reason CLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_sched_runs_sid ON core_schedule_runs(schedule_id);
CREATE INDEX idx_sched_runs_status ON core_schedule_runs(status);
CREATE INDEX idx_sched_runs_sched ON core_schedule_runs(scheduled_at);


CREATE TABLE core_schedule_locks (
    schedule_id VARCHAR2(255) PRIMARY KEY,
    locked_by VARCHAR2(255) NOT NULL,
    locked_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_sched_locks_exp ON core_schedule_locks(expires_at);


-- =============================================================================
-- CALC DEPENDENCIES, EXPECTED SCHEDULES, DATA READINESS
-- =============================================================================

CREATE TABLE core_calc_dependencies (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calc_domain VARCHAR2(255) NOT NULL,
    calc_operation VARCHAR2(255) NOT NULL,
    calc_table VARCHAR2(255),
    depends_on_domain VARCHAR2(255) NOT NULL,
    depends_on_table VARCHAR2(255) NOT NULL,
    dependency_type VARCHAR2(50) NOT NULL,
    description CLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_core_calc_deps_calc ON core_calc_dependencies(calc_domain, calc_operation);
CREATE INDEX idx_core_calc_deps_upstream ON core_calc_dependencies(depends_on_domain, depends_on_table);


CREATE TABLE core_expected_schedules (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR2(255) NOT NULL,
    workflow VARCHAR2(255) NOT NULL,
    schedule_type VARCHAR2(50) NOT NULL,
    cron_expression VARCHAR2(100),
    partition_template VARCHAR2(2000) NOT NULL,
    partition_values CLOB,
    expected_delay_hours NUMBER,
    preliminary_hours NUMBER,
    description CLOB,
    is_active NUMBER(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_core_exp_sched_domain ON core_expected_schedules(domain, workflow);
CREATE INDEX idx_core_exp_sched_active ON core_expected_schedules(is_active);


CREATE TABLE core_data_readiness (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR2(255) NOT NULL,
    partition_key VARCHAR2(2000) NOT NULL,
    is_ready NUMBER(1) DEFAULT 0,
    ready_for VARCHAR2(100),
    all_partitions_present NUMBER(1) DEFAULT 0,
    all_stages_complete NUMBER(1) DEFAULT 0,
    no_critical_anomalies NUMBER(1) DEFAULT 0,
    dependencies_current NUMBER(1) DEFAULT 0,
    age_exceeds_preliminary NUMBER(1) DEFAULT 0,
    blocking_issues CLOB,
    certified_at TIMESTAMP,
    certified_by VARCHAR2(255),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_core_data_readiness UNIQUE (domain, partition_key, ready_for)
);

CREATE INDEX idx_core_data_readiness_domain ON core_data_readiness(domain);
CREATE INDEX idx_core_data_readiness_status ON core_data_readiness(is_ready);
