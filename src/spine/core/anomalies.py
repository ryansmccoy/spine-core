"""
Anomaly recording for operation and workflow failures.

Provides structured error and warning tracking via the AnomalyRecorder class.
Anomalies are issues that should be tracked for audit, alerting, and debugging
but don't necessarily stop operation execution.

Manifesto:
    Financial operations encounter many issues that aren't fatal:
    - Quality threshold warnings
    - Transient network errors
    - Data format anomalies
    - Step execution failures

    These need to be:
    - **Recorded:** Persistent audit trail in core_anomalies table
    - **Classified:** Severity and category for routing
    - **Resolvable:** Mark anomalies as resolved when addressed
    - **Queryable:** Find open issues for investigation

    Anomalies are NEVER deleted - they form a permanent audit trail.

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Anomaly Recording Flow                    │
        └─────────────────────────────────────────────────────────────┘

        Record Anomaly:
        ┌────────────────────────────────────────────────────────────┐
        │ recorder = AnomalyRecorder(conn, domain="finra.otc")       │
        │                                                            │
        │ anomaly_id = recorder.record(                              │
        │     stage="ingest",                                        │
        │     partition_key={"week_ending": "2025-12-26"},           │
        │     severity=Severity.ERROR,                               │
        │     category=AnomalyCategory.QUALITY_GATE,                 │
        │     message="Null rate 35% exceeds threshold 25%",         │
        │     metadata={"null_rate": 0.35}                           │
        │ )                                                          │
        └────────────────────────────────────────────────────────────┘

        Resolve Later:
        ┌────────────────────────────────────────────────────────────┐
        │ recorder.resolve(anomaly_id, "Fixed in re-run abc123")     │
        └────────────────────────────────────────────────────────────┘

        Storage (core_anomalies):
        ┌────────────────────────────────────────────────────────────┐
        │ id       | severity | category      | message | resolved   │
        │ abc123   | ERROR    | QUALITY_GATE  | "..."   | NULL      │
        │ def456   | WARN     | DATA_QUALITY  | "..."   | 2025-12-27│
        └────────────────────────────────────────────────────────────┘

Features:
    - **Severity levels:** DEBUG, INFO, WARN, ERROR, CRITICAL
    - **Categories:** QUALITY_GATE, NETWORK, DATA_QUALITY, etc.
    - **Resolution tracking:** record() + resolve() workflow
    - **Metadata:** Structured JSON for additional context
    - **Lineage:** execution_id correlation

Examples:
    Record an anomaly:

    >>> recorder = AnomalyRecorder(conn, domain="finra.otc_transparency")
    >>> anomaly_id = recorder.record(
    ...     stage="ingest",
    ...     partition_key={"week_ending": "2025-12-26"},
    ...     severity=Severity.ERROR,
    ...     category=AnomalyCategory.QUALITY_GATE,
    ...     message="Null rate 35% exceeds threshold 25%"
    ... )
    >>> # Later, resolve it
    >>> recorder.resolve(anomaly_id)

Tags:
    anomaly, error-tracking, audit-trail, observability, spine-core,
    alerting, monitoring

Doc-Types:
    - API Reference
    - Observability Guide
    - Audit Trail Documentation

SCHEMA:
- Uses shared `core_anomalies` table (defined in spine.core.schema)
- Columns: domain, partition_key, stage, severity, category, message,
           detected_at, metadata, resolved_at
- Anomalies are NEVER deleted - they form an audit trail

SEVERITY LEVELS:
- DEBUG: Diagnostic information
- INFO: Notable events (not problems)
- WARN: Warning conditions that may need attention
- ERROR: Error conditions (step/operation failures)
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
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .dialect import Dialect, SQLiteDialect
from .protocols import Connection
from .schema import CORE_TABLES


class Severity(str, Enum):
    """
    Anomaly severity levels for classifying issue importance.

    Maps directly to log levels and alert routing rules. Lower levels
    (DEBUG, INFO) are informational; higher levels (WARN, ERROR, CRITICAL)
    indicate problems requiring attention.

    Manifesto:
        Not all anomalies are created equal. A CRITICAL issue that breaks
        production needs immediate attention, while INFO is just notable.
        Severity enables:
        - **Alert routing:** CRITICAL pages on-call, WARN creates tickets
        - **Dashboard filtering:** Focus on what matters
        - **Trend analysis:** Track severity distribution over time

    Architecture:
        ::

            Severity → Alert Routing:
            ┌────────────────────────────────────────────────────┐
            │ DEBUG    → Log only, no alert                      │
            │ INFO     → Log only, metrics collection            │
            │ WARN     → Creates ticket, appears on dashboard    │
            │ ERROR    → Triggers alert, requires resolution     │
            │ CRITICAL → Pages on-call, immediate attention      │
            └────────────────────────────────────────────────────┘

    Attributes:
        DEBUG: Diagnostic information for developers.
        INFO: Notable events that aren't problems.
        WARN: Warning conditions that may need attention.
        ERROR: Error conditions causing step/operation failures.
        CRITICAL: Severe errors requiring immediate attention.

    Examples:
        >>> severity = Severity.ERROR
        >>> severity.value
        'ERROR'
        >>> str(severity) == "ERROR"
        True

    Tags:
        severity, logging, alerting, anomaly, enum
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AnomalyCategory(str, Enum):
    """
    Anomaly categories for classification and routing.

    Categorizes anomalies by their root cause to enable:
    - Targeted alerting (network issues → infra team)
    - Trend analysis (spike in QUALITY_GATE failures)
    - Automated remediation (TIMEOUT → retry)

    Manifesto:
        Categories answer "what type of problem?" while severity answers
        "how bad is it?". Together they enable smart routing and analysis.
        The UNKNOWN category is a catch-all for edge cases that should
        be investigated and properly categorized.

    Architecture:
        ::

            Category → Team Routing:
            ┌────────────────────────────────────────────────────┐
            │ QUALITY_GATE      → Data Quality Team              │
            │ NETWORK           → Infrastructure Team            │
            │ DATA_QUALITY      → Data Engineering Team          │
            │ STEP_FAILURE      → Operation Owners                │
            │ WORKFLOW_FAILURE  → Operation Owners                │
            │ CONFIGURATION     → DevOps Team                    │
            │ SOURCE_ERROR      → Data Source Owners             │
            │ TIMEOUT           → Infrastructure Team            │
            │ RESOURCE          → Infrastructure Team            │
            │ UNKNOWN           → On-Call for Triage             │
            └────────────────────────────────────────────────────┘

    Attributes:
        QUALITY_GATE: Data quality threshold not met.
        NETWORK: Network/connectivity issues.
        DATA_QUALITY: Data validation failures.
        STEP_FAILURE: Individual step failures.
        WORKFLOW_FAILURE: Entire workflow failures.
        CONFIGURATION: Configuration errors.
        SOURCE_ERROR: Source data issues.
        TIMEOUT: Operation timeouts.
        RESOURCE: Resource exhaustion.
        UNKNOWN: Uncategorized anomalies.

    Examples:
        >>> category = AnomalyCategory.QUALITY_GATE
        >>> category.value
        'QUALITY_GATE'

    Tags:
        category, classification, routing, anomaly, enum
    """

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
    Record anomalies to core_anomalies table with severity and categorization.

    Anomalies are issues that should be tracked but don't necessarily
    stop processing. They provide an audit trail, enable alerting on
    patterns, and support quality metrics over time.

    Manifesto:
        Production operations encounter many issues that aren't fatal:
        quality warnings, transient network errors, data format anomalies.
        These need to be recorded for audit, classified for routing, and
        tracked to resolution. AnomalyRecorder is the single entry point
        for all such issues in the Spine ecosystem.

        Key principles:
        - **Immutability:** Anomalies are NEVER deleted (audit trail)
        - **Classification:** Severity + Category enable smart routing
        - **Resolution:** Mark resolved, don't delete
        - **Correlation:** execution_id links to operation runs

    Architecture:
        ::

            ┌────────────────────────────────────────────────────────────┐
            │                    AnomalyRecorder                         │
            ├────────────────────────────────────────────────────────────┤
            │ Properties:                                                 │
            │   conn: Connection      # DB connection (sync)             │
            │   domain: str           # Domain name                       │
            │   table: str            # core_anomalies table              │
            ├────────────────────────────────────────────────────────────┤
            │ Methods:                                                    │
            │   record(...)  → str    # Record anomaly, return ID         │
            │   resolve(id, note?)    # Mark anomaly resolved             │
            │   list_unresolved(...)  # Query open anomalies             │
            └────────────────────────────────────────────────────────────┘

            Record Flow:
            ┌───────────┐     ┌─────────────────┐     ┌──────────────┐
            │ Operation  │────▶│ AnomalyRecorder │────▶│ core_anomalies│
            │ catches   │     │ .record()       │     │ table         │
            │ error     │     │                 │     │               │
            └───────────┘     └─────────────────┘     └──────────────┘

            Resolution Flow:
            ┌───────────┐     ┌─────────────────┐     ┌──────────────┐
            │ Operator  │────▶│ AnomalyRecorder │────▶│ resolved_at  │
            │ fixes     │     │ .resolve(id)    │     │ = now()      │
            │ issue     │     │                 │     │               │
            └───────────┘     └─────────────────┘     └──────────────┘

    Features:
        - **Severity classification:** DEBUG/INFO/WARN/ERROR/CRITICAL
        - **Category classification:** QUALITY_GATE, NETWORK, etc.
        - **Metadata storage:** Structured JSON for additional context
        - **Resolution tracking:** record() → resolve() workflow
        - **Execution correlation:** Link to operation execution IDs
        - **Query support:** list_unresolved() for investigation

    Examples:
        Record an anomaly:

        >>> recorder = AnomalyRecorder(conn, domain="finra.otc_transparency")
        >>> anomaly_id = recorder.record(
        ...     stage="ingest",
        ...     partition_key={"week_ending": "2025-12-26"},
        ...     severity=Severity.ERROR,
        ...     category=AnomalyCategory.QUALITY_GATE,
        ...     message="Null rate 35% exceeds threshold 25%",
        ...     metadata={"null_rate": 0.35, "threshold": 0.25},
        ... )
        >>> # Later, resolve it
        >>> recorder.resolve(anomaly_id, note="Fixed in re-run abc123")

        Query unresolved anomalies:

        >>> open_anomalies = recorder.list_unresolved(limit=10)
        >>> for anomaly in open_anomalies:
        ...     print(f"{anomaly['severity']}: {anomaly['message']}")

    Performance:
        - record(): Single INSERT, O(1)
        - resolve(): Single UPDATE by primary key, O(1)
        - list_unresolved(): Index scan on (domain, resolved_at), O(log n)

    Guardrails:
        - All methods are SYNC (no async)
        - Never deletes data (audit compliance)
        - Commits after each operation
        - Uses parameterized queries (SQL injection safe)

    Context:
        - Domain: Observability, audit trail, error tracking
        - Used By: All Spine operations (Entity, Feed, Market)
        - Storage: Shared core_anomalies table
        - Paired With: QualityRunner for automatic anomaly recording

    Tags:
        anomaly, error-tracking, audit-trail, observability,
        spine-core, alerting, monitoring, sync
    """

    def __init__(self, conn: Connection, domain: str, dialect: Dialect = SQLiteDialect()):
        """
        Initialize AnomalyRecorder.

        Args:
            conn: Database connection (sync protocol)
            domain: Domain name (e.g., "finra.otc_transparency")
            dialect: SQL dialect for portable queries
        """
        self.conn = conn
        self.domain = domain
        self.dialect = dialect
        self.table = CORE_TABLES["anomalies"]

    def _ph(self, count: int) -> str:
        """Generate dialect-specific placeholders."""
        return self.dialect.placeholders(count)

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
            anomaly_id: Unique identifier for the recorded anomaly (integer)
        """
        detected_at = datetime.now(UTC).isoformat()
        partition_key_str = self._key_json(partition_key)

        # Convert enums to strings if needed
        severity_str = severity.value if isinstance(severity, Severity) else severity
        category_str = category.value if isinstance(category, AnomalyCategory) else category

        # Include execution_id in metadata if provided
        full_metadata = metadata.copy() if metadata else {}
        if execution_id:
            full_metadata["execution_id"] = execution_id
        details_json = json.dumps(full_metadata) if full_metadata else None

        cursor = self.conn.execute(
            f"""
            INSERT INTO {self.table} (
                domain, stage, partition_key,
                severity, category, message, detected_at, details_json, resolved_at
            ) VALUES ({self._ph(8)}, NULL)
            """,
            (
                self.domain,
                stage,
                partition_key_str,
                severity_str,
                category_str,
                message,
                detected_at,
                details_json,
            ),
        )
        self.conn.commit()

        # Return the AUTOINCREMENT id
        anomaly_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else 0
        return anomaly_id

    def resolve(self, anomaly_id: str, resolution_note: str | None = None) -> None:
        """
        Mark an anomaly as resolved.

        Args:
            anomaly_id: The anomaly to resolve
            resolution_note: Optional note about the resolution
        """
        resolved_at = datetime.now(UTC).isoformat()

        if resolution_note:
            # Update metadata with resolution note
            json_expr = self.dialect.json_set(
                "COALESCE(details_json, '{}')",
                "$.resolution_note",
                self.dialect.placeholder(1),
            )
            self.conn.execute(
                f"""
                UPDATE {self.table}
                SET resolved_at = {self.dialect.placeholder(0)},
                    details_json = {json_expr}
                WHERE id = {self.dialect.placeholder(2)}
                """,
                (resolved_at, resolution_note, anomaly_id),
            )
        else:
            self.conn.execute(
                f"""
                UPDATE {self.table} SET resolved_at = {self.dialect.placeholder(0)}
                WHERE id = {self.dialect.placeholder(1)}
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
                   message, detected_at, details_json, resolved_at
            FROM {self.table}
            WHERE domain = {self.dialect.placeholder(0)} AND resolved_at IS NULL
        """
        params: list[Any] = [self.domain]

        if severity:
            sev_str = severity.value if isinstance(severity, Severity) else severity
            query += f" AND severity = {self.dialect.placeholder(len(params))}"
            params.append(sev_str)

        if category:
            cat_str = category.value if isinstance(category, AnomalyCategory) else category
            query += f" AND category = {self.dialect.placeholder(len(params))}"
            params.append(cat_str)

        if stage:
            query += f" AND stage = {self.dialect.placeholder(len(params))}"
            params.append(stage)

        query += f" ORDER BY detected_at DESC LIMIT {self.dialect.placeholder(len(params))}"
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
        interval_expr = self.dialect.interval(-since_hours, "hours")
        cursor = self.conn.execute(
            f"""
            SELECT severity, COUNT(*) as cnt
            FROM {self.table}
            WHERE domain = {self.dialect.placeholder(0)}
              AND detected_at > {interval_expr}
            GROUP BY severity
            """,
            (self.domain,),
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
        interval_expr = self.dialect.interval(-since_hours, "hours")
        cursor = self.conn.execute(
            f"""
            SELECT 1 FROM {self.table}
            WHERE domain = {self.dialect.placeholder(0)}
              AND severity = 'CRITICAL'
              AND resolved_at IS NULL
              AND detected_at > {interval_expr}
            LIMIT 1
            """,
            (self.domain,),
        )

        return cursor.fetchone() is not None


# Convenience aliases
def create_recorder(conn: Connection, domain: str, dialect: Dialect = SQLiteDialect()) -> AnomalyRecorder:
    """Create an AnomalyRecorder for a domain."""
    return AnomalyRecorder(conn, domain, dialect=dialect)
