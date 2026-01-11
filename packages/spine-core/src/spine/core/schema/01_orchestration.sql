-- =============================================================================
-- SPINE CORE - ORCHESTRATION TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Tables for pipeline group orchestration.
--              Stores group definitions, run history, and step-to-execution mapping.
--
-- Tier Usage:
--   Basic: Optional (groups run without persistence)
--   Intermediate: Optional (adds group run tracking)
--   Advanced/Full: Recommended (full history, DLQ integration)
--
-- Dependencies: Requires core_executions table (from 00_core.sql)
-- =============================================================================


-- =============================================================================
-- PIPELINE GROUPS (Group Definitions)
-- =============================================================================

-- Stores pipeline group definitions (alternative to YAML files)
-- Groups can also be loaded from YAML without using this table
CREATE TABLE IF NOT EXISTS core_pipeline_groups (
    id TEXT PRIMARY KEY,                    -- ULID
    name TEXT NOT NULL UNIQUE,              -- e.g., "finra.weekly_refresh"
    domain TEXT NOT NULL,                   -- e.g., "finra.otc_transparency"
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    spec TEXT NOT NULL,                     -- JSON: Full group spec (steps, policy, defaults)
    tags TEXT,                              -- JSON array: ["finra", "weekly"]
    created_at TEXT NOT NULL,               -- ISO timestamp
    updated_at TEXT NOT NULL,               -- ISO timestamp
    created_by TEXT,                        -- User/system that created
    is_active INTEGER NOT NULL DEFAULT 1    -- 1=active, 0=soft-deleted
);

CREATE INDEX IF NOT EXISTS idx_core_pipeline_groups_domain 
    ON core_pipeline_groups(domain);
CREATE INDEX IF NOT EXISTS idx_core_pipeline_groups_active 
    ON core_pipeline_groups(is_active) WHERE is_active = 1;


-- =============================================================================
-- GROUP RUNS (Execution History)
-- =============================================================================

-- Tracks each execution of a pipeline group
-- One row per "spine groups run <name>" invocation
CREATE TABLE IF NOT EXISTS core_group_runs (
    id TEXT PRIMARY KEY,                    -- ULID
    group_name TEXT NOT NULL,               -- e.g., "finra.weekly_refresh"
    group_version INTEGER NOT NULL,         -- Version at time of execution
    params TEXT,                            -- JSON: Runtime parameters
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed, partial, cancelled
    trigger_source TEXT NOT NULL,           -- cli, api, scheduler
    batch_id TEXT NOT NULL,                 -- Links to core_executions.batch_id
    total_steps INTEGER NOT NULL,           -- Number of steps in plan
    completed_steps INTEGER NOT NULL DEFAULT 0,
    failed_steps INTEGER NOT NULL DEFAULT 0,
    skipped_steps INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,                        -- ISO timestamp
    completed_at TEXT,                      -- ISO timestamp
    error TEXT,                             -- Error message if failed
    created_at TEXT NOT NULL                -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_core_group_runs_status 
    ON core_group_runs(status);
CREATE INDEX IF NOT EXISTS idx_core_group_runs_batch_id 
    ON core_group_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_core_group_runs_group_name 
    ON core_group_runs(group_name);
CREATE INDEX IF NOT EXISTS idx_core_group_runs_created_at 
    ON core_group_runs(created_at);


-- =============================================================================
-- GROUP RUN STEPS (Step-to-Execution Mapping)
-- =============================================================================

-- Maps each step in a group run to its execution
-- Enables drilling from group run → individual pipeline executions
CREATE TABLE IF NOT EXISTS core_group_run_steps (
    id TEXT PRIMARY KEY,                    -- ULID
    group_run_id TEXT NOT NULL,             -- FK to core_group_runs
    step_name TEXT NOT NULL,                -- e.g., "ingest", "normalize"
    pipeline_name TEXT NOT NULL,            -- e.g., "finra.otc_transparency.ingest_week"
    execution_id TEXT,                      -- FK to core_executions (NULL if not yet started)
    sequence_order INTEGER NOT NULL,        -- Order in execution plan (0-based)
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed, skipped
    params TEXT,                            -- JSON: Merged parameters for this step
    started_at TEXT,                        -- ISO timestamp
    completed_at TEXT,                      -- ISO timestamp
    error TEXT,                             -- Error message if failed
    UNIQUE(group_run_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_core_group_run_steps_group_run 
    ON core_group_run_steps(group_run_id);
CREATE INDEX IF NOT EXISTS idx_core_group_run_steps_execution 
    ON core_group_run_steps(execution_id) WHERE execution_id IS NOT NULL;


-- =============================================================================
-- VIEWS
-- =============================================================================

-- Latest run for each group (useful for dashboards)
CREATE VIEW IF NOT EXISTS v_core_group_latest_runs AS
SELECT 
    gr.*,
    (SELECT COUNT(*) FROM core_group_run_steps s WHERE s.group_run_id = gr.id AND s.status = 'completed') as steps_completed,
    (SELECT COUNT(*) FROM core_group_run_steps s WHERE s.group_run_id = gr.id AND s.status = 'failed') as steps_failed
FROM core_group_runs gr
WHERE gr.created_at = (
    SELECT MAX(created_at) 
    FROM core_group_runs 
    WHERE group_name = gr.group_name
);

-- Group run with step details (for API responses)
CREATE VIEW IF NOT EXISTS v_core_group_run_details AS
SELECT 
    gr.id as group_run_id,
    gr.group_name,
    gr.group_version,
    gr.status as group_status,
    gr.batch_id,
    gr.started_at as group_started_at,
    gr.completed_at as group_completed_at,
    s.step_name,
    s.pipeline_name,
    s.execution_id,
    s.sequence_order,
    s.status as step_status,
    s.started_at as step_started_at,
    s.completed_at as step_completed_at,
    s.error as step_error
FROM core_group_runs gr
LEFT JOIN core_group_run_steps s ON s.group_run_id = gr.id
ORDER BY gr.created_at DESC, s.sequence_order ASC;
