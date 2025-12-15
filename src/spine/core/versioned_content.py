"""Generalized Versioned Content Model for spine-core.

Provides base classes for versioned content tracking.

This module provides abstract versioning patterns that can be applied to
ANY content type - not just chat messages:

- Chat messages (Copilot sessions)
- News headlines (market news, earnings announcements)
- SEC filing sections (risk factors, MD&A)
- LLM prompts (prompt engineering)
- Document chunks (RAG pipelines)
- Annotations (human feedback)

Design inspired by:
- Google Docs version history (track changes, restore, compare)
- Financial Observations (multiple values for same observation: GAAP/Non-GAAP)
- Event Sourcing (immutable history, derive current state)

Key Concepts:
    ContentVersion: A single snapshot of content at a point in time
    VersionedContent: Content with immutable version history
    ContentType: Enum defining the kind of content being versioned

Example:
    # Create versioned news headline
    headline = VersionedContent.create(
        content="Apple beats Q4 estimates",
        content_type=ContentType.NEWS_HEADLINE,
        context={"ticker": "AAPL", "source": "reuters"},
    )

    # Add improved version (LLM rewrote)
    headline.add_version(
        content="Apple Reports Q4 Revenue of $95B, Beats Analyst Estimates by 3%",
        source=ContentSource.LLM_EXPANDED,
        created_by="claude-sonnet",
        improvements=["added specifics", "added percentage"],
    )

    # Access version history
    for v in headline.history:
        print(f"v{v.version}: {v.content[:50]}...")
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from spine.core.timestamps import generate_ulid, utc_now

# ============================================================================
# ENUMS
# ============================================================================


class ContentType(str, Enum):
    """Type of content being versioned.

    Use this to distinguish different content domains while sharing
    the same versioning infrastructure.
    """

    # Chat/Productivity
    CHAT_MESSAGE = "chat_message"
    CHAT_SESSION_TITLE = "chat_session_title"
    CHAT_SUMMARY = "chat_summary"

    # News/Market
    NEWS_HEADLINE = "news_headline"
    NEWS_BODY = "news_body"
    NEWS_SUMMARY = "news_summary"
    EARNINGS_CALL_SEGMENT = "earnings_call_segment"

    # SEC Filings
    SEC_FILING_SECTION = "sec_filing_section"
    SEC_RISK_FACTOR = "sec_risk_factor"
    SEC_MDA = "sec_mda"  # Management Discussion & Analysis
    SEC_FOOTNOTE = "sec_footnote"

    # LLM/AI
    LLM_PROMPT = "llm_prompt"
    LLM_RESPONSE = "llm_response"
    LLM_SYSTEM_PROMPT = "llm_system_prompt"

    # Documents
    DOCUMENT_CHUNK = "document_chunk"
    DOCUMENT_SUMMARY = "document_summary"

    # Annotations
    HUMAN_ANNOTATION = "human_annotation"
    HUMAN_FEEDBACK = "human_feedback"

    # Generic
    TEXT = "text"
    CUSTOM = "custom"


class ContentSource(str, Enum):
    """How a content version was created.

    This is reused across all content types to track provenance.
    """

    # Original content
    ORIGINAL = "original"

    # Human edits
    MANUAL_EDIT = "manual"
    CORRECTION = "correction"
    REDACTED = "redacted"

    # Automated transformations
    GRAMMAR = "grammar"
    AUTO_COMPLETE = "auto_complete"
    AUTO_GENERATED = "auto_generated"
    TEMPLATE = "template"

    # LLM transformations
    LLM_IMPROVED = "llm_improved"
    LLM_CLARIFIED = "llm_clarified"
    LLM_SUMMARIZED = "llm_summarized"
    LLM_EXPANDED = "llm_expanded"
    LLM_TRANSLATED = "llm_translated"
    LLM_REFORMATTED = "llm_reformatted"
    LLM_EXTRACTED = "llm_extracted"

    # Version control operations
    REVERTED = "reverted"
    MERGED = "merged"
    BRANCHED = "branched"


# ============================================================================
# PROTOCOLS
# ============================================================================


@runtime_checkable
class Versionable(Protocol):
    """Protocol for content that can be versioned."""

    @property
    def version(self) -> int:
        """Current version number."""
        ...

    @property
    def content(self) -> str:
        """The actual content."""
        ...

    @property
    def content_hash(self) -> str:
        """Hash for deduplication."""
        ...


@runtime_checkable
class HasVersionHistory(Protocol):
    """Protocol for objects with version history."""

    @property
    def versions(self) -> list[Any]:
        """All versions in order."""
        ...

    @property
    def original(self) -> Any:
        """First version."""
        ...

    @property
    def current(self) -> Any:
        """Latest version."""
        ...

    def add_version(self, content: str, source: str, **kwargs) -> Any:
        """Add a new version."""
        ...


# ============================================================================
# CONTENT VERSION
# ============================================================================


@dataclass(slots=True)
class ContentVersion:
    """
    A single snapshot of content at a point in time.

    Generalizes MessageContent to work with any content type.
    Think of this as a "commit" in version control.

    Attributes:
        version: Version number (1 = original)
        content: The actual text content
        source: How this version was created (ContentSource)
        created_at: When this version was created
        created_by: Who/what created it (user, model name, etc.)
        confidence: Quality/confidence score (0.0 - 1.0)
        supersedes_version: Version this replaces (event sourcing)
        superseded_by_version: Version that replaced this
        improvements: List of improvements in this version
        content_hash: SHA-256 for deduplication
        tokens_estimate: Estimated token count
        metadata: Extensible key-value data

    Example:
        v1 = ContentVersion(
            version=1,
            content="Breaking: Apple beats estimates",
            source=ContentSource.ORIGINAL,
        )

        v2 = ContentVersion(
            version=2,
            content="Breaking: Apple reports Q4 revenue of $95B, beating Wall Street estimates by 3.2%",
            source=ContentSource.LLM_EXPANDED,
            created_by="claude-sonnet",
            supersedes_version=1,
            improvements=["added revenue figure", "added percentage beat"],
        )
    """

    version: int
    content: str
    source: str

    # Provenance
    created_at: datetime = field(default_factory=utc_now)
    created_by: str | None = None

    # Quality metrics
    confidence: float = 1.0

    # Event sourcing chain
    supersedes_version: int | None = None
    superseded_by_version: int | None = None

    # Change tracking
    improvements: list[str] = field(default_factory=list)
    change_notes: str | None = None  # Like Git commit message

    # Content metadata
    content_hash: str = field(default="")
    tokens_estimate: int | None = None
    char_count: int | None = None

    # Extensible metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Compute derived fields."""
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()

        if self.char_count is None and self.content:
            self.char_count = len(self.content)

        if self.tokens_estimate is None and self.content:
            # Rough estimate: ~4 chars per token
            self.tokens_estimate = len(self.content) // 4

    @property
    def is_original(self) -> bool:
        """Is this the first version?"""
        return self.version == 1

    @property
    def is_superseded(self) -> bool:
        """Has this been replaced by a newer version?"""
        return self.superseded_by_version is not None

    @property
    def is_current(self) -> bool:
        """Is this the latest version?"""
        return not self.is_superseded

    @property
    def source_enum(self) -> ContentSource | None:
        """Get source as enum if valid."""
        try:
            return ContentSource(self.source)
        except ValueError:
            return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "version": self.version,
            "content": self.content,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "confidence": self.confidence,
            "supersedes_version": self.supersedes_version,
            "superseded_by_version": self.superseded_by_version,
            "improvements": self.improvements,
            "change_notes": self.change_notes,
            "content_hash": self.content_hash,
            "tokens_estimate": self.tokens_estimate,
            "char_count": self.char_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentVersion:
        """Deserialize from dictionary."""
        return cls(
            version=data["version"],
            content=data["content"],
            source=data["source"],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            confidence=data.get("confidence", 1.0),
            supersedes_version=data.get("supersedes_version"),
            superseded_by_version=data.get("superseded_by_version"),
            improvements=data.get("improvements", []),
            change_notes=data.get("change_notes"),
            content_hash=data.get("content_hash", ""),
            tokens_estimate=data.get("tokens_estimate"),
            char_count=data.get("char_count"),
            metadata=data.get("metadata", {}),
        )


# ============================================================================
# VERSIONED CONTENT (Abstract Base)
# ============================================================================


@dataclass
class VersionedContent:
    """
    Content with immutable version history.

    Like Google Docs version history, but for any content type.
    Uses event sourcing - versions are never deleted, only superseded.

    This is the generalized version of VersionedMessage that works
    for news headlines, SEC filings, prompts, etc.

    Attributes:
        id: Unique identifier (ULID)
        content_type: What kind of content this is
        context: Domain-specific context (ticker, filing_id, etc.)
        _versions: Internal version storage
        created_at: When the content was first created
        updated_at: When last version was added

    Example:
        # News headline
        headline = VersionedContent.create(
            content="AAPL beats estimates",
            content_type=ContentType.NEWS_HEADLINE,
            context={"ticker": "AAPL", "source": "reuters"},
        )

        # SEC risk factor
        risk = VersionedContent.create(
            content="We face significant competition...",
            content_type=ContentType.SEC_RISK_FACTOR,
            context={"cik": "0000320193", "filing_type": "10-K", "section": "1A"},
        )

        # LLM prompt
        prompt = VersionedContent.create(
            content="Summarize {{content}} in {{max_sentences}} sentences.",
            content_type=ContentType.LLM_PROMPT,
            context={"name": "summarize", "category": "summarization"},
        )
    """

    id: str
    content_type: ContentType
    context: dict[str, Any]  # Domain-specific context
    _versions: list[ContentVersion] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    # Optional links to source system
    source_id: str | None = None  # ID in source system
    source_system: str | None = None  # "elasticsearch", "postgres", etc.

    @classmethod
    def create(
        cls,
        content: str,
        content_type: ContentType,
        context: dict[str, Any] | None = None,
        source: ContentSource = ContentSource.ORIGINAL,
        created_by: str | None = None,
        id: str | None = None,
        **metadata,
    ) -> VersionedContent:
        """
        Create new versioned content with initial version.

        Args:
            content: Initial content text
            content_type: Type of content
            context: Domain-specific context (ticker, cik, etc.)
            source: How initial content was created
            created_by: Creator identifier
            id: Optional custom ID
            **metadata: Additional metadata for the version

        Returns:
            New VersionedContent with v1
        """
        v1 = ContentVersion(
            version=1,
            content=content,
            source=source.value if isinstance(source, ContentSource) else source,
            created_by=created_by,
            metadata=metadata,
        )

        return cls(
            id=id or generate_ulid(),
            content_type=content_type,
            context=context or {},
            _versions=[v1],
            created_at=v1.created_at,
            updated_at=v1.created_at,
        )

    def add_version(
        self,
        content: str,
        source: ContentSource | str,
        created_by: str | None = None,
        improvements: list[str] | None = None,
        change_notes: str | None = None,
        confidence: float = 1.0,
        **metadata,
    ) -> ContentVersion:
        """
        Add a new version to the history.

        Like saving a new version in Google Docs. The previous version
        is marked as superseded but not deleted.

        Args:
            content: New content text
            source: How this version was created
            created_by: Creator identifier
            improvements: List of improvements made
            change_notes: Commit message
            confidence: Quality score
            **metadata: Additional metadata

        Returns:
            The new ContentVersion
        """
        current = self.current
        new_version = len(self._versions) + 1

        # Mark current as superseded
        if current:
            current.superseded_by_version = new_version

        new_v = ContentVersion(
            version=new_version,
            content=content,
            source=source.value if isinstance(source, ContentSource) else source,
            created_by=created_by,
            confidence=confidence,
            supersedes_version=current.version if current else None,
            improvements=improvements or [],
            change_notes=change_notes,
            metadata=metadata,
        )

        self._versions.append(new_v)
        self.updated_at = new_v.created_at

        return new_v

    def revert_to(self, version: int, reverted_by: str | None = None) -> ContentVersion:
        """
        Revert to a previous version.

        Creates a NEW version with the old content (not destructive).

        Args:
            version: Version number to revert to
            reverted_by: Who performed the revert

        Returns:
            New version with reverted content
        """
        old_version = self.get_version(version)
        if not old_version:
            raise ValueError(f"Version {version} not found")

        return self.add_version(
            content=old_version.content,
            source=ContentSource.REVERTED,
            created_by=reverted_by,
            change_notes=f"Reverted to version {version}",
            metadata={"reverted_from_version": version},
        )

    @property
    def versions(self) -> list[ContentVersion]:
        """All versions in order."""
        return self._versions

    @property
    def history(self) -> list[ContentVersion]:
        """Alias for versions."""
        return self._versions

    @property
    def original(self) -> ContentVersion | None:
        """First version (v1)."""
        return self._versions[0] if self._versions else None

    @property
    def current(self) -> ContentVersion | None:
        """Latest version."""
        return self._versions[-1] if self._versions else None

    @property
    def content(self) -> str:
        """Current content text."""
        return self.current.content if self.current else ""

    @property
    def version_count(self) -> int:
        """Number of versions."""
        return len(self._versions)

    def get_version(self, version: int) -> ContentVersion | None:
        """Get specific version by number."""
        for v in self._versions:
            if v.version == version:
                return v
        return None

    def diff_versions(
        self,
        from_version: int,
        to_version: int | None = None,
    ) -> dict[str, Any]:
        """
        Get diff information between versions.

        Args:
            from_version: Source version
            to_version: Target version (default: current)

        Returns:
            Diff metadata (not actual text diff - use external lib for that)
        """
        v_from = self.get_version(from_version)
        v_to = self.get_version(to_version) if to_version else self.current

        if not v_from or not v_to:
            raise ValueError("Invalid version numbers")

        return {
            "from_version": from_version,
            "to_version": v_to.version,
            "char_diff": (v_to.char_count or 0) - (v_from.char_count or 0),
            "token_diff": (v_to.tokens_estimate or 0) - (v_from.tokens_estimate or 0),
            "same_content": v_from.content_hash == v_to.content_hash,
            "improvements_added": v_to.improvements,
            "versions_between": v_to.version - from_version - 1,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "content_type": self.content_type.value,
            "context": self.context,
            "versions": [v.to_dict() for v in self._versions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "source_id": self.source_id,
            "source_system": self.source_system,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionedContent:
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            content_type=ContentType(data["content_type"]),
            context=data.get("context", {}),
            _versions=[ContentVersion.from_dict(v) for v in data.get("versions", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            source_id=data.get("source_id"),
            source_system=data.get("source_system"),
        )
