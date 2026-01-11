-- Concurrency locks table
CREATE TABLE IF NOT EXISTS concurrency_locks (
    lock_key TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    acquired_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_concurrency_locks_expires ON concurrency_locks(expires_at);
