"""Database adapter base class."""

from __future__ import annotations
from abc import ABC, abstractmethod


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...
