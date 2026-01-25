"""
Step Result - Universal envelope for step execution results.

Every step (lambda or pipeline) returns a StepResult. This provides:
- Success/failure status
- Output data for subsequent steps
- Context updates to merge into workflow context
- Optional quality metrics for data quality gates
- Error categorization for retry decisions

Tier: Basic (spine-core)

Example:
    from spine.orchestration import StepResult, QualityMetrics

    def validate_data(ctx: WorkflowContext, config: dict) -> StepResult:
        records = fetch_records()
        valid = [r for r in records if is_valid(r)]

        quality = QualityMetrics(
            record_count=len(records),
            valid_count=len(valid),
            passed=len(valid) / len(records) > 0.95,
        )

        if not quality.passed:
            return StepResult.fail(
                error=f"Only {len(valid)}/{len(records)} records valid",
                category="DATA_QUALITY",
                quality=quality,
            )

        return StepResult.ok(
            output={"valid_count": len(valid)},
            quality=quality,
        )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """
    Error categories for retry and alerting decisions.

    Tier placement:
    - Basic: INTERNAL, DATA_QUALITY
    - Advanced: TRANSIENT, TIMEOUT, DEPENDENCY (need retry policies)
    """

    INTERNAL = "INTERNAL"        # Bug in step code
    DATA_QUALITY = "DATA_QUALITY"  # Data validation failure
    TRANSIENT = "TRANSIENT"      # Network/service temporary failure
    TIMEOUT = "TIMEOUT"          # Step execution timeout
    DEPENDENCY = "DEPENDENCY"    # External service failure
    CONFIGURATION = "CONFIGURATION"  # Missing/invalid config


@dataclass
class QualityMetrics:
    """
    Quality metrics from a step execution.

    Used by quality gates to decide pass/fail.
    Integrates with spine.core.quality for historical tracking.
    """

    record_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    null_count: int = 0
    passed: bool = True
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    failure_reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Auto-calculate invalid if not provided
        if self.invalid_count == 0 and self.valid_count > 0:
            self.invalid_count = self.record_count - self.valid_count

    @property
    def valid_rate(self) -> float:
        """Percentage of valid records."""
        if self.record_count == 0:
            return 0.0
        return self.valid_count / self.record_count

    @property
    def null_rate(self) -> float:
        """Percentage of records with nulls."""
        if self.record_count == 0:
            return 0.0
        return self.null_count / self.record_count

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/checkpointing."""
        return {
            "record_count": self.record_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "null_count": self.null_count,
            "passed": self.passed,
            "valid_rate": self.valid_rate,
            "null_rate": self.null_rate,
            "custom_metrics": self.custom_metrics,
            "failure_reasons": self.failure_reasons,
        }


@dataclass
class StepResult:
    """
    Result from executing a workflow step.

    This is the universal envelope returned by all steps:
    - Lambda steps return directly
    - Pipeline steps are wrapped by the runner

    Attributes:
        success: Whether the step completed successfully
        output: Data to store under step name in context.outputs
        context_updates: Keys to merge into context.params for next step
        error: Error message if success=False
        error_category: Category for retry decisions (Advanced tier)
        quality: Optional quality metrics for data quality gates
        events: Structured log events for observability
        next_step: Override for next step (Intermediate tier - choice steps)
    """

    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    context_updates: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_category: ErrorCategory | str | None = None
    quality: QualityMetrics | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    next_step: str | None = None  # For choice steps (Intermediate tier)

    def __post_init__(self):
        # Ensure error message on failure
        if not self.success and not self.error:
            object.__setattr__(self, "error", "Step failed without error message")

        # Normalize error_category to string
        if isinstance(self.error_category, ErrorCategory):
            object.__setattr__(self, "error_category", self.error_category.value)

    # =========================================================================
    # Factories
    # =========================================================================

    @classmethod
    def ok(
        cls,
        output: dict[str, Any] | None = None,
        context_updates: dict[str, Any] | None = None,
        quality: QualityMetrics | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> "StepResult":
        """
        Create a successful result.

        Args:
            output: Data to store in context.outputs[step_name]
            context_updates: Keys to merge into context.params
            quality: Optional quality metrics
            events: Optional structured log events
        """
        return cls(
            success=True,
            output=output or {},
            context_updates=context_updates or {},
            quality=quality,
            events=events or [],
        )

    @classmethod
    def fail(
        cls,
        error: str,
        category: ErrorCategory | str = ErrorCategory.INTERNAL,
        output: dict[str, Any] | None = None,
        quality: QualityMetrics | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> "StepResult":
        """
        Create a failed result.

        Args:
            error: Human-readable error message
            category: Error category for retry/alerting decisions
            output: Optional partial output (for debugging)
            quality: Optional quality metrics (for data quality failures)
            events: Optional structured log events
        """
        return cls(
            success=False,
            output=output or {},
            error=error,
            error_category=category,
            quality=quality,
            events=events or [],
        )

    @classmethod
    def skip(
        cls,
        reason: str,
        output: dict[str, Any] | None = None,
    ) -> "StepResult":
        """
        Create a skipped result (success, but no work done).

        Useful for idempotency checks, conditional skips, etc.
        """
        return cls(
            success=True,
            output=output or {"skipped": True, "skip_reason": reason},
            context_updates={},
        )

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize for checkpointing/logging."""
        result = {
            "success": self.success,
            "output": self.output,
            "context_updates": self.context_updates,
        }

        if self.error:
            result["error"] = self.error
        if self.error_category:
            result["error_category"] = self.error_category
        if self.quality:
            result["quality"] = self.quality.to_dict()
        if self.events:
            result["events"] = self.events
        if self.next_step:
            result["next_step"] = self.next_step

        return result

    def __repr__(self) -> str:
        status = "OK" if self.success else f"FAIL({self.error_category})"
        return f"StepResult({status}, output_keys={list(self.output.keys())})"
