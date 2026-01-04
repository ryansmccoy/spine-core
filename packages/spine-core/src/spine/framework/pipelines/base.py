"""Base pipeline interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spine.framework.params import PipelineSpec


class PipelineStatus(str, Enum):
    """Pipeline execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""

    status: PipelineStatus
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        """Duration in seconds if completed."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class Pipeline(ABC):
    """Base class for all pipelines."""

    # Pipeline metadata
    name: str = ""
    description: str = ""
    spec: "PipelineSpec | None" = None  # Parameter specification

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        """Initialize pipeline with parameters."""
        self.params = params or {}

    @abstractmethod
    def run(self) -> PipelineResult:
        """Execute the pipeline. Must be implemented by subclasses."""
        ...

    def validate_params(self) -> None:
        """Validate pipeline parameters. Override in subclasses."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(params={self.params})"
