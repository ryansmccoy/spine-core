"""Step Result — universal envelope for step execution outcomes.

Manifesto:
    Every step (lambda, operation, choice) must return a uniform result so
that the WorkflowRunner can: decide success/failure, pass outputs to
the next step, evaluate quality gates, and categorise errors for retry
decisions.  ``StepResult`` is that envelope.

ARCHITECTURE
────────────
::

    StepResult
      ├── .ok(output, context_updates, quality)     → success
      ├── .fail(error, category, quality)            → failure
      ├── .skip(reason)                              → no-op success
      ├── .from_value(any)                           → coerce plain returns
      └── .with_next_step(name)                      → choice branching

    ErrorCategory  ── INTERNAL, DATA_QUALITY, TRANSIENT, TIMEOUT, ...
    QualityMetrics ── record_count, valid_count, passed, custom_metrics

BEST PRACTICES
──────────────
- Prefer ``StepResult.ok()`` / ``StepResult.fail()`` factories over
  constructing directly.
- Use ``from_value()`` to wrap plain-function returns automatically.
- Set ``error_category`` on failures so retry policies can distinguish
  transient vs permanent errors.

Related modules:
    step_types.py       — Step definitions that produce StepResults
    workflow_runner.py  — consumes StepResults to drive workflow state
    step_adapters.py    — adapts plain functions to return StepResults

Example::

    from spine.orchestration import StepResult, QualityMetrics

    def validate_data(ctx, config):
        records = fetch_records()
        valid = [r for r in records if is_valid(r)]
        quality = QualityMetrics(record_count=len(records), valid_count=len(valid))
        if quality.valid_rate < 0.95:
            return StepResult.fail("Too few valid", category="DATA_QUALITY", quality=quality)
        return StepResult.ok(output={"valid_count": len(valid)}, quality=quality)

Tags:
    spine-core, orchestration, step-result, envelope, success-failure

Doc-Types:
    api-reference
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

    INTERNAL = "INTERNAL"  # Bug in step code
    DATA_QUALITY = "DATA_QUALITY"  # Data validation failure
    TRANSIENT = "TRANSIENT"  # Network/service temporary failure
    TIMEOUT = "TIMEOUT"  # Step execution timeout
    DEPENDENCY = "DEPENDENCY"  # External service failure
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
    - Operation steps are wrapped by the runner

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
    ) -> StepResult:
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
    ) -> StepResult:
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
    ) -> StepResult:
        """
        Create a skipped result (success, but no work done).

        Useful for idempotency checks, conditional skips, etc.
        """
        return cls(
            success=True,
            output=output or {"skipped": True, "skip_reason": reason},
            context_updates={},
        )

    @classmethod
    def from_value(cls, value: Any) -> StepResult:
        """Coerce an arbitrary return value into a StepResult.

        This enables **plain functions** (functions that return dicts, bools,
        strings, numbers, or None) to be used as workflow steps without
        importing or constructing ``StepResult`` explicitly.

        Coercion rules:

        ========== ===========================================================
        Type       Behaviour
        ========== ===========================================================
        StepResult Returned as-is (no wrapping).
        dict       ``StepResult.ok(output=value)``
        bool       ``ok()`` if True, ``fail("returned False")`` if False.
        str        ``ok(output={"message": value})``
        int/float  ``ok(output={"value": value})``
        None       ``ok()`` with empty output.
        other      ``ok(output={"result": value})``
        ========== ===========================================================

        Example::

            # All of these become valid StepResults:
            StepResult.from_value({"count": 42})
            StepResult.from_value(True)
            StepResult.from_value(None)
        """
        if isinstance(value, StepResult):
            return value
        if value is None:
            return cls.ok()
        if isinstance(value, dict):
            return cls.ok(output=value)
        if isinstance(value, bool):
            return cls.ok() if value else cls.fail("Step returned False")
        if isinstance(value, str):
            return cls.ok(output={"message": value})
        if isinstance(value, int | float):
            return cls.ok(output={"value": value})
        return cls.ok(output={"result": value})

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

    def with_next_step(self, next_step: str | None) -> StepResult:
        """Return a new ``StepResult`` with ``next_step`` set.

        Used by choice steps to tell the runner which step to jump to.
        The original result is not mutated.
        """
        return StepResult(
            success=self.success,
            output=self.output,
            context_updates=self.context_updates,
            error=self.error,
            error_category=self.error_category,
            quality=self.quality,
            events=self.events,
            next_step=next_step,
        )

    def __repr__(self) -> str:
        status = "OK" if self.success else f"FAIL({self.error_category})"
        return f"StepResult({status}, output_keys={list(self.output.keys())})"
