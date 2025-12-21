"""
Database router — init, purge, health, table counts, config, and management.

POST /database/init
POST /database/purge
GET  /database/health
GET  /database/tables
GET  /database/config
GET  /database/schema
POST /database/query
POST /database/vacuum
POST /database/backup

Manifesto:
    Database introspection endpoints let operators check table
    counts, run integrity checks, and trigger backups through
    the API rather than direct SQL access.

Tags:
    spine-core, api, database, admin, introspection, backup

Doc-Types:
    api-reference
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from spine.api.deps import OpContext, get_settings
from spine.api.schemas.common import SuccessResponse
from spine.api.schemas.domains import (
    DatabaseHealthSchema,
    DatabaseInitSchema,
    PurgeResultSchema,
    TableCountSchema,
)
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/database")


# ── Additional Schemas ───────────────────────────────────────────────


class DatabaseConfigResponse(BaseModel):
    """Current database configuration (no secrets)."""
    backend: str = Field(description="sqlite | postgresql | timescaledb")
    url_masked: str = Field(description="Connection URL with password masked")
    data_dir: str = Field(description="Data directory path")
    is_persistent: bool = Field(description="True if data survives restart")
    file_path: str | None = Field(None, description="For file-based SQLite, the resolved path")
    file_size_mb: float | None = Field(None, description="DB file size in MB (SQLite only)")
    tier: str = Field(description="minimal | standard | full")
    env_file_hint: str = Field(description="Which .env tier file is in use")


class TableSchemaColumn(BaseModel):
    """Column in a table schema."""
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    default: str | None = None


class TableSchema(BaseModel):
    """Schema of a single table."""
    table_name: str
    columns: list[TableSchemaColumn]
    row_count: int = 0
    indexes: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """Read-only SQL query for inspection."""
    sql: str = Field(..., description="SELECT query to execute (read-only)")
    limit: int = Field(100, ge=1, le=1000, description="Max rows to return")


class QueryResponse(BaseModel):
    """Result of a read-only query."""
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float


class VacuumResponse(BaseModel):
    """Result of a VACUUM operation."""
    success: bool
    size_before_mb: float | None = None
    size_after_mb: float | None = None
    space_reclaimed_mb: float | None = None
    message: str = ""


class BackupResponse(BaseModel):
    """Result of a database backup."""
    success: bool
    backup_path: str | None = None
    size_mb: float | None = None
    message: str = ""


@router.post("/init", response_model=SuccessResponse[DatabaseInitSchema])
def init_database(ctx: OpContext, dry_run: bool = Query(False)):
    """Initialise database schema (create tables)."""
    from spine.ops.database import initialize_database
    from spine.ops.requests import DatabaseInitRequest

    ctx.dry_run = dry_run
    request = DatabaseInitRequest()
    result = initialize_database(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=DatabaseInitSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.post("/purge", response_model=SuccessResponse[PurgeResultSchema])
def purge_data(
    ctx: OpContext,
    older_than_days: int = Query(90, ge=1, description="Delete data older than N days"),
    dry_run: bool = Query(False, description="Preview only, do not delete"),
):
    """Purge old execution data.

    Removes execution records older than the specified threshold.
    Use for data retention compliance and storage management.

    Args:
        ctx: Operation context with database connection.
        older_than_days: Delete records older than this many days (default 90).
        dry_run: If True, returns what would be deleted without making changes.

    Returns:
        SuccessResponse containing PurgeResultSchema with deletion counts.

    Example:
        POST /api/v1/database/purge?older_than_days=30&dry_run=true

        Response:
        {
            "data": {
                "rows_deleted": 1500,
                "tables_purged": ["core_executions", "core_events"],
                "dry_run": true
            }
        }
    """
    from spine.ops.database import purge_old_data
    from spine.ops.requests import PurgeRequest

    ctx.dry_run = dry_run
    request = PurgeRequest(older_than_days=older_than_days)
    result = purge_old_data(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=PurgeResultSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/health", response_model=SuccessResponse[DatabaseHealthSchema])
def database_health(ctx: OpContext):
    """Check database connectivity and stats.

    Returns connection status, backend type, and latency metrics.
    Use for health dashboards and monitoring alerts.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing DatabaseHealthSchema.

    Example:
        GET /api/v1/database/health

        Response:
        {
            "data": {
                "connected": true,
                "backend": "postgresql",
                "table_count": 8,
                "latency_ms": 2.5
            }
        }
    """
    from spine.ops.database import check_database_health

    result = check_database_health(ctx)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=DatabaseHealthSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/tables", response_model=SuccessResponse[list[TableCountSchema]])
def table_counts(ctx: OpContext):
    """Get row counts for all managed tables.

    Returns current row counts for each spine-core database table.
    Useful for capacity planning and monitoring data growth.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing list of TableCountSchema items.

    Example:
        GET /api/v1/database/tables

        Response:
        {
            "data": [
                {"table": "core_executions", "count": 15420},
                {"table": "core_events", "count": 89650},
                {"table": "core_schedules", "count": 12}
            ]
        }
    """
    from spine.ops.database import get_table_counts

    result = get_table_counts(ctx)
    if not result.success:
        return _handle_error(result)
    items = [TableCountSchema(**_dc(tc)) for tc in (result.data or [])]
    return SuccessResponse(
        data=items,
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


# ── New management endpoints ─────────────────────────────────────────


def _mask_url(url: str) -> str:
    """Mask password in a database URL for safe display."""
    if "://" not in url:
        return url
    # postgresql://user:password@host:port/db → postgresql://user:***@host:port/db
    try:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{scheme}://{user}:***@{host_part}"
        return url
    except Exception:
        return url.split("://")[0] + "://***"


def _get_sqlite_file_path(settings: Any) -> str | None:
    """Resolve the SQLite file path from settings."""
    url = settings.database_url
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
    elif not url.startswith(("postgresql", "postgres")):
        path = url
    else:
        return None
    p = Path(path)
    if not p.is_absolute() and settings.data_dir:
        p = Path(settings.data_dir).expanduser() / path
    return str(p.resolve()) if p.exists() else str(p)


def _get_file_size_mb(path: str | None) -> float | None:
    """Get file size in MB, or None if not a file."""
    if path and Path(path).exists():
        return round(Path(path).stat().st_size / (1024 * 1024), 3)
    return None


def _detect_tier() -> tuple[str, str]:
    """Detect which tier/env-file is active."""
    tier = os.environ.get("SPINE_TIER", "")
    if tier:
        return tier, f".env.{tier}"
    url = os.environ.get("SPINE_DATABASE_URL", "")
    if "timescaledb" in url or "timescale" in url.lower():
        return "full", ".env.full"
    if url.startswith(("postgresql://", "postgres://")):
        return "standard", ".env.standard"
    return "minimal", ".env.minimal"


@router.get("/config", response_model=SuccessResponse[DatabaseConfigResponse])
def database_config():
    """Get current database configuration (safe — passwords masked).

    Returns the active backend type, masked connection URL, data directory,
    persistence info, and detected tier. Use this to display connection
    status in the frontend database manager.

    Example:
        GET /api/v1/database/config

        Response:
        {
            "data": {
                "backend": "sqlite",
                "url_masked": "sqlite:///spine_core.db",
                "data_dir": "~/.spine",
                "is_persistent": true,
                "file_path": "/home/user/.spine/spine_core.db",
                "file_size_mb": 0.125,
                "tier": "minimal",
                "env_file_hint": ".env.minimal"
            }
        }
    """
    settings = get_settings()
    url = settings.database_url
    is_pg = url.startswith(("postgresql://", "postgres://"))
    tier, env_hint = _detect_tier()
    file_path = _get_sqlite_file_path(settings) if not is_pg else None

    return SuccessResponse(data=DatabaseConfigResponse(
        backend="postgresql" if is_pg else "sqlite",
        url_masked=_mask_url(url),
        data_dir=settings.data_dir,
        is_persistent=url != ":memory:" and url != "memory",
        file_path=file_path,
        file_size_mb=_get_file_size_mb(file_path),
        tier=tier,
        env_file_hint=env_hint,
    ))


@router.get("/schema", response_model=SuccessResponse[list[TableSchema]])
def database_schema(ctx: OpContext):
    """Inspect full database schema — tables, columns, indexes, row counts.

    Returns detailed schema information for every table in the database.
    Supports both SQLite and PostgreSQL backends.

    Example:
        GET /api/v1/database/schema

        Response:
        {
            "data": [
                {
                    "table_name": "core_executions",
                    "columns": [
                        {"name": "run_id", "type": "TEXT", "nullable": false, "primary_key": true}
                    ],
                    "row_count": 150,
                    "indexes": ["idx_executions_status"]
                }
            ]
        }
    """
    t0 = time.monotonic()
    conn = ctx.conn
    tables: list[TableSchema] = []

    try:
        # Try SQLite introspection first
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [row[0] if isinstance(row, tuple) else row["name"] for row in cursor.fetchall()]

        for tname in table_names:
            # Column info
            cols_cursor = conn.execute(f"PRAGMA table_info('{tname}')")
            columns = []
            for col in cols_cursor.fetchall():
                if isinstance(col, tuple):
                    columns.append(TableSchemaColumn(
                        name=col[1], type=col[2] or "TEXT",
                        nullable=not bool(col[3]), primary_key=bool(col[5]),
                        default=str(col[4]) if col[4] is not None else None,
                    ))
                else:
                    columns.append(TableSchemaColumn(
                        name=col["name"], type=col["type"] or "TEXT",
                        nullable=not bool(col["notnull"]), primary_key=bool(col["pk"]),
                        default=str(col["dflt_value"]) if col["dflt_value"] is not None else None,
                    ))

            # Row count
            try:
                rc = conn.execute(f"SELECT COUNT(*) FROM '{tname}'")
                row_count = rc.fetchone()[0] if rc else 0
            except Exception:
                row_count = 0

            # Indexes
            idx_cursor = conn.execute(f"PRAGMA index_list('{tname}')")
            indexes = []
            for idx in idx_cursor.fetchall():
                idx_name = idx[1] if isinstance(idx, tuple) else idx["name"]
                indexes.append(idx_name)

            tables.append(TableSchema(
                table_name=tname, columns=columns,
                row_count=row_count, indexes=indexes,
            ))

    except Exception:
        # Fallback for PostgreSQL
        try:
            cursor = conn.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            table_names = [row[0] if isinstance(row, tuple) else row["table_name"] for row in cursor.fetchall()]

            for tname in table_names:
                cols_cursor = conn.execute(f"""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = '{tname}' AND table_schema = 'public'
                    ORDER BY ordinal_position
                """)
                columns = []
                for col in cols_cursor.fetchall():
                    c = col if isinstance(col, tuple) else (col["column_name"], col["data_type"], col["is_nullable"], col["column_default"])
                    columns.append(TableSchemaColumn(
                        name=c[0], type=c[1],
                        nullable=c[2] == "YES",
                        default=str(c[3]) if c[3] else None,
                    ))

                try:
                    rc = conn.execute(f"SELECT COUNT(*) FROM \"{tname}\"")
                    row_count = rc.fetchone()[0] if rc else 0
                except Exception:
                    row_count = 0

                tables.append(TableSchema(
                    table_name=tname, columns=columns, row_count=row_count,
                ))

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Schema introspection failed: {exc}") from exc

    elapsed = round((time.monotonic() - t0) * 1000, 2)
    return SuccessResponse(data=tables, elapsed_ms=elapsed)


@router.post("/query", response_model=SuccessResponse[QueryResponse])
def run_query(ctx: OpContext, body: QueryRequest):
    """Execute a read-only SQL query (SELECT only).

    This is a developer/admin tool for inspecting data directly.
    Only SELECT statements are allowed — any mutation attempt is rejected.

    Args:
        ctx: Operation context.
        body: The SQL query and limit.

    Returns:
        Query results with column names and rows.

    Raises:
        400: Non-SELECT query attempted.

    Example:
        POST /api/v1/database/query
        {"sql": "SELECT * FROM core_executions WHERE status = 'failed' LIMIT 10"}
    """
    sql = body.sql.strip()

    # Security: only allow SELECT
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

    # Reject dangerous patterns
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC"]
    upper_sql = sql.upper()
    for keyword in dangerous:
        # Check for keyword as a separate word (not inside a string)
        if f" {keyword} " in f" {upper_sql} ":
            raise HTTPException(status_code=400, detail=f"Query contains forbidden keyword: {keyword}")

    t0 = time.monotonic()
    try:
        # Apply limit
        if "LIMIT" not in upper_sql:
            sql = f"{sql} LIMIT {body.limit}"

        cursor = ctx.conn.execute(sql)
        rows_raw = cursor.fetchall()

        # Extract column names
        if hasattr(cursor, "description") and cursor.description:
            columns = [desc[0] for desc in cursor.description]
        elif rows_raw and hasattr(rows_raw[0], "keys"):
            columns = list(rows_raw[0].keys())
        else:
            columns = [f"col_{i}" for i in range(len(rows_raw[0]) if rows_raw else 0)]

        # Convert to lists
        rows = []
        for row in rows_raw:
            if isinstance(row, (tuple, list)):
                rows.append(list(row))
            elif hasattr(row, "keys"):
                rows.append([row[k] for k in columns])
            else:
                rows.append(list(row))

        elapsed = round((time.monotonic() - t0) * 1000, 2)
        return SuccessResponse(data=QueryResponse(
            columns=columns,
            rows=rows[:body.limit],
            row_count=len(rows),
            truncated=len(rows_raw) > body.limit,
            elapsed_ms=elapsed,
        ))

    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Query failed: {exc}") from exc


@router.post("/vacuum", response_model=SuccessResponse[VacuumResponse])
def vacuum_database(ctx: OpContext):
    """Run VACUUM on SQLite database to reclaim space.

    Only works on SQLite backends. For PostgreSQL, use VACUUM ANALYZE
    via psql directly.

    Example:
        POST /api/v1/database/vacuum
    """
    settings = get_settings()
    if settings.database_url.startswith(("postgresql://", "postgres://")):
        return SuccessResponse(data=VacuumResponse(
            success=False,
            message="VACUUM not available via API for PostgreSQL. Use psql: VACUUM ANALYZE;",
        ))

    file_path = _get_sqlite_file_path(settings)
    size_before = _get_file_size_mb(file_path)

    try:
        # SQLite VACUUM requires autocommit mode
        raw = getattr(ctx.conn, "raw", None)
        if raw:
            raw.execute("VACUUM")
        else:
            ctx.conn.execute("VACUUM")
            ctx.conn.commit()

        size_after = _get_file_size_mb(file_path)
        reclaimed = round(size_before - size_after, 3) if size_before and size_after else None

        return SuccessResponse(data=VacuumResponse(
            success=True,
            size_before_mb=size_before,
            size_after_mb=size_after,
            space_reclaimed_mb=reclaimed,
            message=f"VACUUM complete. Reclaimed {reclaimed or 0:.3f} MB.",
        ))

    except Exception as exc:
        return SuccessResponse(data=VacuumResponse(
            success=False,
            message=f"VACUUM failed: {exc}",
        ))


@router.post("/backup", response_model=SuccessResponse[BackupResponse])
def backup_database(ctx: OpContext):
    """Create a backup of the SQLite database file.

    Creates a timestamped copy of the database file. Only works for
    file-based SQLite databases.

    Example:
        POST /api/v1/database/backup
    """
    settings = get_settings()
    if settings.database_url.startswith(("postgresql://", "postgres://")):
        return SuccessResponse(data=BackupResponse(
            success=False,
            message="Use pg_dump for PostgreSQL backups: pg_dump -h localhost -p 10432 -U spine spine > backup.sql",
        ))

    file_path = _get_sqlite_file_path(settings)
    if not file_path or not Path(file_path).exists():
        return SuccessResponse(data=BackupResponse(
            success=False,
            message="No database file found (in-memory database cannot be backed up).",
        ))

    try:
        import datetime
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.backup_{ts}"
        shutil.copy2(file_path, backup_path)
        size = _get_file_size_mb(backup_path)

        return SuccessResponse(data=BackupResponse(
            success=True,
            backup_path=backup_path,
            size_mb=size,
            message=f"Backup created: {Path(backup_path).name}",
        ))

    except Exception as exc:
        return SuccessResponse(data=BackupResponse(
            success=False,
            message=f"Backup failed: {exc}",
        ))
