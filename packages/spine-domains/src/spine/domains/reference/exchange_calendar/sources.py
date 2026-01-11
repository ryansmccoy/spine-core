"""
Source and period abstractions for Exchange Calendar domain.

This domain uses:
- JsonSource: Reads static JSON files with holiday data
- AnnualPeriod: Year-based temporal granularity

These are domain-local registries (not shared with FINRA).
Each domain can define its own source types as needed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
import json


# =============================================================================
# PERIOD STRATEGY (Annual)
# =============================================================================


class PeriodStrategy(ABC):
    """Abstract base for period strategies (domain-local)."""

    @property
    @abstractmethod
    def period_type(self) -> str:
        """Return period type identifier."""
        ...

    @abstractmethod
    def derive_period_end(self, reference_date: date) -> date:
        """Derive period end from a reference date."""
        ...

    @abstractmethod
    def validate_date(self, period_end: date) -> bool:
        """Validate that date is a valid period end."""
        ...

    @abstractmethod
    def format_for_display(self, period_end: date) -> str:
        """Human-readable period identifier."""
        ...


# Period Registry (domain-local)
PERIOD_REGISTRY: dict[str, type[PeriodStrategy]] = {}


def register_period(name: str):
    """Decorator to register a period strategy."""
    def decorator(cls: type[PeriodStrategy]) -> type[PeriodStrategy]:
        PERIOD_REGISTRY[name] = cls
        return cls
    return decorator


def resolve_period(period_type: str = "annual") -> PeriodStrategy:
    """Resolve period strategy by type."""
    if period_type not in PERIOD_REGISTRY:
        available = ", ".join(PERIOD_REGISTRY.keys())
        raise ValueError(f"Unknown period type: {period_type}. Available: {available}")
    return PERIOD_REGISTRY[period_type]()


@register_period("annual")
class AnnualPeriod(PeriodStrategy):
    """
    Annual period strategy for reference data.
    
    Period end is December 31 of the reference year.
    """

    @property
    def period_type(self) -> str:
        return "annual"

    def derive_period_end(self, reference_date: date) -> date:
        """
        Derive year-end from any date in that year.
        
        Example: 2025-06-15 → 2025-12-31
        """
        return date(reference_date.year, 12, 31)

    def validate_date(self, period_end: date) -> bool:
        """Annual period ends must be December 31."""
        return period_end.month == 12 and period_end.day == 31

    def format_for_display(self, period_end: date) -> str:
        """Display as year only."""
        return str(period_end.year)


# =============================================================================
# SOURCE ABSTRACTION (JSON)
# =============================================================================


@dataclass
class IngestionMetadata:
    """Metadata about ingested data."""
    
    year: int
    exchange_code: str
    source_type: str
    source_name: str
    fetched_at: datetime
    period_type: str = "annual"
    
    # Alias for consistency with other domains
    @property
    def period_end(self) -> date:
        """Period end date (Dec 31 of year)."""
        return date(self.year, 12, 31)


@dataclass
class Payload:
    """Content + metadata from any source."""
    
    content: dict[str, Any]  # Parsed JSON
    metadata: IngestionMetadata


class IngestionSource(ABC):
    """Abstract base for ingestion sources."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return source type identifier."""
        ...

    @abstractmethod
    def fetch(self) -> Payload:
        """Fetch data from source."""
        ...


# Source Registry (domain-local)
SOURCE_REGISTRY: dict[str, type[IngestionSource]] = {}


def register_source(name: str):
    """Decorator to register a source type."""
    def decorator(cls: type[IngestionSource]) -> type[IngestionSource]:
        SOURCE_REGISTRY[name] = cls
        return cls
    return decorator


def resolve_source(source_type: str = "json", **kwargs) -> IngestionSource:
    """Resolve source by type with parameters."""
    if source_type not in SOURCE_REGISTRY:
        available = ", ".join(SOURCE_REGISTRY.keys())
        raise ValueError(f"Unknown source type: {source_type}. Available: {available}")
    return SOURCE_REGISTRY[source_type](**kwargs)


class IngestionError(Exception):
    """Error during data ingestion."""
    pass


@register_source("json")
class JsonSource(IngestionSource):
    """
    JSON file ingestion source for reference data.
    
    Reads static JSON files containing holiday calendars.
    """

    def __init__(
        self,
        file_path: Path | str | None = None,
        year: int | None = None,
        exchange_code: str | None = None,
        period_type: str = "annual",
        **kwargs,  # Accept extra params for registry compatibility
    ):
        if file_path is None:
            raise IngestionError("file_path is required for JsonSource")
        
        self.file_path = Path(file_path)
        self.year = year
        self.exchange_code = exchange_code
        self.period_strategy = resolve_period(period_type)

        if not self.file_path.exists():
            raise IngestionError(f"File not found: {self.file_path}")

    @property
    def source_type(self) -> str:
        return "json"

    def fetch(self) -> Payload:
        """Read and parse JSON file."""
        from datetime import UTC
        
        content = json.loads(self.file_path.read_text(encoding="utf-8"))
        
        # Extract year and exchange from content if not provided
        year = self.year or content.get("year")
        exchange_code = self.exchange_code or content.get("exchange_code")
        
        if not year:
            raise IngestionError("year not found in file or parameters")
        if not exchange_code:
            raise IngestionError("exchange_code not found in file or parameters")
        
        return Payload(
            content=content,
            metadata=IngestionMetadata(
                year=int(year),
                exchange_code=exchange_code,
                source_type="json",
                source_name=str(self.file_path),
                fetched_at=datetime.now(UTC),
                period_type=self.period_strategy.period_type,
            ),
        )


def create_source(source_type: str = "json", **kwargs) -> IngestionSource:
    """
    Factory for creating sources (backward compatibility).
    
    Delegates to resolve_source().
    """
    return resolve_source(source_type=source_type, **kwargs)
