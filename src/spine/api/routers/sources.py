"""
Sources router — data source registration and fetch tracking.

Provides endpoints for managing data sources, viewing fetch history,
managing cache, and configuring database connections.

Endpoints:
    GET  /sources                List registered data sources
    POST /sources                Register a new data source
    GET  /sources/{id}           Get source details
    DELETE /sources/{id}         Delete a data source
    POST /sources/{id}/enable    Enable a source
    POST /sources/{id}/disable   Disable a source
    GET  /sources/fetches        List source fetch history
    GET  /sources/cache          List cached source entries
    POST /sources/{id}/cache/invalidate  Invalidate source cache
    GET  /sources/connections    List database connections
    POST /sources/connections    Register a database connection
    DELETE /sources/connections/{id}  Delete a database connection
    POST /sources/connections/{id}/test  Test a database connection

Manifesto:
    Data sources must be manageable through the API so operators
    can add, update, and monitor ingestion endpoints dynamically.

Tags:
    spine-core, api, sources, data-source, ingestion, configuration

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/sources")


# ------------------------------------------------------------------ #
# Pydantic Schemas
# ------------------------------------------------------------------ #


class SourceSchema(BaseModel):
    """Data source representation."""

    id: str
    name: str
    source_type: str
    domain: str | None = None
    enabled: bool = True
    created_at: str | None = None


class SourceDetailSchema(BaseModel):
    """Full data source representation."""

    id: str
    name: str
    source_type: str
    config: dict[str, Any] = {}
    domain: str | None = None
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class SourceCreateRequest(BaseModel):
    """Request body for registering a data source."""

    name: str = Field(..., description="Unique source name")
    source_type: str = Field(..., description="Source type: file, http, database, s3, sftp")
    config: dict[str, Any] = Field(default_factory=dict, description="Type-specific configuration")
    domain: str | None = Field(default=None, description="Domain context")
    enabled: bool = Field(default=True, description="Whether source is active")


class SourceFetchSchema(BaseModel):
    """Source fetch history entry."""

    id: str
    source_id: str | None = None
    source_name: str
    source_type: str
    source_locator: str
    status: str
    record_count: int | None = None
    byte_count: int | None = None
    started_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class SourceCacheSchema(BaseModel):
    """Source cache entry."""

    cache_key: str
    source_id: str | None = None
    source_type: str
    source_locator: str
    content_hash: str
    content_size: int
    fetched_at: str | None = None
    expires_at: str | None = None


class DatabaseConnectionSchema(BaseModel):
    """Database connection representation."""

    id: str
    name: str
    dialect: str
    host: str | None = None
    port: int | None = None
    database: str
    enabled: bool = True
    last_connected_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None


class DatabaseConnectionCreateRequest(BaseModel):
    """Request body for registering a database connection."""

    name: str = Field(..., description="Unique connection name")
    dialect: str = Field(..., description="Database dialect: postgresql, mysql, sqlite, oracle, db2")
    host: str | None = Field(default=None, description="Database host")
    port: int | None = Field(default=None, description="Database port")
    database: str = Field(..., description="Database name")
    username: str | None = Field(default=None, description="Username")
    password_ref: str | None = Field(default=None, description="Reference to password secret")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max pool overflow")
    pool_timeout: int = Field(default=30, description="Pool timeout seconds")
    enabled: bool = Field(default=True, description="Whether connection is active")


# ------------------------------------------------------------------ #
# Sources Endpoints
# ------------------------------------------------------------------ #


@router.get("", response_model=PagedResponse[SourceSchema])
def list_sources(
    ctx: OpContext,
    source_type: str | None = Query(None, description="Filter by source type"),
    domain: str | None = Query(None, description="Filter by domain"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List registered data sources.

    Returns data sources configured for fetching. Sources can be
    filtered by type (file, http, database) and enabled status.
    """
    from spine.ops.requests import ListSourcesRequest
    from spine.ops.sources import list_sources as _list

    request = ListSourcesRequest(
        source_type=source_type,
        domain=domain,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }


@router.post("", status_code=201)
def register_source(
    ctx: OpContext,
    body: SourceCreateRequest,
):
    """Register a new data source.

    Creates a new source definition that can be used for data fetching.
    """
    from spine.ops.requests import CreateSourceRequest
    from spine.ops.sources import register_source as _register

    request = CreateSourceRequest(
        name=body.name,
        source_type=body.source_type,
        config=body.config,
        domain=body.domain,
        enabled=body.enabled,
    )
    result = _register(ctx, request)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


@router.get("/{source_id}", response_model=SourceDetailSchema)
def get_source(
    ctx: OpContext,
    source_id: str = Path(..., description="Source ID"),
):
    """Get data source details.

    Returns full configuration for a specific source.
    """
    from spine.ops.sources import get_source as _get

    result = _get(ctx, source_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


@router.delete("/{source_id}")
def delete_source(
    ctx: OpContext,
    source_id: str = Path(..., description="Source ID"),
):
    """Delete a data source.

    Removes the source definition. Fetch history is preserved.
    """
    from spine.ops.sources import delete_source as _delete

    result = _delete(ctx, source_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


@router.post("/{source_id}/enable")
def enable_source(
    ctx: OpContext,
    source_id: str = Path(..., description="Source ID"),
):
    """Enable a data source."""
    from spine.ops.sources import enable_source as _enable

    result = _enable(ctx, source_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


@router.post("/{source_id}/disable")
def disable_source(
    ctx: OpContext,
    source_id: str = Path(..., description="Source ID"),
):
    """Disable a data source."""
    from spine.ops.sources import disable_source as _disable

    result = _disable(ctx, source_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


# ------------------------------------------------------------------ #
# Fetch History Endpoints
# ------------------------------------------------------------------ #


@router.get("/fetches", response_model=PagedResponse[SourceFetchSchema])
def list_source_fetches(
    ctx: OpContext,
    source_id: str | None = Query(None, description="Filter by source ID"),
    source_name: str | None = Query(None, description="Filter by source name"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List source fetch history.

    Returns fetch attempts for data sources with timing and status.
    """
    from spine.ops.requests import ListSourceFetchesRequest
    from spine.ops.sources import list_source_fetches as _list

    request = ListSourceFetchesRequest(
        source_id=source_id,
        source_name=source_name,
        status=status,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }


# ------------------------------------------------------------------ #
# Cache Endpoints
# ------------------------------------------------------------------ #


@router.get("/cache", response_model=PagedResponse[SourceCacheSchema])
def list_source_cache(
    ctx: OpContext,
    source_id: str | None = Query(None, description="Filter by source ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List source cache entries.

    Returns cached source data for deduplication and change detection.
    """
    from spine.ops.sources import list_source_cache as _list

    result = _list(ctx, source_id=source_id, limit=limit, offset=offset)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }


@router.post("/{source_id}/cache/invalidate")
def invalidate_source_cache(
    ctx: OpContext,
    source_id: str = Path(..., description="Source ID"),
):
    """Invalidate source cache.

    Removes all cached data for a source, forcing a fresh fetch.
    """
    from spine.ops.sources import invalidate_source_cache as _invalidate

    result = _invalidate(ctx, source_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


# ------------------------------------------------------------------ #
# Database Connections Endpoints
# ------------------------------------------------------------------ #


@router.get("/connections", response_model=PagedResponse[DatabaseConnectionSchema])
def list_database_connections(
    ctx: OpContext,
    dialect: str | None = Query(None, description="Filter by dialect"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List registered database connections.

    Returns external database connections configured for data sourcing.
    """
    from spine.ops.requests import ListDatabaseConnectionsRequest
    from spine.ops.sources import list_database_connections as _list

    request = ListDatabaseConnectionsRequest(
        dialect=dialect,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }


@router.post("/connections", status_code=201)
def register_database_connection(
    ctx: OpContext,
    body: DatabaseConnectionCreateRequest,
):
    """Register a new database connection.

    Configures a connection to an external database for data sourcing.
    """
    from spine.ops.requests import CreateDatabaseConnectionRequest
    from spine.ops.sources import register_database_connection as _register

    request = CreateDatabaseConnectionRequest(
        name=body.name,
        dialect=body.dialect,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password_ref=body.password_ref,
        pool_size=body.pool_size,
        max_overflow=body.max_overflow,
        pool_timeout=body.pool_timeout,
        enabled=body.enabled,
    )
    result = _register(ctx, request)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


@router.delete("/connections/{connection_id}")
def delete_database_connection(
    ctx: OpContext,
    connection_id: str = Path(..., description="Connection ID"),
):
    """Delete a database connection."""
    from spine.ops.sources import delete_database_connection as _delete

    result = _delete(ctx, connection_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))


@router.post("/connections/{connection_id}/test")
def test_database_connection(
    ctx: OpContext,
    connection_id: str = Path(..., description="Connection ID"),
):
    """Test a database connection.

    Attempts to connect to the database and returns status.
    """
    from spine.ops.sources import test_database_connection as _test

    result = _test(ctx, connection_id)

    if not result.success:
        return _handle_error(result)

    return SuccessResponse(data=_dc(result.data))
