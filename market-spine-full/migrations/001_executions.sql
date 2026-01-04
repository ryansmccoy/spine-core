-- Executions table - the core execution ledger
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    lane TEXT NOT NULL DEFAULT 'default',
    trigger_source TEXT NOT NULL DEFAULT 'api',
    parent_execution_id TEXT REFERENCES executions(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result JSONB,
    error TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_pipeline ON executions(pipeline);
CREATE INDEX IF NOT EXISTS idx_executions_created_at ON executions(created_at);
