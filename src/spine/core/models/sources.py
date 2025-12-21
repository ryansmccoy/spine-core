"""Source tracking table models (05_sources.sql).

Manifesto:
    Data source registry, fetch history, caching, and DB connection
    config need typed dataclass representations for the ops layer
    and API to work with structured objects.

Models for data source tracking: source registry, fetch history,
caching, and database connection configuration.

Tags:
    spine-core, models, sources, dataclasses, schema-mapping

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# core_sources
# ---------------------------------------------------------------------------


@dataclass
class Source:
    """Source registry row (``core_sources``)."""

    id: str = ""
    name: str = ""
    source_type: str = ""  # file, http, database, s3, sftp
    config_json: str = ""  # JSON type-specific configuration
    domain: str | None = None
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    created_by: str | None = None


# ---------------------------------------------------------------------------
# core_source_fetches
# ---------------------------------------------------------------------------


@dataclass
class SourceFetch:
    """Fetch history row (``core_source_fetches``)."""

    id: str = ""
    source_id: str | None = None
    source_name: str = ""
    source_type: str = ""  # file, http, database
    source_locator: str = ""
    status: str = ""  # SUCCESS, FAILED, NOT_FOUND, UNCHANGED
    record_count: int | None = None
    byte_count: int | None = None
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    started_at: str = ""
    completed_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    error_category: str | None = None
    retry_count: int = 0
    execution_id: str | None = None
    run_id: str | None = None
    capture_id: str | None = None
    metadata_json: str | None = None  # JSON additional source metadata
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_source_cache
# ---------------------------------------------------------------------------


@dataclass
class SourceCacheEntry:
    """Source cache row (``core_source_cache``)."""

    cache_key: str = ""
    source_id: str | None = None
    source_type: str = ""
    source_locator: str = ""
    content_hash: str = ""
    content_size: int = 0
    content_path: str | None = None
    # Note: content_blob (BLOB) omitted – binary payloads should be
    # handled at the DB layer, not serialised into Pydantic models.
    fetched_at: str = ""
    expires_at: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    metadata_json: str | None = None  # JSON source metadata
    created_at: str = ""
    last_accessed_at: str | None = None


# ---------------------------------------------------------------------------
# core_database_connections
# ---------------------------------------------------------------------------


@dataclass
class DatabaseConnectionConfig:
    """Database connection configuration row (``core_database_connections``)."""

    id: str = ""
    name: str = ""
    dialect: str = ""  # sqlite, postgresql, db2
    host: str | None = None
    port: int | None = None
    database: str = ""
    username: str | None = None
    password_ref: str | None = None  # Reference to secret store (never plaintext)
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    enabled: bool = True
    last_connected_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    created_by: str | None = None
