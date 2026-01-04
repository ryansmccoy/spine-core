-- Dead letter queue table
CREATE TABLE IF NOT EXISTS dead_letters (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    pipeline TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    error TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_retry_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_dead_letters_resolved ON dead_letters(resolved_at);
CREATE INDEX IF NOT EXISTS idx_dead_letters_pipeline ON dead_letters(pipeline);
