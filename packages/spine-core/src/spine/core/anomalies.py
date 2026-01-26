"""
Anomaly recording for pipeline and workflow failures.

AnomalyRecorder provides structured error/warning tracking in core_anomalies table.

SCHEMA:
- Uses shared `core_anomalies` table (defined in spine.core.schema)
- Columns: domain, partition_key, stage, severity, category, message,
           detected_at, metadata, resolved_at
- Anomalies are NEVER deleted - they form an audit trail

SEVERITY LEVELS:
- DEBUG: Diagnostic information
- INFO: Notable events (not problems)
- WARN: Warning conditions that may need attention
- ERROR: Error conditions (step/pipeline failures)
- CRITICAL: Severe errors requiring immediate attention

CATEGORIES:
- QUALITY_GATE: Data quality threshold not met
- NETWORK: Network/connectivity issues
- DATA_QUALITY: Data validation failures
- STEP_FAILURE: Individual step failures
- WORKFLOW_FAILURE: Entire workflow failures
- CONFIGURATION: Configuration errors
- SOURCE_ERROR: Source data issues
- TIMEOUT: Operation timeouts
- RESOURCE: Resource exhaustion

SYNC-ONLY: All methods are synchronous.
"""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from .schema import CORE_TABLES


class Connection(Protocol):
    """Minimal SYNC DB connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...
    def commit(self) -> None: ...


class Severity(str, Enum):
    """Anomaly severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AnomalyCategory(str, Enum):
    """Anomaly categories for classification."""
    QUALITY_GATE = "QUALITY_GATE"
    NETWORK = "NETWORK"
    DATA_QUALITY = "DATA_QUALITY"
    STEP_FAILURE = "STEP_FAILURE"
    WORKFLOW_FAILURE = "WORKFLOW_FAILURE"
    CONFIGURATION = "CONFIGURATION"
    SOURCE_ERROR = "SOURCE_ERROR"
    TIMEOUT = "TIMEOUT"
    RESOURCE = "RESOURCE"
    UNKNOWN = "UNKNOWN"


class AnomalyRecorder:
    """
    Record anomalies to core_anomalies table.

    Anomalies are issues that should be tracked but don't necessarily
    stop processing. They provide:
    - Audit trail of problems
    - Alerting on patterns
    - Quality metrics over time

    Example:
        recorder = AnomalyRecorder(conn, domain="finra.otc_transparency")

        # Record an error
        anomaly_id = recorder.record(
            stage="ingest",
            partition_key={"week_ending": "2025-12-26"},
            severity=Severity.ERROR,
            category=AnomalyCategory.QUALITY_GATE,
            message="Null rate 35% exceeds threshold 25%",
            metadata={"null_rate": 0.35, "threshold": 0.25},
        )

        # Later, resolve it
        recorder.resolve(anomaly_id)

        # Query unresolved anomalies
        open_anomalies = recorder.list_unresolved(limit=10)
    """

    def __init__(self, conn: Connection, domain: str):
        """
        Initialize AnomalyRecorder.

        Args:
            conn: Database connection (sync protocol)
            domain: Domain name (e.g., "finra.otc_transparency")
        """
        self.conn = conn
        self.domain = domain
        self.table = CORE_TABLES["anomalies"]

    def _key_json(self, key: dict[str, Any] | str) -> str:
        """Serialize partition key to JSON."""
        if isinstance(key, str):
            return key
        return json.dumps(key, sort_keys=True, default=str)

    def record(
        self,
        stage: str,
        partition_key: dict[str, Any] | str,
        severity: Severity | str,
        category: AnomalyCategory | str,
        message: str,
        *,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record an anomaly.

        Args:
            stage: Stage/step where anomaly occurred
            partition_key: Partition key (dict or JSON string)
            severity: Severity level (DEBUG, INFO, WARN, ERROR, CRITICAL)
            category: Category for classification
            message: Human-readable description
            execution_id: Optional execution ID for correlation
            metadata: Additional structured data

        Returns:
            anomaly_id: Unique identifier for the recorded anomaly
        """
        anomaly_id = str(uuid.uuid4())
        detected_at = datetime.now(timezone.utc).isoformat()
        partition_key_str = self._key_json(partition_key)

        # Convert enums to strings if needed
        severity_str = severity.value if isinstance(severity, Severity) else severity
        category_str = category.value if isinstance(category, AnomalyCategory) else category

        # Include execution_id in metadata if provided
        full_metadata = metadata.copy() if metadata else {}
        if execution_id:
            full_metadata["execution_id"] = execution_id
        metadata_json = json.dumps(full_metadata) if full_metadata else None

        self.conn.execute(
            f"""
            INSERT INTO {self.table} (
                id, domain, stage, partition_key,
                severity, category, message, detected_at, metadata_json, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                anomaly_id,
                self.domain,
                stage,
                partition_key_str,
                severity_str,
                category_str,
                message,
                detected_at,
                metadata_json,
            ),
        )
        self.conn.commit()

        return anomaly_id

    def resolve(self, anomaly_id: str, resolution_note: str | None = None) -> None:
        """
        Mark an anomaly as resolved.

        Args:
            anomaly_id: The anomaly to resolve
            resolution_note: Optional note about the resolution
        """
        resolved_at = datetime.now(timezone.utc).isoformat()

        if resolution_note:
            # Update metadata with resolution note
            self.conn.execute(
                f"""
                UPDATE {self.table}
                SET resolved_at = ?,
                    metadata_json = json_set(
                        COALESCE(metadata_json, '{{}}'),
                        '$.resolution_note', ?
                    )
                WHERE id = ?
                """,
                (resolved_at, resolution_note, anomaly_id),
            )
        else:
            self.conn.execute(
                f"""
                UPDATE {self.table} SET resolved_at = ?
                WHERE id = ?
                """,
                (resolved_at, anomaly_id),
            )

        self.conn.commit()

    def list_unresolved(
        self,
        *,
        severity: Severity | str | None = None,
        category: AnomalyCategory | str | None = None,
        stage: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List unresolved anomalies.

        Args:
            severity: Filter by severity level
            category: Filter by category
            stage: Filter by stage
            limit: Maximum number to return

        Returns:
            List of anomaly records as dicts
        """
        query = f"""
            SELECT id, domain, stage, partition_key, severity, category,
                   message, detected_at, metadata_json, resolved_at
            FROM {self.table}
            WHERE domain = ? AND resolved_at IS NULL
        """
        params: list[Any] = [self.domain]

        if severity:
            sev_str = severity.value if isinstance(severity, Severity) else severity
            query += " AND severity = ?"
            params.append(sev_str)

        if category:
            cat_str = category.value if isinstance(category, AnomalyCategory) else category
            query += " AND category = ?"
            params.append(cat_str)

        if stage:
            query += " AND stage = ?"
            params.append(stage)

        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, tuple(params))
        rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "domain": row[1],
                "stage": row[2],
                "partition_key": row[3],
                "severity": row[4],
                "category": row[5],
                "message": row[6],
                "detected_at": row[7],
                "metadata": json.loads(row[8]) if row[8] else {},
                "resolved_at": row[9],
            }
            for row in rows
        ]

    def count_by_severity(self, since_hours: int = 24) -> dict[str, int]:
        """
        Count anomalies by severity in the given time window.

        Args:
            since_hours: Look back this many hours

        Returns:
            Dict mapping severity to count
        """
        cursor = self.conn.execute(
            f"""
            SELECT severity, COUNT(*) as cnt
            FROM {self.table}
            WHERE domain = ?
              AND detected_at > datetime('now', ? || ' hours')
            GROUP BY severity
            """,
            (self.domain, f"-{since_hours}"),
        )

        return {row[0]: row[1] for row in cursor.fetchall()}

    def has_recent_critical(self, since_hours: int = 1) -> bool:
        """
        Check if there are recent CRITICAL anomalies.

        Args:
            since_hours: Look back this many hours

        Returns:
            True if any unresolved CRITICAL anomalies exist
        """
        cursor = self.conn.execute(
            f"""
            SELECT 1 FROM {self.table}
            WHERE domain = ?
              AND severity = 'CRITICAL'
              AND resolved_at IS NULL
              AND detected_at > datetime('now', ? || ' hours')
            LIMIT 1
            """,
            (self.domain, f"-{since_hours}"),
        )

        return cursor.fetchone() is not None


# Convenience aliases
def create_recorder(conn: Connection, domain: str) -> AnomalyRecorder:
    """Create an AnomalyRecorder for a domain."""
    return AnomalyRecorder(conn, domain)
