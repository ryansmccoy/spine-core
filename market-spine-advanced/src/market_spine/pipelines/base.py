"""Base classes for pipeline definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from enum import Enum

import structlog

logger = structlog.get_logger()


class StepStatus(str, Enum):
    """Status of a pipeline step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result from executing a pipeline step."""

    status: StepStatus
    output: Any = None
    error: str | None = None
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result from executing a complete pipeline."""

    success: bool
    steps: list[StepResult] = field(default_factory=list)
    output: Any = None
    error: str | None = None
    total_duration_ms: float = 0


class Step(ABC):
    """Base class for a pipeline step."""

    def __init__(self, name: str | None = None):
        self.name = name or self.__class__.__name__

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> StepResult:
        """Execute the step with given context."""
        pass

    def should_run(self, context: dict[str, Any]) -> bool:
        """Override to conditionally skip the step."""
        return True


class FunctionStep(Step):
    """Step that wraps a simple function."""

    def __init__(self, func: Callable, name: str | None = None):
        super().__init__(name or func.__name__)
        self.func = func

    def execute(self, context: dict[str, Any]) -> StepResult:
        start = datetime.now()
        try:
            result = self.func(context)
            duration = (datetime.now() - start).total_seconds() * 1000
            return StepResult(
                status=StepStatus.COMPLETED,
                output=result,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            logger.exception("step_failed", step=self.name, error=str(e))
            return StepResult(
                status=StepStatus.FAILED,
                error=str(e),
                duration_ms=duration,
            )


class Pipeline(ABC):
    """
    Base class for defining a data pipeline.

    Subclasses should define:
    - name: unique identifier for the pipeline
    - steps: list of Step instances to execute
    - optionally override validate_params() and get_logical_key()
    """

    name: str = "base"
    description: str = ""

    def __init__(self):
        self.steps: list[Step] = []

    @abstractmethod
    def build_steps(self, params: dict[str, Any]) -> list[Step]:
        """Build the list of steps for this pipeline run."""
        pass

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate pipeline parameters.

        Returns (is_valid, error_message).
        """
        return True, None

    def get_logical_key(self, params: dict[str, Any]) -> str | None:
        """
        Generate a logical key for deduplication.

        Return None to disable deduplication.
        """
        return None

    def execute(self, params: dict[str, Any]) -> PipelineResult:
        """
        Execute the pipeline with given parameters.

        This runs synchronously - for async execution, use the runner/backend.
        """
        start = datetime.now()
        step_results: list[StepResult] = []

        # Validate params
        valid, error = self.validate_params(params)
        if not valid:
            return PipelineResult(
                success=False,
                error=f"Validation failed: {error}",
            )

        # Build steps
        try:
            self.steps = self.build_steps(params)
        except Exception as e:
            logger.exception("pipeline_build_failed", pipeline=self.name, error=str(e))
            return PipelineResult(
                success=False,
                error=f"Failed to build pipeline: {e}",
            )

        # Create execution context
        context: dict[str, Any] = {
            "params": params,
            "pipeline_name": self.name,
            "outputs": {},
        }

        # Execute steps
        for step in self.steps:
            logger.info("step_starting", pipeline=self.name, step=step.name)

            # Check if step should run
            if not step.should_run(context):
                step_results.append(
                    StepResult(
                        status=StepStatus.SKIPPED,
                        metadata={"reason": "should_run returned False"},
                    )
                )
                continue

            # Execute step
            result = step.execute(context)
            step_results.append(result)

            # Store output in context for subsequent steps
            context["outputs"][step.name] = result.output

            logger.info(
                "step_completed",
                pipeline=self.name,
                step=step.name,
                status=result.status.value,
                duration_ms=result.duration_ms,
            )

            # Stop on failure
            if result.status == StepStatus.FAILED:
                total_duration = (datetime.now() - start).total_seconds() * 1000
                return PipelineResult(
                    success=False,
                    steps=step_results,
                    error=result.error,
                    total_duration_ms=total_duration,
                )

        total_duration = (datetime.now() - start).total_seconds() * 1000

        # Get final output from last step
        final_output = step_results[-1].output if step_results else None

        return PipelineResult(
            success=True,
            steps=step_results,
            output=final_output,
            total_duration_ms=total_duration,
        )
