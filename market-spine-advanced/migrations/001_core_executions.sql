-- Core executions table
-- Tracks all pipeline execution requests and their status

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    backend TEXT,
    backend_run_id TEXT,
    parent_execution_id TEXT REFERENCES executions(id),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    
    CONSTRAINT valid_status CHECK (status IN ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled', 'dlq', 'retried'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_pipeline ON executions(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_executions_created ON executions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_executions_parent ON executions(parent_execution_id);

-- Partial unique index for logical_key concurrency control
-- Only one active execution per logical_key
CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_logical_key_active 
ON executions(logical_key) 
WHERE logical_key IS NOT NULL AND status IN ('pending', 'queued', 'running');

-- DLQ index for failed executions
CREATE INDEX IF NOT EXISTS idx_executions_dlq ON executions(status, created_at) 
WHERE status = 'dlq';
