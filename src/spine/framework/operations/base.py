"""Base operation interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spine.framework.params import OperationSpec


class OperationStatus(str, Enum):
    """Operation execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OperationResult:
    """Result of a operation execution."""

    status: OperationStatus
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


class Operation(ABC):
    """Base class for all operations."""

    # Operation metadata
    name: str = ""
    description: str = ""
    spec: "OperationSpec | None" = None  # Parameter specification

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        """Initialize operation with parameters."""
        self.params = params or {}

    @abstractmethod
    def run(self) -> OperationResult:
        """Execute the operation. Must be implemented by subclasses."""
        ...

    def validate_params(self) -> None:  # noqa: B027
        """Validate operation parameters. Override in subclasses."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(params={self.params})"
