"""
Quality check framework for data validation.

Provides a composable framework for defining and executing data quality checks.
QualityRunner executes checks and records results to core_quality table, enabling
quality gates, audit trails, and compliance reporting.

Manifesto:
    Data quality is critical for financial pipelines. Bad data leads to bad
    decisions. The quality framework provides:
    
    - **Declarative checks:** Define what to check, not how to check it
    - **Audit trail:** All checks recorded with results and context
    - **Quality gates:** Stop processing if critical checks fail
    - **Composable:** Add/remove checks without code changes
    
    Checks are non-blocking by default: they record issues but don't stop
    processing. Use has_failures() for explicit quality gates.

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Quality Framework                         │
        └─────────────────────────────────────────────────────────────┘
        
        QualityCheck Definition:
        ┌────────────────────────────────────────────────────────────┐
        │ check = QualityCheck(                                      │
        │     name="market_share_sum",                               │
        │     category=QualityCategory.BUSINESS_RULE,                │
        │     check_fn=lambda ctx: QualityResult(...)                │
        │ )                                                          │
        └────────────────────────────────────────────────────────────┘
        
        QualityRunner Execution:
        ┌────────────────────────────────────────────────────────────┐
        │ runner = QualityRunner(conn, domain="otc", exec_id="...")  │
        │ runner.add(check1).add(check2)                             │
        │ results = runner.run_all(context, partition_key)           │
        │                                                            │
        │ if runner.has_failures():                                  │
        │     raise QualityGateError(runner.failures())              │
        └────────────────────────────────────────────────────────────┘
        
        Storage (core_quality table):
        ┌────────────────────────────────────────────────────────────┐
        │ domain | partition_key | check_name | status | message    │
        │ "otc"  | {...}         | "sum_100"  | "PASS" | "Sum OK"   │
        │ "otc"  | {...}         | "no_neg"   | "FAIL" | "Found -5" │
        └────────────────────────────────────────────────────────────┘

Features:
    - **QualityCheck:** Declarative check definition
    - **QualityRunner:** Execute checks and record results
    - **QualityStatus:** PASS/WARN/FAIL status enum
    - **QualityCategory:** INTEGRITY/COMPLETENESS/BUSINESS_RULE
    - **Quality gates:** has_failures(), failures() for gating

Examples:
    Define and run checks:

    >>> def check_share_sum(ctx: dict) -> QualityResult:
    ...     total = sum(s.market_share_pct for s in ctx["shares"])
    ...     if 99.9 <= total <= 100.1:
    ...         return QualityResult(QualityStatus.PASS, "Sum OK", total, 100.0)
    ...     return QualityResult(QualityStatus.FAIL, f"Sum {total}", total, 100.0)
    >>> 
    >>> runner = QualityRunner(conn, domain="otc", execution_id="abc")
    >>> runner.add(QualityCheck("share_sum", QualityCategory.BUSINESS_RULE, check_share_sum))
    >>> results = runner.run_all({"shares": venue_shares}, partition_key={...})
    >>> runner.has_failures()
    False

Tags:
    quality, validation, data-quality, audit-trail, quality-gate,
    spine-core, compliance

Doc-Types:
    - API Reference
    - Data Quality Guide
    - Compliance Documentation

SCHEMA OWNERSHIP:
- Uses shared `core_quality` table (defined in spine.core.schema)
- Domain is a partition key, not a separate table
- Domains do NOT need their own quality tables

SYNC-ONLY: All methods are synchronous.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from .schema import CORE_TABLES


class Connection(Protocol):
    """Minimal SYNC DB connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...


class QualityStatus(str, Enum):
    """
    Result status of a quality check.

    Manifesto:
        Three-state quality results enable nuanced handling:
        - **PASS:** Check succeeded, data is valid
        - **WARN:** Check found issues but not critical
        - **FAIL:** Check failed, data quality is compromised

        WARN allows for soft thresholds: "null rate is 15%, above 10% target
        but below 25% hard limit". This enables alerting without blocking.

    Examples:
        >>> result = QualityResult(QualityStatus.PASS, "Sum within tolerance")
        >>> result.status == QualityStatus.PASS
        True

    Tags:
        quality-status, enum, data-quality, spine-core
    """

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class QualityCategory(str, Enum):
    """
    Category of quality check for classification and routing.

    Manifesto:
        Quality checks fall into categories:
        - **INTEGRITY:** Data structure correctness (types, constraints)
        - **COMPLETENESS:** Data coverage and availability
        - **BUSINESS_RULE:** Domain-specific validation rules

        Categories enable:
        - Routing failures to appropriate teams
        - Different alert thresholds by category
        - Quality dashboards by check type

    Examples:
        >>> check = QualityCheck("sum_100", QualityCategory.BUSINESS_RULE, fn)
        >>> check.category.value
        'BUSINESS_RULE'

    Tags:
        quality-category, enum, classification, spine-core
    """

    INTEGRITY = "INTEGRITY"  # Data structure correctness
    COMPLETENESS = "COMPLETENESS"  # Data coverage/availability
    BUSINESS_RULE = "BUSINESS_RULE"  # Domain-specific rules


@dataclass
class QualityResult:
    """
    Result of one quality check execution.

    Contains the check status, human-readable message, and optional
    actual/expected values for debugging and reporting.

    Manifesto:
        Quality results must be actionable:
        - **status:** Did the check pass, warn, or fail?
        - **message:** Human-readable explanation
        - **actual_value:** What was found (for debugging)
        - **expected_value:** What was expected (for comparison)

        This enables both automated gating and human investigation.

    Examples:
        Passing check:

        >>> result = QualityResult(
        ...     status=QualityStatus.PASS,
        ...     message="Sum within tolerance",
        ...     actual_value=100.05,
        ...     expected_value=100.0
        ... )

        Failing check:

        >>> result = QualityResult(
        ...     status=QualityStatus.FAIL,
        ...     message="Negative volume found",
        ...     actual_value=-500,
        ...     expected_value=">=0"
        ... )

    Attributes:
        status: PASS, WARN, or FAIL
        message: Human-readable explanation
        actual_value: What was found
        expected_value: What was expected

    Tags:
        quality-result, dataclass, validation, spine-core
    """

    status: QualityStatus
    message: str
    actual_value: Any = None
    expected_value: Any = None


@dataclass
class QualityCheck:
    """
    Definition of a quality check to be executed.

    A check consists of a name, category, and check function that receives
    a context dict and returns a QualityResult. Checks are declarative -
    define once, run anywhere.

    Manifesto:
        Quality checks should be:
        - **Named:** For identification in reports and alerts
        - **Categorized:** For routing and dashboards
        - **Pure functions:** Context in → Result out
        - **Reusable:** Same check for different partitions

    Examples:
        Define a business rule check:

        >>> def check_share_sum(ctx: dict) -> QualityResult:
        ...     total = sum(s.market_share_pct for s in ctx["shares"])
        ...     if 99.9 <= total <= 100.1:
        ...         return QualityResult(QualityStatus.PASS, "Sum OK", total, 100.0)
        ...     return QualityResult(QualityStatus.FAIL, f"Sum {total}", total, 100.0)
        >>>
        >>> check = QualityCheck(
        ...     name="market_share_sum",
        ...     category=QualityCategory.BUSINESS_RULE,
        ...     check_fn=check_share_sum
        ... )

    Attributes:
        name: Unique identifier for the check
        category: INTEGRITY, COMPLETENESS, or BUSINESS_RULE
        check_fn: Function (context: dict) -> QualityResult

    Tags:
        quality-check, definition, validation, spine-core
    """

    name: str
    category: QualityCategory
    check_fn: Callable[[dict], QualityResult]


class QualityRunner:
    """
    Execute quality checks and record results to core_quality table.

    QualityRunner is the execution engine for quality checks. It runs checks
    against a context, records results to the database, and provides
    methods for quality gating (has_failures, failures).

    Manifesto:
        Quality execution should be:
        - **Recorded:** All results persisted for audit trail
        - **Chainable:** Add checks fluently with add()
        - **Non-blocking:** Runs all checks, reports at end
        - **Gate-ready:** has_failures() enables quality gates

        Results are stored in core_quality table, partitioned by domain.
        Each check run creates one row with full context.

    Architecture:
        ```
        ┌──────────────────────────────────────────────────────────┐
        │                    QualityRunner Flow                     │
        └──────────────────────────────────────────────────────────┘

        1. Setup:
        ┌────────────────────────────────────────────────────────┐
        │ runner = QualityRunner(conn, domain="otc", exec_id="..")│
        │ runner.add(check1).add(check2).add(check3)             │
        └────────────────────────────────────────────────────────┘

        2. Execution:
        ┌────────────────────────────────────────────────────────┐
        │ results = runner.run_all(context, partition_key)       │
        │                                                        │
        │ For each check:                                        │
        │   result = check.check_fn(context)                     │
        │   INSERT INTO core_quality (...)                       │
        └────────────────────────────────────────────────────────┘

        3. Quality Gate:
        ┌────────────────────────────────────────────────────────┐
        │ if runner.has_failures():                              │
        │     raise QualityGateError(runner.failures())          │
        └────────────────────────────────────────────────────────┘
        ```

    Features:
        - **Fluent API:** runner.add(check1).add(check2)
        - **Batch execution:** run_all() executes all checks
        - **Persistence:** Results recorded to core_quality table
        - **Quality gates:** has_failures(), failures()
        - **Context flow:** execution_id, batch_id for lineage

    Examples:
        Basic usage:

        >>> runner = QualityRunner(conn, domain="otc", execution_id="abc123")
        >>> runner.add(QualityCheck("sum_100", BUSINESS_RULE, check_share_sum))
        >>> runner.add(QualityCheck("no_negative", INTEGRITY, check_volumes))
        >>>
        >>> results = runner.run_all(
        ...     {"shares": venue_shares, "volumes": volumes},
        ...     partition_key={"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
        ... )
        >>> # results = {"sum_100": PASS, "no_negative": PASS}

        Quality gate pattern:

        >>> runner.run_all(context, partition_key)
        >>> if runner.has_failures():
        ...     failed = runner.failures()  # ["check_name", ...]
        ...     raise QualityGateError(f"Failed checks: {failed}")

    Performance:
        - **run_all():** O(n) where n = number of checks
        - **Each check:** Depends on check function + 1 INSERT

    Guardrails:
        ❌ DON'T: Ignore has_failures() for critical pipelines
        ✅ DO: Check has_failures() and decide how to handle

        ❌ DON'T: Run heavy computations in check_fn
        ✅ DO: Pre-compute values, pass via context

    Tags:
        quality-runner, execution, quality-gate, audit-trail, spine-core

    Doc-Types:
        - API Reference
        - Data Quality Guide
    """

    def __init__(
        self,
        conn: Connection,
        domain: str,
        execution_id: str,
        batch_id: str = None,
        table: str = None,  # Deprecated: use core_quality
    ):
        self.conn = conn
        self.domain = domain
        self.table = table or CORE_TABLES["quality"]
        self.execution_id = execution_id
        self.batch_id = batch_id
        self.checks: list[QualityCheck] = []
        self._results: dict[str, QualityResult] = {}

    def _key_json(self, key: dict[str, Any]) -> str:
        """Serialize key dict to JSON for storage."""
        return json.dumps(key, sort_keys=True, default=str)

    def add(self, check: QualityCheck) -> "QualityRunner":
        """Add a check. Returns self for chaining."""
        self.checks.append(check)
        return self

    def run_all(
        self, context: dict, partition_key: dict[str, Any] = None
    ) -> dict[str, QualityStatus]:
        """
        Run all checks, record results.

        Returns:
            Dict mapping check name to status
        """
        self._results.clear()

        for check in self.checks:
            result = check.check_fn(context)
            self._results[check.name] = result
            self._record(check, result, partition_key)

        return {name: r.status for name, r in self._results.items()}

    def has_failures(self) -> bool:
        """Check if any checks failed."""
        return any(r.status == QualityStatus.FAIL for r in self._results.values())

    def failures(self) -> list[str]:
        """Get names of failed checks."""
        return [name for name, r in self._results.items() if r.status == QualityStatus.FAIL]

    def _record(
        self, check: QualityCheck, result: QualityResult, partition_key: dict[str, Any]
    ) -> None:
        key_json = self._key_json(partition_key) if partition_key else "{}"

        columns = [
            "domain",
            "partition_key",
            "check_name",
            "category",
            "status",
            "message",
            "actual_value",
            "expected_value",
            "execution_id",
            "batch_id",
            "created_at",
        ]

        values = (
            self.domain,
            key_json,
            check.name,
            check.category.value,
            result.status.value,
            result.message,
            json.dumps(result.actual_value, default=str)
            if result.actual_value is not None
            else None,
            json.dumps(result.expected_value, default=str)
            if result.expected_value is not None
            else None,
            self.execution_id,
            self.batch_id,
            datetime.utcnow().isoformat(),
        )

        placeholders = ", ".join("?" * len(columns))
        self.conn.execute(
            f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})", values
        )
