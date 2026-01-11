"""
Scheduler Result Contract - Shared schema for all scheduler outputs.

This module defines the stable contract for scheduler results across all domains.
All schedulers MUST return results conforming to this schema.

Key design principles:
- JSON-serializable for automation pipelines
- Consistent structure across FINRA, prices, and future schedulers
- Machine-readable for CI/CD exit code decisions
- Human-readable summaries

Exit Code Contract:
    0 = SUCCESS: All partitions processed successfully
    1 = FAILURE: Fail-fast triggered or systemic error
    2 = PARTIAL: Some partitions failed but execution continued
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class SchedulerStatus(str, Enum):
    """Overall scheduler execution status."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    DRY_RUN = "dry_run"


class RunStatus(str, Enum):
    """Individual pipeline run status."""
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


@dataclass
class RunResult:
    """Result of a single pipeline run within a scheduler execution."""
    pipeline: str
    partition_key: str
    status: RunStatus
    duration_ms: int = 0
    capture_id: str | None = None
    execution_id: str | None = None
    error: str | None = None
    rows_affected: int = 0
    
    # Revision tracking (for lookback/restatement)
    is_revision: bool = False
    revision_summary: dict | None = None  # {rows_added, rows_removed, rows_changed}
    
    def as_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pipeline": self.pipeline,
            "partition_key": self.partition_key,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "capture_id": self.capture_id,
            "execution_id": self.execution_id,
            "error": self.error,
            "rows_affected": self.rows_affected,
            "is_revision": self.is_revision,
            "revision_summary": self.revision_summary,
        }


@dataclass
class SchedulerStats:
    """Aggregate statistics for scheduler execution."""
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    
    @property
    def total(self) -> int:
        return self.succeeded + self.failed + self.skipped
    
    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
        }


@dataclass
class AnomalySummary:
    """Summary of an anomaly recorded during scheduler execution."""
    anomaly_id: str
    severity: str
    category: str
    partition_key: str
    message: str
    
    def as_dict(self) -> dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "severity": self.severity,
            "category": self.category,
            "partition_key": self.partition_key,
            "message": self.message,
        }


@dataclass
class SchedulerResult:
    """
    Standard result contract for all schedulers.
    
    All domain schedulers (FINRA, prices, etc.) MUST return this structure.
    Wrapper scripts convert this to JSON and exit codes.
    
    Attributes:
        domain: Domain identifier (e.g., "finra.otc_transparency", "market_data")
        scheduler: Scheduler name (e.g., "weekly_ingest", "price_batch")
        started_at: ISO timestamp when scheduler started
        finished_at: ISO timestamp when scheduler finished
        status: Overall execution status
        stats: Aggregate counts
        runs: Individual pipeline run results
        anomalies: Anomalies recorded during execution
        warnings: Non-fatal warnings
        config: Configuration used for this run
    """
    domain: str
    scheduler: str
    started_at: str
    finished_at: str
    status: SchedulerStatus
    stats: SchedulerStats = field(default_factory=SchedulerStats)
    runs: list[RunResult] = field(default_factory=list)
    anomalies: list[AnomalySummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Total execution duration in seconds."""
        try:
            start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.finished_at.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except (ValueError, AttributeError):
            return 0.0
    
    @property
    def exit_code(self) -> int:
        """
        Compute exit code based on status.
        
        Returns:
            0 = SUCCESS or DRY_RUN
            1 = FAILURE (fail-fast or systemic)
            2 = PARTIAL (some failures, execution continued)
        """
        if self.status in (SchedulerStatus.SUCCESS, SchedulerStatus.DRY_RUN):
            return 0
        elif self.status == SchedulerStatus.PARTIAL:
            return 2
        else:
            return 1
    
    def as_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "domain": self.domain,
            "scheduler": self.scheduler,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "stats": self.stats.as_dict(),
            "runs": [r.as_dict() for r in self.runs],
            "anomalies": [a.as_dict() for a in self.anomalies],
            "warnings": self.warnings,
            "config": self.config,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.as_dict(), indent=indent, default=str)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchedulerResult":
        """Create from dictionary (e.g., parsed JSON)."""
        stats = SchedulerStats(**data.get("stats", {}))
        
        runs = []
        for r in data.get("runs", []):
            r_copy = r.copy()
            r_copy["status"] = RunStatus(r_copy["status"])
            runs.append(RunResult(**r_copy))
        
        anomalies = [AnomalySummary(**a) for a in data.get("anomalies", [])]
        
        return cls(
            domain=data["domain"],
            scheduler=data["scheduler"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            status=SchedulerStatus(data["status"]),
            stats=stats,
            runs=runs,
            anomalies=anomalies,
            warnings=data.get("warnings", []),
            config=data.get("config", {}),
        )


# Schema version for compatibility tracking
SCHEDULER_RESULT_SCHEMA_VERSION = "1.0.0"


def validate_scheduler_result(result: SchedulerResult) -> tuple[bool, list[str]]:
    """
    Validate a SchedulerResult conforms to the contract.
    
    Returns:
        (is_valid: bool, errors: list[str])
    """
    errors = []
    
    if not result.domain:
        errors.append("domain is required")
    if not result.scheduler:
        errors.append("scheduler is required")
    if not result.started_at:
        errors.append("started_at is required")
    if not result.finished_at:
        errors.append("finished_at is required")
    if not isinstance(result.status, SchedulerStatus):
        errors.append(f"status must be SchedulerStatus, got {type(result.status)}")
    
    # Validate stats consistency
    expected_total = result.stats.succeeded + result.stats.failed + result.stats.skipped
    if len(result.runs) != expected_total:
        errors.append(
            f"runs count ({len(result.runs)}) != stats total ({expected_total})"
        )
    
    # Validate run results
    for i, run in enumerate(result.runs):
        if not run.pipeline:
            errors.append(f"run[{i}].pipeline is required")
        if not run.partition_key:
            errors.append(f"run[{i}].partition_key is required")
        if not isinstance(run.status, RunStatus):
            errors.append(f"run[{i}].status must be RunStatus")
    
    return (len(errors) == 0, errors)
