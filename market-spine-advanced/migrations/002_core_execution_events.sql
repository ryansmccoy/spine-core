-- Execution events table for event sourcing
-- Provides audit trail and debugging information

CREATE TABLE IF NOT EXISTS execution_events (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB DEFAULT '{}',
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_execution_events_execution ON execution_events(execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_type ON execution_events(event_type);
CREATE INDEX IF NOT EXISTS idx_execution_events_created ON execution_events(created_at);

-- Unique constraint for idempotency
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_events_idempotency 
ON execution_events(idempotency_key) 
WHERE idempotency_key IS NOT NULL;
