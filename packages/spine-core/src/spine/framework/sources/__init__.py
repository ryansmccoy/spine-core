"""
Unified Source Protocol package.

Provides a common interface for all data sources.
"""

from spine.framework.sources.protocol import (
    # Types
    SourceType,
    SourceMetadata,
    SourceResult,
    # Protocols
    Source,
    StreamingSource,
    CachingSource,
    # Base class
    BaseSource,
    # Registry
    SourceRegistry,
    source_registry,
    register_source,
)

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
