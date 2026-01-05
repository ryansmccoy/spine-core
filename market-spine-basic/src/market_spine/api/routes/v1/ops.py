"""
Operations and monitoring endpoints.

Provides endpoints for storage statistics, captures, and system operations.
"""

from pydantic import BaseModel
from fastapi import APIRouter

from market_spine.db import get_connection

router = APIRouter(prefix="/ops", tags=["operations"])


# =============================================================================
# Response Models
# =============================================================================


class TableStatsResponse(BaseModel):
    """Statistics for a single table."""

    name: str
    row_count: int
    size_bytes: int | None = None


class StorageStatsResponse(BaseModel):
    """Storage statistics response."""

    database_path: str
    database_size_bytes: int
    tables: list[TableStatsResponse]
    total_rows: int


class CaptureInfo(BaseModel):
    """Information about a single data capture."""

    capture_id: str
    captured_at: str | None
    tier: str
    week_ending: str
    row_count: int


class CapturesListResponse(BaseModel):
    """Response listing all captures."""

    captures: list[CaptureInfo]
    count: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/storage", response_model=StorageStatsResponse)
async def get_storage_stats() -> StorageStatsResponse:
    """
    Get current storage statistics.

    Returns database size, table row counts, and storage metrics.
    Useful for monitoring disk usage and planning retention.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get database file path and size
    cursor.execute("PRAGMA database_list")
    db_info = cursor.fetchone()
    db_path = db_info[2] if db_info else ":memory:"

    # Get database file size
    import os

    try:
        db_size = os.path.getsize(db_path) if db_path != ":memory:" else 0
    except OSError:
        db_size = 0

    # Get table statistics
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    table_names = [row[0] for row in cursor.fetchall()]

    tables = []
    total_rows = 0

    for table_name in table_names:
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
        row_count = cursor.fetchone()[0]
        total_rows += row_count

        tables.append(
            TableStatsResponse(
                name=table_name,
                row_count=row_count,
                size_bytes=None,  # SQLite doesn't provide per-table sizes easily
            )
        )

    return StorageStatsResponse(
        database_path=db_path,
        database_size_bytes=db_size,
        tables=tables,
        total_rows=total_rows,
    )


@router.get("/captures", response_model=CapturesListResponse)
async def list_captures() -> CapturesListResponse:
    """
    List all data captures in the system.

    Returns capture IDs with their associated metadata including
    the tier, week ending date, capture timestamp, and row counts.
    Useful for tracking data lineage and restatement history.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Query unique capture_ids from the normalized table with aggregated info
    try:
        cursor.execute(
            """
            SELECT 
                capture_id,
                MIN(captured_at) as captured_at,
                tier,
                week_ending,
                COUNT(*) as row_count
            FROM finra_otc_transparency_normalized
            GROUP BY capture_id, tier, week_ending
            ORDER BY week_ending DESC, tier, captured_at DESC
            """
        )
        rows = cursor.fetchall()
    except Exception:
        # Table doesn't exist yet - return empty list
        return CapturesListResponse(captures=[], count=0)

    captures = []
    for row in rows:
        # Handle both dict-like and tuple-like rows
        if hasattr(row, "__getitem__") and not isinstance(row, tuple):
            capture_id = row["capture_id"]
            captured_at = row["captured_at"]
            tier = row["tier"]
            week_ending = row["week_ending"]
            row_count = row["row_count"]
        else:
            capture_id, captured_at, tier, week_ending, row_count = row

        captures.append(
            CaptureInfo(
                capture_id=capture_id,
                captured_at=captured_at,
                tier=tier,
                week_ending=week_ending,
                row_count=row_count,
            )
        )

    return CapturesListResponse(
        captures=captures,
        count=len(captures),
    )
