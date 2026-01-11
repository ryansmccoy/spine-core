"""
Ingestion source and period strategy abstractions for FINRA OTC data.

This module provides uniform interfaces for:
1. Sources: Where data comes from (file, API, S3, etc.)
2. Periods: Temporal granularity (weekly, monthly, etc.)

Both use registry patterns for extensibility without pipeline edits.

Architecture:
    Pipeline → resolve_source(params) → source.fetch() → Payload
             → resolve_period(params) → period.derive_period_end()
             → parse_finra_content(payload.content) → records
             → insert with metadata

To add a new source or period:
    @register_source("s3")
    class S3Source(IngestionSource): ...

    @register_period("monthly")
    class MonthlyPeriod(PeriodStrategy): ...

The pipeline never changes when new sources or periods are added.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from spine.domains.finra.otc_transparency.connector import (
    extract_file_date_from_content,
    extract_file_date_from_filename,
    extract_tier_from_filename,
)


# =============================================================================
# PERIOD STRATEGY (Temporal Granularity Abstraction)
# =============================================================================


class PeriodStrategy(ABC):
    """
    Abstract base for period/time-grain strategies.
    
    Encapsulates temporal semantics:
    - How to derive period end from publication date
    - Date validation rules
    - Filename/display formatting
    """

    @property
    @abstractmethod
    def period_type(self) -> str:
        """Return period type identifier (weekly, monthly, etc.)."""
        ...

    @abstractmethod
    def derive_period_end(self, publish_date: date) -> date:
        """
        Derive period end date from publication date.
        
        Example: Monday publish → Friday week_ending for weekly data.
        """
        ...

    @abstractmethod
    def validate_date(self, period_end: date) -> bool:
        """
        Validate that date is a valid period end.
        
        Example: For weekly, must be Friday.
        """
        ...

    @abstractmethod
    def format_for_filename(self, period_end: date) -> str:
        """Format period end for filename construction."""
        ...

    @abstractmethod
    def format_for_display(self, period_end: date) -> str:
        """Human-readable period identifier for logs/UI."""
        ...


# Period Registry
PERIOD_REGISTRY: dict[str, type[PeriodStrategy]] = {}


def register_period(name: str):
    """Decorator to register a period strategy."""
    def decorator(cls: type[PeriodStrategy]) -> type[PeriodStrategy]:
        PERIOD_REGISTRY[name] = cls
        return cls
    return decorator


def resolve_period(period_type: str = "weekly") -> PeriodStrategy:
    """
    Resolve period strategy by type from registry.
    
    Args:
        period_type: Period identifier (weekly, monthly, etc.)
    
    Returns:
        PeriodStrategy instance
    
    Raises:
        ValueError: If period_type not in registry
    """
    if period_type not in PERIOD_REGISTRY:
        raise ValueError(
            f"Unknown period: {period_type}. Known: {list(PERIOD_REGISTRY.keys())}"
        )
    return PERIOD_REGISTRY[period_type]()


def list_periods() -> list[str]:
    """Return list of registered period types."""
    return list(PERIOD_REGISTRY.keys())


# =============================================================================
# WEEKLY PERIOD (Default for FINRA OTC)
# =============================================================================


@register_period("weekly")
class WeeklyPeriod(PeriodStrategy):
    """
    FINRA weekly data semantics.
    
    - Published on Mondays
    - Period end = previous Friday
    - week_ending must be a Friday
    """

    @property
    def period_type(self) -> str:
        return "weekly"

    def derive_period_end(self, publish_date: date) -> date:
        """
        Derive Friday week_ending from Monday publication date.
        
        Rule: week_ending = file_date - 3 days (for Monday publication)
        
        Example:
            2025-12-22 (Mon) -> 2025-12-19 (Fri)
            2025-12-29 (Mon) -> 2025-12-26 (Fri)
        """
        # Monday is weekday 0, Friday is weekday 4
        days_since_friday = (publish_date.weekday() - 4) % 7
        if days_since_friday == 0:
            days_since_friday = 7  # If it's Friday, go back a week
        return publish_date - timedelta(days=days_since_friday)

    def validate_date(self, period_end: date) -> bool:
        """Week ending must be Friday (weekday 4)."""
        return period_end.weekday() == 4

    def format_for_filename(self, period_end: date) -> str:
        """ISO date format: YYYY-MM-DD."""
        return period_end.isoformat()

    def format_for_display(self, period_end: date) -> str:
        """Human readable: Week ending 2025-12-26."""
        return f"Week ending {period_end.isoformat()}"


# =============================================================================
# MONTHLY PERIOD (Future: FINRA monthly data)
# =============================================================================


@register_period("monthly")
class MonthlyPeriod(PeriodStrategy):
    """
    FINRA monthly data semantics.
    
    - Published ~1st of month
    - Period end = last day of previous month
    """

    @property
    def period_type(self) -> str:
        return "monthly"

    def derive_period_end(self, publish_date: date) -> date:
        """
        Derive month end from publication date.
        
        Monthly data is published around the 1st for the previous month.
        """
        first_of_current = publish_date.replace(day=1)
        last_of_prev = first_of_current - timedelta(days=1)
        return last_of_prev

    def validate_date(self, period_end: date) -> bool:
        """Month ending must be last day of month."""
        next_day = period_end + timedelta(days=1)
        return next_day.day == 1

    def format_for_filename(self, period_end: date) -> str:
        """Year-month format: YYYY-MM."""
        return period_end.strftime("%Y-%m")

    def format_for_display(self, period_end: date) -> str:
        """Human readable: Month ending December 2025."""
        return f"Month ending {period_end.strftime('%B %Y')}"


# =============================================================================
# BACKWARD COMPATIBILITY FUNCTION
# =============================================================================


def derive_week_ending_from_publish_date(publish_date: date) -> date:
    """
    Derive week_ending from publish date using WeeklyPeriod strategy.
    
    This is a convenience wrapper for backward compatibility.
    New code should use: resolve_period("weekly").derive_period_end(...)
    """
    return WeeklyPeriod().derive_period_end(publish_date)


# =============================================================================
# INGESTION METADATA & PAYLOAD
# =============================================================================


@dataclass
class IngestionMetadata:
    """
    Metadata about an ingestion source.

    This abstracts over file metadata and API response metadata,
    providing the pipeline with what it needs regardless of source.

    Attributes:
        week_ending: Business period end (Friday for weekly, month-end for monthly)
        file_date: Publication date (Monday for FINRA weekly)
        tier_hint: Tier detected from source (may be None)
        source_name: Canonical identifier (file path, API URL, etc.)
        source_type: "file", "api", "s3", etc.
        period_type: "weekly", "monthly", etc.
    """

    week_ending: date  # Kept as week_ending for backward compat (alias: period_end)
    file_date: date
    tier_hint: str | None = None
    source_name: str = ""
    source_type: str = "file"
    period_type: str = "weekly"
    extra: dict = field(default_factory=dict)

    @property
    def period_end(self) -> date:
        """Alias for week_ending (generic name)."""
        return self.week_ending


@dataclass
class Payload:
    """
    Raw content and metadata from an ingestion source.

    The pipeline receives this and calls parse_finra_content(payload.content)
    to get records. This ensures uniform parsing regardless of source.
    """

    content: str
    metadata: IngestionMetadata


class IngestionError(Exception):
    """Error during ingestion from a source."""

    def __init__(self, message: str, source_type: str, details: dict | None = None):
        super().__init__(message)
        self.source_type = source_type
        self.details = details or {}


# =============================================================================
# SOURCE ABSTRACTION
# =============================================================================


class IngestionSource(ABC):
    """
    Abstract base for ingestion data sources.

    Implementations fetch raw content from their source type.
    The pipeline handles parsing uniformly via parse_finra_content().
    """

    @abstractmethod
    def fetch(self) -> Payload:
        """
        Fetch raw content and metadata from this source.

        Returns:
            Payload with raw PSV content and metadata

        Raises:
            IngestionError: If fetch fails
        """
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return source type identifier."""
        ...


# Source Registry
SOURCE_REGISTRY: dict[str, type[IngestionSource]] = {}


def register_source(name: str):
    """
    Decorator to register a source type.
    
    Usage:
        @register_source("s3")
        class S3Source(IngestionSource): ...
    """
    def decorator(cls: type[IngestionSource]) -> type[IngestionSource]:
        SOURCE_REGISTRY[name] = cls
        return cls
    return decorator


def list_sources() -> list[str]:
    """Return list of registered source types."""
    return list(SOURCE_REGISTRY.keys())


# =============================================================================
# File Source Implementation
# =============================================================================


@register_source("file")
class FileSource(IngestionSource):
    """
    Ingestion source that reads from local PSV files.

    Handles date inference from filename/content.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        week_ending_override: date | None = None,
        file_date_override: date | None = None,
        period_type: str = "weekly",
        **kwargs,  # Accept and ignore extra kwargs for registry compatibility
    ):
        if not file_path:
            raise ValueError("file_path is required for FileSource")
        self.file_path = Path(file_path)
        self.week_ending_override = week_ending_override
        self.file_date_override = file_date_override
        self.period_strategy = resolve_period(period_type)

    @property
    def source_type(self) -> str:
        return "file"

    def fetch(self) -> Payload:
        """Read file content and extract metadata."""
        if not self.file_path.exists():
            raise IngestionError(
                f"File not found: {self.file_path}",
                source_type="file",
                details={"path": str(self.file_path)},
            )

        # Read raw content
        content = self.file_path.read_text(encoding="utf-8")

        # Determine file_date (publication date)
        if self.file_date_override:
            file_date = self.file_date_override
            date_source = "override"
        else:
            # Try filename first, then content
            file_date = extract_file_date_from_filename(self.file_path)
            if file_date:
                date_source = "filename"
            else:
                file_date = extract_file_date_from_content(self.file_path)
                if file_date:
                    date_source = "content"
                else:
                    raise IngestionError(
                        f"Cannot determine file date from {self.file_path}",
                        source_type="file",
                        details={"path": str(self.file_path)},
                    )

        # Determine period end using strategy
        if self.week_ending_override:
            week_ending = self.week_ending_override
        else:
            week_ending = self.period_strategy.derive_period_end(file_date)

        # Try to detect tier from filename
        tier_hint = extract_tier_from_filename(self.file_path)

        metadata = IngestionMetadata(
            week_ending=week_ending,
            file_date=file_date,
            tier_hint=tier_hint,
            source_name=str(self.file_path),
            source_type="file",
            period_type=self.period_strategy.period_type,
            extra={"date_source": date_source},
        )

        return Payload(content=content, metadata=metadata)


# =============================================================================
# API Source Implementation
# =============================================================================


@dataclass
class APIConfig:
    """Configuration for FINRA API access."""

    base_url: str = "https://api.finra.org/data/otc"
    timeout_seconds: int = 30


@register_source("api")
class APISource(IngestionSource):
    """
    Ingestion source that fetches from FINRA OTC API.

    Supports offline mode via mock_content for testing.
    """

    def __init__(
        self,
        tier: str | None = None,
        week_ending: date | None = None,
        config: APIConfig | None = None,
        mock_content: str | None = None,
        period_type: str = "weekly",
        **kwargs,  # Accept and ignore extra kwargs for registry compatibility
    ):
        if not tier:
            raise ValueError("tier is required for APISource")
        if not week_ending:
            raise ValueError("week_ending is required for APISource")
        self.tier = tier
        self.week_ending = week_ending
        self.config = config or APIConfig()
        self.mock_content = mock_content
        self.period_strategy = resolve_period(period_type)

    @property
    def source_type(self) -> str:
        return "api"

    def fetch(self) -> Payload:
        """Fetch content from API (or mock)."""
        if self.mock_content is not None:
            content = self.mock_content
            source_name = f"mock://finra-otc/{self.tier}/{self.week_ending}"
        else:
            content = self._fetch_from_api()
            source_name = f"{self.config.base_url}/{self.tier}/{self.week_ending}"

        metadata = IngestionMetadata(
            week_ending=self.week_ending,
            file_date=date.today(),  # API fetch date
            tier_hint=self.tier,
            source_name=source_name,
            source_type="api",
            period_type=self.period_strategy.period_type,
            extra={"fetched_at": datetime.now().isoformat()},
        )

        return Payload(content=content, metadata=metadata)

    def _fetch_from_api(self) -> str:
        """
        Fetch data from live FINRA API.

        Placeholder - real implementation would use httpx.
        """
        raise IngestionError(
            "Live API fetch not implemented. Use mock_content for offline testing.",
            source_type="api",
            details={"tier": self.tier, "week_ending": str(self.week_ending)},
        )


# =============================================================================
# Source Resolution (Registry-based)
# =============================================================================


def resolve_source(source_type: str = "file", **params) -> IngestionSource:
    """
    Resolve source by type from registry.
    
    This is the registry-based replacement for the old create_source factory.
    Adding a new source (e.g., S3) only requires @register_source("s3") - 
    no changes to this function.
    
    Args:
        source_type: Source identifier (file, api, s3, etc.)
        **params: Parameters passed to source constructor
    
    Returns:
        IngestionSource instance
    
    Raises:
        ValueError: If source_type not in registry
    """
    if source_type not in SOURCE_REGISTRY:
        raise ValueError(
            f"Unknown source: {source_type}. Known: {list(SOURCE_REGISTRY.keys())}"
        )
    return SOURCE_REGISTRY[source_type](**params)


# =============================================================================
# Backward Compatibility: create_source (delegates to resolve_source)
# =============================================================================


def create_source(
    source_type: str = "file",
    *,
    file_path: str | Path | None = None,
    tier: str | None = None,
    week_ending: date | None = None,
    week_ending_override: date | None = None,
    file_date_override: date | None = None,
    mock_content: str | None = None,
    api_config: APIConfig | None = None,
    period_type: str = "weekly",
) -> IngestionSource:
    """
    Factory function to create the appropriate ingestion source.
    
    DEPRECATED: Use resolve_source() for new code.
    This function is kept for backward compatibility.

    Args:
        source_type: "file" or "api" (default: "file")
        file_path: Path to PSV file (required for file source)
        tier: Market tier (required for API source)
        week_ending: Week ending date (required for API source)
        week_ending_override: Override week_ending for file source
        file_date_override: Override file_date for file source
        mock_content: Mock PSV content for API testing
        api_config: API configuration
        period_type: Period strategy (weekly, monthly)

    Returns:
        IngestionSource implementation

    Raises:
        ValueError: If required params missing for source type
    """
    # Delegate to registry-based resolution
    return resolve_source(
        source_type,
        file_path=file_path,
        tier=tier,
        week_ending=week_ending,
        week_ending_override=week_ending_override,
        file_date_override=file_date_override,
        mock_content=mock_content,
        config=api_config,
        period_type=period_type,
    )
