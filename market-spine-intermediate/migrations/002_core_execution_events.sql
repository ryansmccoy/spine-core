-- Execution events table
CREATE TABLE IF NOT EXISTS execution_events (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB,
    idempotency_key TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_events_execution ON execution_events(execution_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON execution_events(event_type);
