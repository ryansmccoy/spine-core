"""
Unified Source Protocol for data ingestion.

Provides a common interface for all data sources:
- File sources (CSV, PSV, JSON, Parquet)
- HTTP sources (REST APIs)
- Database sources (queries)
- Cloud storage (S3, GCS, SFTP)

Design Principles:
- #3 Registry-Driven: Sources registered by type
- #4 Protocol over Inheritance: Use Protocol for flexibility
- #6 Idempotency: Fetch with change detection
- #13 Observable: Metrics and logging built-in

Usage:
    from spine.framework.sources import FileSource, HttpSource
    from spine.framework.sources.registry import source_registry
    
    # Use directly
    source = FileSource(path="/data/trades.csv")
    result = source.fetch()
    
    # Or via registry
    source = source_registry.get("finra_file")
    result = source.fetch(params={"date": "2026-01-11"})
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from spine.core.errors import SourceError, SpineError
from spine.core.result import Result, Ok, Err


class SourceType(str, Enum):
    """Standard source types."""
    
    FILE = "file"
    HTTP = "http"
    DATABASE = "database"
    S3 = "s3"
    SFTP = "sftp"
    CUSTOM = "custom"


@dataclass
class SourceMetadata:
    """
    Metadata about a source fetch operation.
    
    Used for change detection, caching, and auditing.
    """
    
    # Identity
    source_name: str
    source_type: SourceType
    
    # Timing
    fetched_at: datetime = field(default_factory=datetime.now)
    duration_ms: int | None = None
    
    # Change detection
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_changed: bool = True
    
    # Size
    bytes_fetched: int | None = None
    row_count: int | None = None
    
    # Source-specific
    url: str | None = None
    path: str | None = None
    query: str | None = None
    
    # Context
    params: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        result = {
            "source_name": self.source_name,
            "source_type": self.source_type.value,
            "fetched_at": self.fetched_at.isoformat(),
            "content_changed": self.content_changed,
        }
        for attr in ["duration_ms", "content_hash", "etag", "last_modified",
                     "bytes_fetched", "row_count", "url", "path", "query"]:
            val = getattr(self, attr)
            if val is not None:
                result[attr] = val
        if self.params:
            result["params"] = self.params
        return result


@dataclass
class SourceResult:
    """
    Result of a source fetch operation.
    
    Contains the fetched data plus metadata for auditing.
    """
    
    # Data (one of these should be set)
    data: list[dict[str, Any]] | None = None
    raw_data: bytes | None = None
    
    # Metadata
    metadata: SourceMetadata | None = None
    
    # Status
    success: bool = True
    error: SpineError | None = None
    
    @classmethod
    def ok(
        cls,
        data: list[dict[str, Any]],
        metadata: SourceMetadata,
    ) -> SourceResult:
        """Create successful result with parsed data."""
        metadata.row_count = len(data)
        return cls(data=data, metadata=metadata, success=True)
    
    @classmethod
    def ok_raw(
        cls,
        raw_data: bytes,
        metadata: SourceMetadata,
    ) -> SourceResult:
        """Create successful result with raw bytes."""
        metadata.bytes_fetched = len(raw_data)
        return cls(raw_data=raw_data, metadata=metadata, success=True)
    
    @classmethod
    def fail(
        cls,
        error: SpineError,
        metadata: SourceMetadata | None = None,
    ) -> SourceResult:
        """Create failed result."""
        return cls(error=error, metadata=metadata, success=False)
    
    def to_result(self) -> Result[list[dict[str, Any]]]:
        """Convert to Result type for functional composition."""
        if self.success and self.data is not None:
            return Ok(self.data)
        elif self.error:
            return Err(self.error)
        else:
            return Err(SourceError("No data or error in SourceResult"))
    
    def __len__(self) -> int:
        """Return row count."""
        if self.data is not None:
            return len(self.data)
        return 0


@runtime_checkable
class Source(Protocol):
    """
    Protocol for all data sources.
    
    Implementations must provide:
    - name: Unique identifier for the source
    - source_type: Type classification
    - fetch(): Get all data at once
    
    Optional:
    - stream(): Iterator for large datasets
    - supports_streaming: Whether streaming is available
    """
    
    @property
    def name(self) -> str:
        """Unique source name."""
        ...
    
    @property
    def source_type(self) -> SourceType:
        """Source type classification."""
        ...
    
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """
        Fetch data from the source.
        
        Args:
            params: Optional parameters for the fetch (date filters, etc.)
        
        Returns:
            SourceResult with data or error
        """
        ...


@runtime_checkable
class StreamingSource(Source, Protocol):
    """
    Source that supports streaming for large datasets.
    
    Use for sources that may return millions of rows.
    """
    
    @property
    def supports_streaming(self) -> bool:
        """Whether this source supports streaming."""
        ...
    
    def stream(
        self,
        params: dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Stream data in batches.
        
        Args:
            params: Optional parameters for the fetch
            batch_size: Number of rows per batch
        
        Yields:
            Batches of rows as list of dicts
        """
        ...


@runtime_checkable
class CachingSource(Source, Protocol):
    """
    Source that supports caching with change detection.
    
    Use for sources where data changes infrequently.
    """
    
    def get_cache_key(self, params: dict[str, Any] | None = None) -> str:
        """Generate cache key for the fetch parameters."""
        ...
    
    def has_changed(
        self,
        params: dict[str, Any] | None = None,
        last_hash: str | None = None,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> bool:
        """
        Check if source has changed since last fetch.
        
        Uses content hash, ETag, or Last-Modified as available.
        Returns True if unknown (force fetch).
        """
        ...


# =============================================================================
# BASE SOURCE IMPLEMENTATIONS
# =============================================================================


class BaseSource:
    """
    Base class for source implementations.
    
    Provides common functionality:
    - Metadata creation
    - Error handling
    - Timing
    """
    
    def __init__(
        self,
        name: str,
        source_type: SourceType,
        *,
        domain: str | None = None,
        config: dict[str, Any] | None = None,
    ):
        self._name = name
        self._source_type = source_type
        self._domain = domain
        self._config = config or {}
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def source_type(self) -> SourceType:
        return self._source_type
    
    @property
    def domain(self) -> str | None:
        return self._domain
    
    def _create_metadata(
        self,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> SourceMetadata:
        """Create metadata for a fetch operation."""
        return SourceMetadata(
            source_name=self._name,
            source_type=self._source_type,
            params=params or {},
            **kwargs,
        )
    
    def _wrap_error(
        self,
        error: Exception,
        message: str | None = None,
    ) -> SourceError:
        """Wrap an exception in SourceError with context."""
        if isinstance(error, SourceError):
            return error
        return SourceError(
            message or str(error),
            cause=error,
        ).with_context(source_name=self._name, source_type=self._source_type.value)
    
    @abstractmethod
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """Fetch data from the source."""
        raise NotImplementedError


# =============================================================================
# SOURCE REGISTRY
# =============================================================================


class SourceRegistry:
    """
    Registry for source instances.
    
    Design Principle #3: Registry-Driven Discovery
    
    Usage:
        registry = SourceRegistry()
        registry.register(FileSource(name="trades", path="/data/trades.csv"))
        
        source = registry.get("trades")
        result = source.fetch()
    """
    
    def __init__(self):
        self._sources: dict[str, Source] = {}
        self._factories: dict[str, tuple[type, dict[str, Any]]] = {}
    
    def register(self, source: Source) -> None:
        """Register a source instance."""
        self._sources[source.name] = source
    
    def register_factory(
        self,
        name: str,
        source_class: type,
        config: dict[str, Any],
    ) -> None:
        """
        Register a source factory for lazy instantiation.
        
        Useful when source creation is expensive or
        configuration is loaded at startup.
        """
        self._factories[name] = (source_class, config)
    
    def get(self, name: str) -> Source:
        """
        Get a registered source by name.
        
        Raises:
            SourceError: If source not found
        """
        if name in self._sources:
            return self._sources[name]
        
        if name in self._factories:
            source_class, config = self._factories[name]
            source = source_class(name=name, **config)
            self._sources[name] = source
            return source
        
        raise SourceError(f"Source not found: {name}")
    
    def list_sources(self) -> list[str]:
        """List all registered source names."""
        return sorted(set(self._sources.keys()) | set(self._factories.keys()))
    
    def list_by_type(self, source_type: SourceType) -> list[str]:
        """List sources of a specific type."""
        return [
            name for name, source in self._sources.items()
            if source.source_type == source_type
        ]


# Global registry instance
source_registry = SourceRegistry()


def register_source(source: Source) -> Source:
    """
    Register a source with the global registry.
    
    Can be used as decorator for source classes.
    """
    source_registry.register(source)
    return source


__all__ = [
    # Types
    "SourceType",
    "SourceMetadata",
    "SourceResult",
    # Protocols
    "Source",
    "StreamingSource",
    "CachingSource",
    # Base class
    "BaseSource",
    # Registry
    "SourceRegistry",
    "source_registry",
    "register_source",
]
