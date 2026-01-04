-- Core executions table
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    params JSONB,
    lane TEXT NOT NULL DEFAULT 'normal',
    trigger_source TEXT NOT NULL,
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    backend TEXT NOT NULL DEFAULT 'local',
    backend_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    result JSONB
);

CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_pipeline ON executions(pipeline);
CREATE INDEX IF NOT EXISTS idx_executions_logical_key ON executions(logical_key) WHERE logical_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_executions_pending ON executions(created_at) WHERE status IN ('pending', 'queued');
