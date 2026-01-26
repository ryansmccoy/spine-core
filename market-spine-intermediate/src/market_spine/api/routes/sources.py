"""Source management endpoints.

Provides API access to data sources, fetch history, and cache.

Follows API Design Guardrails:
- Resource-style URLs: /v1/sources, /v1/sources/{id}/fetches
- Pagination: offset/limit with has_more
- Standard error envelope
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    offset: int
    limit: int
    total: int
    has_more: bool


# -----------------------------------------------------------------------------
# Sources
# -----------------------------------------------------------------------------


class SourceCreate(BaseModel):
    """Request to register a new source."""
    name: str = Field(..., description="Unique source name")
    source_type: Literal["file", "http", "database", "s3", "sftp"] = Field(..., description="Source type")
    domain: str | None = Field(None, description="Business domain (e.g., 'finra')")
    
    # Connection config (type-specific)
    config: dict[str, Any] = Field(..., description="Type-specific connection configuration")
    
    # Scheduling
    cron_expression: str | None = Field(None, description="Fetch schedule as cron expression")
    
    # Parse settings
    parser_type: str | None = Field(None, description="Parser to use (e.g., 'csv', 'json', 'xml')")
    parser_config: dict[str, Any] | None = Field(None, description="Parser configuration")
    
    enabled: bool = Field(True, description="Whether source is active")


class SourceUpdate(BaseModel):
    """Request to update a source."""
    config: dict[str, Any] | None = None
    cron_expression: str | None = None
    parser_type: str | None = None
    parser_config: dict[str, Any] | None = None
    enabled: bool | None = None


class SourceSummary(BaseModel):
    """Summary of a source for list views."""
    id: str
    name: str
    source_type: str
    domain: str | None
    enabled: bool
    
    # Health
    last_fetch_at: datetime | None
    last_fetch_status: Literal["SUCCESS", "FAILED", "PARTIAL"] | None
    consecutive_failures: int
    
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceDetail(BaseModel):
    """Full source details."""
    id: str
    name: str
    source_type: str
    domain: str | None
    config: dict[str, Any]  # Sensitive fields redacted
    
    # Scheduling
    cron_expression: str | None
    next_fetch_at: datetime | None
    
    # Parse settings
    parser_type: str | None
    parser_config: dict[str, Any] | None
    
    enabled: bool
    
    # Health
    last_fetch_at: datetime | None
    last_fetch_status: str | None
    last_fetch_error: str | None
    consecutive_failures: int
    
    # Stats
    total_fetches: int
    success_rate: float
    avg_fetch_duration_ms: float | None
    
    # Change detection
    last_content_hash: str | None
    last_etag: str | None
    last_modified: str | None
    
    # Audit
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = {"from_attributes": True}


class SourceList(BaseModel):
    """Paginated list of sources."""
    data: list[SourceSummary]
    pagination: PaginationMeta


class SourceActionResponse(BaseModel):
    """Response for source actions."""
    id: str
    status: str
    message: str


# -----------------------------------------------------------------------------
# Fetches
# -----------------------------------------------------------------------------


class FetchSummary(BaseModel):
    """Summary of a fetch operation."""
    id: str
    source_id: str
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    
    # Change detection
    content_changed: bool
    
    # Metrics
    bytes_fetched: int | None
    rows_parsed: int | None

    model_config = {"from_attributes": True}


class FetchDetail(BaseModel):
    """Full fetch operation details."""
    id: str
    source_id: str
    source_name: str
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]
    trigger: Literal["SCHEDULE", "MANUAL", "API", "DEPENDENCY"]
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    
    # Change detection
    content_changed: bool
    content_hash: str | None
    etag: str | None
    last_modified: str | None
    
    # Metrics
    bytes_fetched: int | None
    rows_parsed: int | None
    
    # Errors
    error: str | None
    error_category: str | None
    
    # Context
    triggered_by: str | None
    execution_id: str | None
    run_id: str | None
    
    # Capture reference
    capture_id: str | None

    model_config = {"from_attributes": True}


class FetchList(BaseModel):
    """Paginated list of fetches."""
    data: list[FetchSummary]
    pagination: PaginationMeta


class FetchTriggerResponse(BaseModel):
    """Response when triggering a fetch."""
    fetch_id: str
    source_id: str
    source_name: str
    status: Literal["PENDING", "STARTED"]
    message: str


# -----------------------------------------------------------------------------
# Cache
# -----------------------------------------------------------------------------


class CacheEntry(BaseModel):
    """Cached source data entry."""
    id: str
    source_id: str
    source_name: str
    cache_key: str
    content_hash: str
    size_bytes: int
    cached_at: datetime
    expires_at: datetime | None
    
    # Source reference
    fetch_id: str | None
    
    # Metadata
    content_type: str | None
    encoding: str | None

    model_config = {"from_attributes": True}


class CacheList(BaseModel):
    """Paginated list of cache entries."""
    data: list[CacheEntry]
    pagination: PaginationMeta


class CacheStats(BaseModel):
    """Cache statistics."""
    total_entries: int
    total_bytes: int
    hit_rate: float
    miss_rate: float
    expired_entries: int
    by_source: dict[str, int]


# -----------------------------------------------------------------------------
# Database Connections
# -----------------------------------------------------------------------------


class DatabaseConnectionCreate(BaseModel):
    """Request to create a database connection."""
    name: str = Field(..., description="Unique connection name")
    db_type: Literal["postgresql", "db2", "sqlite", "mysql", "oracle"] = Field(..., description="Database type")
    host: str
    port: int
    database: str
    username: str | None = None
    password_ref: str | None = Field(None, description="Reference to secret store for password")
    
    # Connection pool
    pool_size: int = Field(5, description="Connection pool size")
    pool_overflow: int = Field(10, description="Max overflow connections")
    
    # SSL/TLS
    ssl_mode: Literal["disable", "require", "verify-ca", "verify-full"] = Field("require", description="SSL mode")
    ssl_cert_ref: str | None = Field(None, description="Reference to SSL certificate")
    
    enabled: bool = Field(True, description="Whether connection is active")


class DatabaseConnectionResponse(BaseModel):
    """Database connection details."""
    id: str
    name: str
    db_type: str
    host: str
    port: int
    database: str
    username: str | None
    
    # Pool
    pool_size: int
    pool_overflow: int
    
    # SSL
    ssl_mode: str
    
    enabled: bool
    
    # Health
    last_health_check_at: datetime | None
    health_status: Literal["HEALTHY", "UNHEALTHY", "UNKNOWN"]
    health_message: str | None
    
    # Stats
    active_connections: int
    idle_connections: int
    
    # Audit
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DatabaseConnectionList(BaseModel):
    """Paginated list of database connections."""
    data: list[DatabaseConnectionResponse]
    pagination: PaginationMeta


# =============================================================================
# SOURCE ENDPOINTS
# =============================================================================


@router.get(
    "",
    response_model=SourceList,
    summary="List sources",
    description="Get registered data sources",
)
async def list_sources(
    source_type: str | None = Query(None, description="Filter by source type"),
    domain: str | None = Query(None, description="Filter by domain"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all registered data sources."""
    return SourceList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.post(
    "",
    response_model=SourceDetail,
    status_code=201,
    summary="Register source",
    description="Register a new data source",
)
async def create_source(request: SourceCreate):
    """
    Register a new data source.
    
    The source will start fetching on schedule if cron_expression is provided.
    """
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Source registration not yet implemented"},
    )


@router.get(
    "/{source_id}",
    response_model=SourceDetail,
    summary="Get source",
    description="Get source details",
)
async def get_source(
    source_id: str = Path(..., description="Source ID or name"),
):
    """Get details of a specific source."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Source not found: {source_id}"},
    )


@router.patch(
    "/{source_id}",
    response_model=SourceDetail,
    summary="Update source",
    description="Update source configuration",
)
async def update_source(
    source_id: str = Path(..., description="Source ID or name"),
    request: SourceUpdate = ...,
):
    """Update a source configuration."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Source not found: {source_id}"},
    )


@router.delete(
    "/{source_id}",
    status_code=204,
    summary="Delete source",
    description="Remove a data source",
)
async def delete_source(
    source_id: str = Path(..., description="Source ID or name"),
):
    """Delete a data source."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Source not found: {source_id}"},
    )


@router.post(
    "/{source_id}/enable",
    response_model=SourceActionResponse,
    summary="Enable source",
)
async def enable_source(source_id: str = Path(...)):
    """Enable a disabled source."""
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Source not found: {source_id}"})


@router.post(
    "/{source_id}/disable",
    response_model=SourceActionResponse,
    summary="Disable source",
)
async def disable_source(source_id: str = Path(...)):
    """Disable a source."""
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Source not found: {source_id}"})


# =============================================================================
# FETCH ENDPOINTS
# =============================================================================


@router.get(
    "/{source_id}/fetches",
    response_model=FetchList,
    summary="List fetches for source",
    description="Get fetch history for a source",
)
async def list_source_fetches(
    source_id: str = Path(..., description="Source ID or name"),
    status: str | None = Query(None, description="Filter by status"),
    start_date: str | None = Query(None, description="Filter by date range start"),
    end_date: str | None = Query(None, description="Filter by date range end"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get fetch history for a specific source."""
    return FetchList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.post(
    "/{source_id}/fetch",
    response_model=FetchTriggerResponse,
    summary="Trigger fetch",
    description="Trigger an immediate fetch from the source",
)
async def trigger_fetch(
    source_id: str = Path(..., description="Source ID or name"),
    force: bool = Query(False, description="Force fetch even if no changes detected"),
):
    """
    Trigger an immediate fetch from the source.
    
    If force is True, will fetch even if content hasn't changed.
    """
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Source not found: {source_id}"},
    )


@router.get(
    "/fetches/all",
    response_model=FetchList,
    summary="List all fetches",
    description="Get fetch history across all sources",
)
async def list_all_fetches(
    source_type: str | None = Query(None, description="Filter by source type"),
    status: str | None = Query(None, description="Filter by status"),
    domain: str | None = Query(None, description="Filter by domain"),
    start_date: str | None = Query(None, description="Filter by date range start"),
    end_date: str | None = Query(None, description="Filter by date range end"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get fetch history across all sources."""
    return FetchList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.get(
    "/fetches/{fetch_id}",
    response_model=FetchDetail,
    summary="Get fetch details",
    description="Get full details of a fetch operation",
)
async def get_fetch(
    fetch_id: str = Path(..., description="Fetch ID"),
):
    """Get full details of a fetch operation."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Fetch not found: {fetch_id}"},
    )


# =============================================================================
# CACHE ENDPOINTS
# =============================================================================


@router.get(
    "/cache",
    response_model=CacheList,
    summary="List cache entries",
    description="Get cached source data entries",
)
async def list_cache(
    source_id: str | None = Query(None, description="Filter by source ID"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List cached source data entries."""
    return CacheList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.get(
    "/cache/stats",
    response_model=CacheStats,
    summary="Get cache statistics",
)
async def get_cache_stats():
    """Get cache statistics."""
    return CacheStats(
        total_entries=0,
        total_bytes=0,
        hit_rate=0.0,
        miss_rate=0.0,
        expired_entries=0,
        by_source={},
    )


@router.delete(
    "/cache",
    status_code=204,
    summary="Clear cache",
    description="Clear source cache entries",
)
async def clear_cache(
    source_id: str | None = Query(None, description="Clear cache for specific source"),
    expired_only: bool = Query(False, description="Only clear expired entries"),
):
    """Clear source cache entries."""
    pass


# =============================================================================
# DATABASE CONNECTION ENDPOINTS
# =============================================================================


@router.get(
    "/connections",
    response_model=DatabaseConnectionList,
    summary="List database connections",
    description="Get registered database connections",
)
async def list_connections(
    db_type: str | None = Query(None, description="Filter by database type"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all registered database connections."""
    return DatabaseConnectionList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.post(
    "/connections",
    response_model=DatabaseConnectionResponse,
    status_code=201,
    summary="Create database connection",
    description="Register a new database connection",
)
async def create_connection(request: DatabaseConnectionCreate):
    """
    Register a new database connection.
    
    The connection will be health-checked immediately.
    """
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Connection creation not yet implemented"},
    )


@router.get(
    "/connections/{connection_id}",
    response_model=DatabaseConnectionResponse,
    summary="Get database connection",
)
async def get_connection(
    connection_id: str = Path(..., description="Connection ID or name"),
):
    """Get details of a database connection."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Connection not found: {connection_id}"},
    )


@router.delete(
    "/connections/{connection_id}",
    status_code=204,
    summary="Delete database connection",
)
async def delete_connection(
    connection_id: str = Path(..., description="Connection ID or name"),
):
    """Delete a database connection."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Connection not found: {connection_id}"},
    )


@router.post(
    "/connections/{connection_id}/test",
    response_model=SourceActionResponse,
    summary="Test database connection",
)
async def test_connection(
    connection_id: str = Path(..., description="Connection ID or name"),
):
    """Test a database connection."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Connection not found: {connection_id}"},
    )
