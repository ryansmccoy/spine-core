"""Base Pipeline class."""

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class Pipeline(ABC):
    """
    Base class for all pipelines.

    A pipeline is a unit of work that:
    - Has a unique name
    - Takes parameters
    - Executes some business logic
    - Returns a result

    Pipelines are registered in the registry and invoked by the runner.
    """

    # Override in subclasses
    name: str = "base"
    description: str = "Base pipeline"

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the pipeline.

        Args:
            params: Pipeline parameters

        Returns:
            Result dictionary
        """
        ...

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        Validate pipeline parameters.

        Override in subclasses for custom validation.

        Returns:
            List of validation error messages (empty if valid)
        """
        return []

    def __repr__(self) -> str:
        return f"<Pipeline:{self.name}>"
