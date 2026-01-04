"""Example domain models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ExampleRecord:
    """Example raw record for testing pipelines."""

    id: int | None
    name: str
    value: float
    created_at: datetime
    metadata: dict[str, Any] | None = None
