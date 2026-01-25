"""
Quality check framework for data validation.

QualityRunner executes checks and records results,
enabling quality gates and audit trails.

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
    """Result status of a quality check."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class QualityCategory(str, Enum):
    """Category of quality check."""

    INTEGRITY = "INTEGRITY"  # Data structure correctness
    COMPLETENESS = "COMPLETENESS"  # Data coverage/availability
    BUSINESS_RULE = "BUSINESS_RULE"  # Domain-specific rules


@dataclass
class QualityResult:
    """
    Result of one quality check.

    Attributes:
        status: PASS, WARN, or FAIL
        message: Human-readable explanation
        actual_value: What was found
        expected_value: What was expected
    """

    status: QualityStatus
    message: str
    actual_value: Any = None
    expected_value: Any = None


@dataclass
class QualityCheck:
    """
    Definition of a quality check.

    The check_fn receives a context dict and returns a QualityResult.

    Example:
        def check_share_sum(ctx: dict) -> QualityResult:
            total = sum(s.market_share_pct for s in ctx["shares"])
            if 99.9 <= total <= 100.1:
                return QualityResult(QualityStatus.PASS, "Sum within tolerance", total, 100.0)
            return QualityResult(QualityStatus.FAIL, f"Sum {total} outside tolerance", total, 100.0)

        check = QualityCheck("market_share_sum", QualityCategory.BUSINESS_RULE, check_share_sum)
    """

    name: str
    category: QualityCategory
    check_fn: Callable[[dict], QualityResult]


class QualityRunner:
    """
    Run quality checks and record results to core_quality table.

    Example:
        runner = QualityRunner(conn, domain="otc", execution_id="abc123")
        runner.add(QualityCheck("market_share_sum", BUSINESS_RULE, check_share_sum))
        runner.add(QualityCheck("no_negative_volume", INTEGRITY, check_volumes))

        results = runner.run_all(
            {"shares": venue_shares, "volumes": volumes},
            partition_key={"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
        )
        # results = {"market_share_sum": PASS, "no_negative_volume": PASS}

        if runner.has_failures():
            raise QualityGateError(runner.failures())
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
