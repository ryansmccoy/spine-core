"""Data retention and purge utilities.

Provides functions to purge old records from core tables based on
configurable retention periods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from spine.core.dialect import Dialect, SQLiteDialect
from spine.core.protocols import Connection

logger = logging.getLogger(__name__)


@dataclass
class PurgeResult:
    """Result of a purge operation."""

    table: str
    deleted: int
    cutoff: str


@dataclass
class RetentionReport:
    """Aggregated results of a full retention run."""

    results: list[PurgeResult] = field(default_factory=list)
    total_deleted: int = 0
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# Table configuration: (table_name, timestamp_column, extra_condition)
_PURGEABLE_TABLES: list[tuple[str, str, str | None]] = [
    ("core_executions", "created_at", None),
    ("core_rejects", "created_at", None),
    ("core_quality", "created_at", None),
    ("core_anomalies", "created_at", None),
    ("core_work_items", "completed_at", "state = 'COMPLETE'"),
]


def compute_cutoff(days: int) -> str:
    """Compute ISO 8601 cutoff timestamp for retention.

    Parameters
    ----------
    days
        Number of days to retain. Records older than this are eligible
        for purging.

    Returns
    -------
    str
        ISO 8601 formatted cutoff timestamp.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%S")


def purge_table(
    conn: Connection,
    table: str,
    timestamp_column: str,
    cutoff: str,
    extra_condition: str | None = None,
    dialect: Dialect = SQLiteDialect(),
) -> PurgeResult:
    """Purge records older than cutoff from a single table.

    Parameters
    ----------
    conn
        Database connection.
    table
        Table name to purge.
    timestamp_column
        Column containing the timestamp to compare.
    cutoff
        ISO 8601 timestamp. Records older than this are deleted.
    extra_condition
        Optional additional WHERE clause (e.g., "state = 'COMPLETE'").

    Returns
    -------
    PurgeResult
        Result with table name, deleted count, and cutoff used.
    """
    where = f"{timestamp_column} < {dialect.placeholder(0)}"
    if extra_condition:
        where = f"{where} AND {extra_condition}"

    sql = f"DELETE FROM {table} WHERE {where}"  # noqa: S608
    cursor = conn.execute(sql, (cutoff,))
    deleted = cursor.rowcount
    conn.commit()

    logger.info(
        "retention.purged",
        extra={"table": table, "deleted": deleted, "cutoff": cutoff},
    )
    return PurgeResult(table=table, deleted=deleted, cutoff=cutoff)


def purge_executions(conn: Connection, days: int = 90) -> PurgeResult:
    """Purge old execution records.

    Parameters
    ----------
    conn
        Database connection.
    days
        Retention period in days. Default 90.
    """
    return purge_table(conn, "core_executions", "created_at", compute_cutoff(days))


def purge_rejects(conn: Connection, days: int = 30) -> PurgeResult:
    """Purge old reject records.

    Parameters
    ----------
    conn
        Database connection.
    days
        Retention period in days. Default 30.
    """
    return purge_table(conn, "core_rejects", "created_at", compute_cutoff(days))


def purge_quality(conn: Connection, days: int = 90) -> PurgeResult:
    """Purge old quality check records.

    Parameters
    ----------
    conn
        Database connection.
    days
        Retention period in days. Default 90.
    """
    return purge_table(conn, "core_quality", "created_at", compute_cutoff(days))


def purge_anomalies(conn: Connection, days: int = 180) -> PurgeResult:
    """Purge old anomaly records.

    Parameters
    ----------
    conn
        Database connection.
    days
        Retention period in days. Default 180.
    """
    return purge_table(conn, "core_anomalies", "created_at", compute_cutoff(days))


def purge_work_items(conn: Connection, days: int = 30) -> PurgeResult:
    """Purge completed work items older than retention period.

    Only purges items with state='COMPLETE'.

    Parameters
    ----------
    conn
        Database connection.
    days
        Retention period in days. Default 30.
    """
    return purge_table(
        conn,
        "core_work_items",
        "completed_at",
        compute_cutoff(days),
        extra_condition="state = 'COMPLETE'",
    )


@dataclass
class RetentionConfig:
    """Configuration for retention periods (in days)."""

    executions: int = 90
    rejects: int = 30
    quality: int = 90
    anomalies: int = 180
    work_items: int = 30


def purge_all(
    conn: Connection,
    config: RetentionConfig | None = None,
) -> RetentionReport:
    """Run purge on all purgeable tables with configured retention.

    Parameters
    ----------
    conn
        Database connection.
    config
        Retention configuration. Uses defaults if not provided.

    Returns
    -------
    RetentionReport
        Aggregated results of all purge operations.
    """
    if config is None:
        config = RetentionConfig()

    report = RetentionReport()

    purge_ops = [
        ("core_executions", "created_at", None, config.executions),
        ("core_rejects", "created_at", None, config.rejects),
        ("core_quality", "created_at", None, config.quality),
        ("core_anomalies", "created_at", None, config.anomalies),
        ("core_work_items", "completed_at", "state = 'COMPLETE'", config.work_items),
    ]

    for table, ts_col, extra_cond, days in purge_ops:
        try:
            cutoff = compute_cutoff(days)
            result = purge_table(conn, table, ts_col, cutoff, extra_cond)
            report.results.append(result)
            report.total_deleted += result.deleted
        except Exception as exc:
            report.errors[table] = str(exc)
            logger.error(
                "retention.error",
                extra={"table": table, "error": str(exc)},
            )

    return report


def get_table_counts(conn: Connection) -> dict[str, int]:
    """Get row counts for all purgeable tables.

    Useful for monitoring before/after purge operations.

    Parameters
    ----------
    conn
        Database connection.

    Returns
    -------
    dict
        Mapping of table name to row count.
    """
    counts = {}
    for table, _, _ in _PURGEABLE_TABLES:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            counts[table] = cursor.fetchone()[0]
        except Exception:
            counts[table] = -1  # Table doesn't exist
    return counts
