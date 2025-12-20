"""
Database operations.

Thin wrappers around ``spine.core.schema`` for table creation, health
checks, and data lifecycle management.
"""

from __future__ import annotations

import time
from typing import Any

from spine.core.logging import get_logger

from spine.core.dialect import Dialect, SQLiteDialect

# The CORE_TABLES dict maps logical names to SQL table names.
from spine.core.schema import CORE_TABLES
from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.requests import DatabaseInitRequest, PurgeRequest
from spine.ops.responses import (
    DatabaseHealth,
    DatabaseInitResult,
    PurgeResult,
    TableCount,
)
from spine.ops.result import OperationResult, start_timer

logger = get_logger(__name__)

# Tables that contain timestamped rows eligible for purging.
_PURGEABLE_TABLES: list[tuple[str, str]] = [
    ("core_executions", "created_at"),
    ("core_dead_letters", "created_at"),
    ("core_quality", "created_at"),
    ("core_anomalies", "detected_at"),
    ("core_manifest", "updated_at"),
    ("core_rejects", "created_at"),
]


def initialize_database(
    ctx: OperationContext,
    request: DatabaseInitRequest | None = None,
) -> OperationResult[DatabaseInitResult]:
    """Create all spine-core tables (idempotent).

    Applies all SQL schema files from ``spine.core.schema/*.sql``.
    """
    request = request or DatabaseInitRequest()
    timer = start_timer()

    if ctx.dry_run:
        table_names = _table_names_from_ddl()
        return OperationResult.ok(
            DatabaseInitResult(tables_created=table_names, dry_run=True),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        # Apply all SQL schema files — single source of truth for table
        # definitions.  The SQL files (00_core.sql through 08_temporal.sql)
        # cover all 30 tables.  All use CREATE TABLE IF NOT EXISTS.
        apply_all_schemas(ctx.conn)
        table_names = _table_names_from_ddl()
        return OperationResult.ok(
            DatabaseInitResult(tables_created=table_names),
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to create tables: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def get_table_counts(ctx: OperationContext) -> OperationResult[list[TableCount]]:
    """Return row counts for all spine-core tables."""
    timer = start_timer()
    counts: list[TableCount] = []

    for tbl in _table_names_from_ddl():
        try:
            ctx.conn.execute(f"SELECT COUNT(*) FROM {tbl}")  # noqa: S608
            row = ctx.conn.fetchone()
            counts.append(TableCount(table=tbl, count=row[0] if row else 0))
        except Exception:
            # Table may not exist yet — report count of -1.
            counts.append(TableCount(table=tbl, count=-1))

    return OperationResult.ok(counts, elapsed_ms=timer.elapsed_ms)


def purge_old_data(
    ctx: OperationContext,
    request: PurgeRequest,
    dialect: Dialect = SQLiteDialect(),
) -> OperationResult[PurgeResult]:
    """Delete rows older than *request.older_than_days*."""
    timer = start_timer()

    if ctx.dry_run:
        target_tables = [t for t, _ in _PURGEABLE_TABLES]
        if request.tables:
            target_tables = [t for t in target_tables if t in request.tables]
        return OperationResult.ok(
            PurgeResult(rows_deleted=0, tables_purged=target_tables, dry_run=True),
            elapsed_ms=timer.elapsed_ms,
        )

    total_deleted = 0
    purged: list[str] = []
    warnings: list[str] = []

    for table, ts_col in _PURGEABLE_TABLES:
        if request.tables and table not in request.tables:
            continue
        try:
            interval_expr = dialect.interval(-request.older_than_days, "days")
            ctx.conn.execute(
                f"DELETE FROM {table} WHERE {ts_col} < {interval_expr}",  # noqa: S608
            )
            # SQLite returns rowcount via changes(); abstract conn may not.
            # We count best-effort.
            purged.append(table)
        except Exception as exc:
            warnings.append(f"{table}: {exc}")

    try:
        ctx.conn.commit()
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Commit failed after purge: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )

    return OperationResult.ok(
        PurgeResult(rows_deleted=total_deleted, tables_purged=purged),
        warnings=warnings,
        elapsed_ms=timer.elapsed_ms,
    )


def check_database_health(ctx: OperationContext) -> OperationResult[DatabaseHealth]:
    """Check database connectivity and table status."""
    timer = start_timer()

    try:
        start = time.perf_counter()
        ctx.conn.execute("SELECT 1")
        ctx.conn.fetchone()
        latency = (time.perf_counter() - start) * 1000

        # Count tables that exist
        table_count = 0
        for tbl in _table_names_from_ddl():
            try:
                ctx.conn.execute(f"SELECT 1 FROM {tbl} LIMIT 0")  # noqa: S608
                table_count += 1
            except Exception:
                pass

        # Detect backend
        backend = _detect_backend(ctx.conn)

        return OperationResult.ok(
            DatabaseHealth(
                connected=True,
                backend=backend,
                table_count=table_count,
                latency_ms=round(latency, 2),
            ),
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.ok(
            DatabaseHealth(connected=False, backend="unknown"),
            warnings=[f"Health check error: {exc}"],
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _table_names_from_ddl() -> list[str]:
    """Return the actual SQL table names from :data:`CORE_TABLES`."""
    return sorted(CORE_TABLES.values())


def _detect_backend(conn: Any) -> str:
    """Best-effort backend detection."""
    type_name = type(conn).__module__ + "." + type(conn).__qualname__
    name_lower = type_name.lower()
    if "sqlite" in name_lower:
        return "sqlite"
    if "psycopg" in name_lower or "asyncpg" in name_lower:
        return "postgresql"
    if "ibm_db" in name_lower:
        return "db2"
    if "mysql" in name_lower:
        return "mysql"
    if "oracledb" in name_lower or "cx_oracle" in name_lower:
        return "oracle"

    # Fallback: try database-specific probes
    for probe_sql, backend_name, validator in [
        ("SELECT sqlite_version()", "sqlite", lambda _r: True),
        ("SELECT 1 FROM SYSIBM.SYSDUMMY1", "db2", lambda _r: True),
        (
            "SELECT version()",
            "postgresql",
            lambda r: "postgresql" in str(r[0]).lower(),
        ),
    ]:
        try:
            cursor = conn.execute(probe_sql)
            row = getattr(cursor, "fetchone", lambda: None)()
            if row and validator(row):
                return backend_name
        except Exception:
            pass

    return "unknown"
