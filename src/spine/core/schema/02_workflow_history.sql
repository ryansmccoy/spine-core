-- =============================================================================
-- SPINE CORE - WORKFLOW HISTORY TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Tables for workflow execution history and run tracking.
--              Enables audit, debugging, and operational visibility.
--
-- Tier Usage:
--   Basic: Optional (runs without persistence)
--   Intermediate: Required (full history)
--   Advanced/Full: Required (+ retention policies)
--
-- Design Principles Applied:
--   #8 Idempotency: run_id is deterministic from workflow+params+timestamp
--   #13 Observable: All runs tracked with complete context
--
-- Dependencies: Requires core_executions table (from 00_core.sql)
-- =============================================================================


-- =============================================================================
-- WORKFLOW RUNS (Top-level execution tracking)
-- =============================================================================

-- Tracks each execution of a workflow (v2 orchestration)
-- One row per workflow.run() invocation
CREATE TABLE IF NOT EXISTS core_workflow_runs (
    -- Identity
    run_id TEXT PRIMARY KEY,                -- ULID or deterministic ID
    workflow_name TEXT NOT NULL,            -- e.g., "finra.weekly_ingest"
    workflow_version INTEGER NOT NULL DEFAULT 1,
    
    -- Scope
    domain TEXT,                            -- e.g., "finra.otc_transparency"
    partition_key TEXT,                     -- JSON: {"week_ending": "2025-01-10", "tier": "NMS_TIER_1"}
    
    -- State (PENDING → RUNNING → COMPLETED | FAILED | CANCELLED)
    status TEXT NOT NULL DEFAULT 'PENDING',
    
    -- Timing
    started_at TEXT,                        -- ISO timestamp
    completed_at TEXT,                      -- ISO timestamp
    duration_ms INTEGER,                    -- Computed on completion
    
    -- Context
    params TEXT,                            -- JSON: Input parameters
    outputs TEXT,                           -- JSON: Final outputs
    
    -- Results
    error TEXT,                             -- Error message if failed
    error_category TEXT,                    -- Error category for retry decisions
    error_retryable INTEGER,                -- 1=retryable, 0=permanent
    
    -- Metrics
    total_steps INTEGER NOT NULL DEFAULT 0,
    completed_steps INTEGER NOT NULL DEFAULT 0,
    failed_steps INTEGER NOT NULL DEFAULT 0,
    skipped_steps INTEGER NOT NULL DEFAULT 0,
    
    -- Trigger
    triggered_by TEXT NOT NULL DEFAULT 'manual',  -- manual, schedule, api, parent_workflow
    parent_run_id TEXT,                     -- FK to parent workflow (for nested workflows)
    schedule_id TEXT,                       -- FK to core_schedules if triggered by schedule
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT,                        -- User or system that triggered
    
    -- Capture ID for this run's outputs
    capture_id TEXT                         -- Links outputs to this run
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON core_workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON core_workflow_runs(workflow_name);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_domain ON core_workflow_runs(domain);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started ON core_workflow_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created ON core_workflow_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_parent ON core_workflow_runs(parent_run_id) WHERE parent_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_runs_schedule ON core_workflow_runs(schedule_id) WHERE schedule_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_runs_failed ON core_workflow_runs(status, created_at) WHERE status = 'FAILED';


-- =============================================================================
-- WORKFLOW STEPS (Step-level execution details)
-- =============================================================================

-- Tracks each step within a workflow run
-- Enables drilling from run → individual step executions
CREATE TABLE IF NOT EXISTS core_workflow_steps (
    -- Identity
    step_id TEXT PRIMARY KEY,               -- ULID
    run_id TEXT NOT NULL,                   -- FK to core_workflow_runs
    
    -- Step definition
    step_name TEXT NOT NULL,                -- e.g., "fetch_data", "validate", "compute"
    step_type TEXT NOT NULL,                -- e.g., "operation", "task", "condition", "parallel"
    step_order INTEGER NOT NULL,            -- Execution order (0-based)
    
    -- State (PENDING → RUNNING → COMPLETED | FAILED | SKIPPED)
    status TEXT NOT NULL DEFAULT 'PENDING',
    
    -- Timing
    started_at TEXT,                        -- ISO timestamp
    completed_at TEXT,                      -- ISO timestamp
    duration_ms INTEGER,                    -- Computed on completion
    
    -- Context
    params TEXT,                            -- JSON: Input parameters for this step
    outputs TEXT,                           -- JSON: Step outputs
    
    -- Results
    error TEXT,                             -- Error message if failed
    error_category TEXT,                    -- Error classification
    
    -- Metrics
    row_count INTEGER,                      -- Rows processed (if applicable)
    metrics TEXT,                           -- JSON: Additional metrics
    
    -- Retry tracking
    attempt INTEGER NOT NULL DEFAULT 1,     -- Current attempt number
    max_attempts INTEGER NOT NULL DEFAULT 1,
    
    -- Execution linkage
    execution_id TEXT,                      -- FK to core_executions (if operation step)
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(run_id, step_name, attempt)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_workflow_steps_run ON core_workflow_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_status ON core_workflow_steps(status);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_execution ON core_workflow_steps(execution_id) WHERE execution_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_steps_failed ON core_workflow_steps(run_id, status) WHERE status = 'FAILED';


-- =============================================================================
-- WORKFLOW EVENTS (Step-level lifecycle events)
-- =============================================================================

-- Immutable event log for workflow state transitions
-- Enables audit trail and debugging
CREATE TABLE IF NOT EXISTS core_workflow_events (
    -- Identity
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,                   -- FK to core_workflow_runs
    step_id TEXT,                           -- FK to core_workflow_steps (NULL for run-level events)
    
    -- Event
    event_type TEXT NOT NULL,               -- started, completed, failed, retrying, skipped, cancelled
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Context
    payload TEXT,                           -- JSON: Event-specific data
    
    -- Idempotency
    idempotency_key TEXT UNIQUE             -- Prevents duplicate events
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_workflow_events_run ON core_workflow_events(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_workflow_events_step ON core_workflow_events(step_id) WHERE step_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_events_type ON core_workflow_events(event_type);
