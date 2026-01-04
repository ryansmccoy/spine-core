-- File storage metadata table
-- Tracks files stored in storage backends (local/S3)

CREATE TABLE IF NOT EXISTS stored_files (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    storage_type TEXT NOT NULL,
    size_bytes BIGINT,
    content_type TEXT,
    checksum TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_stored_files_path ON stored_files(path);
CREATE INDEX IF NOT EXISTS idx_stored_files_created ON stored_files(created_at DESC);
