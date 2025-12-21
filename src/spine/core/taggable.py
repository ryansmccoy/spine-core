"""Generalized Taggable Content Model for spine-core.

Provides base classes for taggable content entities with multi-dimensional
tagging that can be applied to ANY content type — chat messages, news
articles, SEC filings, LLM prompts, and documents.

Manifesto:
    Content in the spine ecosystem needs multi-dimensional classification
    for discovery, filtering, and similarity matching. Without a shared
    tagging model, each project invents its own taxonomy with incompatible
    structures. TagGroupSet provides:

    - **Orthogonal dimensions:** Independent tag groups (topics, sectors, etc.)
    - **Faceted search:** Multiple independent filters on any axis
    - **Hierarchical taxonomies:** topic > subtopic nesting support
    - **Similarity matching:** Compare tagsets for content similarity

Architecture:
    ::

        TagGroupSet
        ├── TagGroup("tickers", ["AAPL", "MSFT"])
        ├── TagGroup("sectors", ["Technology"])
        ├── TagGroup("event_types", ["earnings"])
        └── TagGroup("sentiment", ["positive"])

        Taggable Protocol → TaggableContent Mixin
              │
              └── Any content class can gain tagging via mixin

Features:
    - **TagGroup:** Named dimension with values (topics, tickers, etc.)
    - **TagGroupSet:** Collection of orthogonal tag dimensions
    - **Taggable:** Protocol for anything that can be tagged
    - **TaggableContent:** Mixin that adds tagging to any content class
    - **Similarity matching:** matches() for content-based discovery

Examples:
    >>> tags = TagGroupSet.create(
    ...     tickers=["AAPL", "MSFT"],
    ...     sectors=["Technology"],
    ...     event_types=["earnings", "guidance"],
    ... )

Tags:
    tagging, faceted-search, taxonomy, content-model, spine-core,
    multi-dimensional, similarity, discovery

Doc-Types:
    - API Reference
    - Content Model Guide
    - Search & Discovery Documentation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from spine.core.timestamps import utc_now

# ============================================================================
# ENUMS
# ============================================================================


class TagDimension(str, Enum):
    """
    Standard tag dimensions that can be applied to any content.

    These are "orthogonal axes" like MetricSpec has (code, category, basis).
    Each dimension captures a different aspect of the content.
    """

    # Universal dimensions
    TOPICS = "topics"
    TECHNOLOGIES = "technologies"
    PROJECTS = "projects"
    ENTITIES = "entities"  # People, companies, organizations
    FILES = "files"

    # Intent/Status dimensions
    INTENT = "intent"
    STATUS = "status"
    PRIORITY = "priority"

    # Market/Financial dimensions
    TICKERS = "tickers"
    SECTORS = "sectors"
    INDUSTRIES = "industries"
    EVENT_TYPES = "event_types"
    REGIONS = "regions"

    # Document dimensions
    FILING_TYPES = "filing_types"
    RISK_CATEGORIES = "risk_categories"
    DEPARTMENTS = "departments"
    SENSITIVITY = "sensitivity"

    # AI/LLM dimensions
    CAPABILITIES = "capabilities"
    MODELS = "models"
    USE_CASES = "use_cases"

    # Custom
    CUSTOM = "custom"


class ExtractionMethod(str, Enum):
    """How tags were extracted."""

    MANUAL = "manual"
    KEYWORD = "keyword"
    REGEX = "regex"
    LLM = "llm"
    NER = "ner"  # Named Entity Recognition
    RULE_BASED = "rule_based"
    INFERRED = "inferred"
    INHERITED = "inherited"  # From parent/related content


# ============================================================================
# PROTOCOLS
# ============================================================================


@runtime_checkable
class Taggable(Protocol):
    """Protocol for content that can be tagged."""

    @property
    def tag_groups(self) -> TagGroupSet:
        """Get the tag groups."""
        ...

    def add_tags(
        self,
        dimension: str,
        values: list[str] | str,
        method: str = "manual",
    ) -> None:
        """Add tags to a dimension."""
        ...


# ============================================================================
# TAG GROUP
# ============================================================================


@dataclass(slots=True)
class TagGroup:
    """
    A single dimension of tags with metadata.

    Think of this as ONE axis in a multi-dimensional space:
    - "tickers" dimension might have values ["AAPL", "MSFT"]
    - "sectors" dimension might have values ["Technology"]

    Attributes:
        dimension: Name of this tag dimension
        values: List of tag values in this dimension
        extraction_method: How these tags were extracted
        confidence: Extraction confidence (0.0 - 1.0)
        extracted_by: Who/what extracted (model name, user, etc.)
        extracted_at: When tags were extracted
        metadata: Additional dimension-specific data
    """

    dimension: str
    values: list[str] = field(default_factory=list)

    # Extraction provenance
    extraction_method: str = "manual"
    confidence: float = 1.0
    extracted_by: str | None = None
    extracted_at: datetime | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize values."""
        # Ensure unique, sorted values
        self.values = sorted(set(self.values))

        if self.extracted_at is None:
            self.extracted_at = utc_now()

    def add(self, *values: str) -> None:
        """Add values to this dimension."""
        for v in values:
            if v not in self.values:
                self.values.append(v)
        self.values.sort()

    def remove(self, *values: str) -> None:
        """Remove values from this dimension."""
        self.values = [v for v in self.values if v not in values]

    def has(self, value: str) -> bool:
        """Check if value exists in this dimension."""
        return value in self.values

    def overlaps(self, other: TagGroup) -> float:
        """
        Calculate overlap with another TagGroup (Jaccard similarity).

        Returns:
            0.0 (no overlap) to 1.0 (identical)
        """
        if not self.values and not other.values:
            return 1.0  # Both empty = identical
        if not self.values or not other.values:
            return 0.0  # One empty = no overlap

        s1, s2 = set(self.values), set(other.values)
        intersection = len(s1 & s2)
        union = len(s1 | s2)

        return intersection / union if union > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "dimension": self.dimension,
            "values": self.values,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "extracted_by": self.extracted_by,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TagGroup:
        """Deserialize from dictionary."""
        return cls(
            dimension=data["dimension"],
            values=data.get("values", []),
            extraction_method=data.get("extraction_method", "manual"),
            confidence=data.get("confidence", 1.0),
            extracted_by=data.get("extracted_by"),
            extracted_at=datetime.fromisoformat(data["extracted_at"]) if data.get("extracted_at") else None,
            metadata=data.get("metadata", {}),
        )


# ============================================================================
# TAG GROUP SET
# ============================================================================


@dataclass
class TagGroupSet:
    """
    Multi-dimensional tag organization.

    Instead of flat tags like ["AAPL", "earnings", "positive"],
    organize into orthogonal dimensions - similar to how MetricSpec has
    code, category, basis, presentation axes.

    Standard Dimensions (can use any or all):
        topics: What is being discussed
        technologies: Tools/frameworks involved
        projects: Which codebase/project
        entities: People/companies mentioned

        tickers: Stock symbols (market content)
        sectors: Market sectors
        event_types: Type of market event

        filing_types: SEC filing types
        risk_categories: Risk factor categories

        intent: User intent
        status: Current state
        priority: Urgency level

    Example:
        # Chat session tags
        tags = TagGroupSet()
        tags.set("topics", ["authentication", "jwt"])
        tags.set("technologies", ["fastapi", "pyjwt"])
        tags.set("intent", "bug-fix")

        # News article tags
        tags = TagGroupSet()
        tags.set("tickers", ["AAPL", "MSFT"])
        tags.set("event_types", ["earnings"])
        tags.set("sentiment", "positive")

        # Find similar content
        similarity = tags.matches(other_tags)
    """

    _groups: dict[str, TagGroup] = field(default_factory=dict)

    # Global extraction metadata
    extraction_method: str | None = None
    extraction_confidence: float = 1.0
    extracted_at: datetime | None = None

    @classmethod
    def create(cls, **dimensions: list[str] | str) -> TagGroupSet:
        """
        Create TagGroupSet from keyword arguments.

        Example:
            tags = TagGroupSet.create(
                tickers=["AAPL", "MSFT"],
                sectors=["Technology"],
                sentiment="positive",
            )
        """
        instance = cls()
        for dim, values in dimensions.items():
            if isinstance(values, str):
                values = [values]
            instance.set(dim, values)
        return instance

    def set(
        self,
        dimension: str,
        values: list[str] | str,
        method: str = "manual",
        confidence: float = 1.0,
        extracted_by: str | None = None,
    ) -> None:
        """
        Set values for a dimension.

        Args:
            dimension: Dimension name (topics, tickers, etc.)
            values: Tag values (list or single string)
            method: Extraction method
            confidence: Extraction confidence
            extracted_by: Extractor identifier
        """
        if isinstance(values, str):
            values = [values]

        self._groups[dimension] = TagGroup(
            dimension=dimension,
            values=values,
            extraction_method=method,
            confidence=confidence,
            extracted_by=extracted_by,
        )

    def add(
        self,
        dimension: str,
        *values: str,
        method: str = "manual",
    ) -> None:
        """
        Add values to a dimension (creates if doesn't exist).
        """
        if dimension not in self._groups:
            self._groups[dimension] = TagGroup(
                dimension=dimension,
                values=[],
                extraction_method=method,
            )
        self._groups[dimension].add(*values)

    def get(self, dimension: str) -> list[str]:
        """Get values for a dimension."""
        if dimension in self._groups:
            return self._groups[dimension].values
        return []

    def has_dimension(self, dimension: str) -> bool:
        """Check if dimension exists."""
        return dimension in self._groups

    def dimensions(self) -> list[str]:
        """List all dimensions."""
        return list(self._groups.keys())

    def all_tags_flat(self) -> list[str]:
        """Get all tags flattened (with dimension prefix)."""
        tags = []
        for dim, group in self._groups.items():
            for v in group.values:
                tags.append(f"{dim}:{v}")
        return tags

    # -------------------------------------------------------------------------
    # Convenience Accessors (Common Dimensions)
    # -------------------------------------------------------------------------

    @property
    def topics(self) -> list[str]:
        return self.get("topics")

    @property
    def technologies(self) -> list[str]:
        return self.get("technologies")

    @property
    def projects(self) -> list[str]:
        return self.get("projects")

    @property
    def entities(self) -> list[str]:
        return self.get("entities")

    @property
    def tickers(self) -> list[str]:
        return self.get("tickers")

    @property
    def sectors(self) -> list[str]:
        return self.get("sectors")

    @property
    def event_types(self) -> list[str]:
        return self.get("event_types")

    @property
    def intent(self) -> str | None:
        vals = self.get("intent")
        return vals[0] if vals else None

    @property
    def status(self) -> str | None:
        vals = self.get("status")
        return vals[0] if vals else None

    @property
    def priority(self) -> str | None:
        vals = self.get("priority")
        return vals[0] if vals else None

    # -------------------------------------------------------------------------
    # Matching / Similarity
    # -------------------------------------------------------------------------

    def matches(
        self,
        other: TagGroupSet,
        weights: dict[str, float] | None = None,
    ) -> float:
        """
        Calculate similarity score with another TagGroupSet.

        Uses weighted Jaccard similarity across dimensions.

        Args:
            other: TagGroupSet to compare
            weights: Optional weights per dimension

        Returns:
            0.0 (no similarity) to 1.0 (identical)
        """
        all_dims = set(self._groups.keys()) | set(other._groups.keys())

        if not all_dims:
            return 1.0  # Both empty = identical

        weights = weights or {}
        total_weight = 0.0
        weighted_similarity = 0.0

        for dim in all_dims:
            w = weights.get(dim, 1.0)
            total_weight += w

            self_group = self._groups.get(dim)
            other_group = other._groups.get(dim)

            if self_group and other_group:
                sim = self_group.overlaps(other_group)
            elif not self_group and not other_group:
                sim = 1.0  # Both missing = identical for this dim
            else:
                sim = 0.0  # One has, one doesn't

            weighted_similarity += w * sim

        return weighted_similarity / total_weight if total_weight > 0 else 0.0

    def filter_match(self, filters: dict[str, list[str]]) -> bool:
        """
        Check if this TagGroupSet matches filter criteria.

        Useful for faceted search - all filter dimensions must have
        at least one matching value.

        Args:
            filters: {dimension: [required_values]}

        Returns:
            True if all filters match
        """
        for dim, required_values in filters.items():
            group = self._groups.get(dim)
            if not group:
                return False

            # At least one required value must be present
            if not any(v in group.values for v in required_values):
                return False

        return True

    # -------------------------------------------------------------------------
    # Merge / Combine
    # -------------------------------------------------------------------------

    def merge(
        self,
        other: TagGroupSet,
        conflict_strategy: str = "union",
    ) -> TagGroupSet:
        """
        Merge with another TagGroupSet.

        Args:
            other: TagGroupSet to merge
            conflict_strategy: 'union', 'replace', or 'keep'

        Returns:
            New merged TagGroupSet
        """
        merged = TagGroupSet()
        merged._groups = {dim: TagGroup.from_dict(g.to_dict()) for dim, g in self._groups.items()}

        for dim, other_group in other._groups.items():
            if dim not in merged._groups:
                merged._groups[dim] = TagGroup.from_dict(other_group.to_dict())
            elif conflict_strategy == "union":
                merged._groups[dim].add(*other_group.values)
            elif conflict_strategy == "replace":
                merged._groups[dim] = TagGroup.from_dict(other_group.to_dict())
            # 'keep' = do nothing, keep original

        return merged

    # -------------------------------------------------------------------------
    # Factory Methods
    # -------------------------------------------------------------------------

    @classmethod
    def from_flat(cls, tags: list[str]) -> TagGroupSet:
        """
        Create from flat list, guessing dimensions.

        Uses heuristics to categorize tags:
        - UPPERCASE 1-5 chars → tickers
        - .py, .js, .ts → files
        - Known tech words → technologies
        - Else → topics
        """
        instance = cls()

        tech_keywords = {
            "python",
            "javascript",
            "typescript",
            "react",
            "fastapi",
            "django",
            "flask",
            "postgresql",
            "elasticsearch",
            "redis",
            "docker",
            "kubernetes",
            "aws",
            "gcp",
            "azure",
            "nodejs",
        }

        intent_keywords = {
            "question",
            "bug-fix",
            "feature",
            "refactor",
            "documentation",
            "debug",
            "review",
            "explain",
            "generate",
        }

        status_keywords = {
            "in-progress",
            "resolved",
            "blocked",
            "deferred",
            "abandoned",
        }

        for tag in tags:
            tag_lower = tag.lower()

            # Check if it's a ticker (UPPERCASE, 1-5 chars)
            if tag.isupper() and 1 <= len(tag) <= 5:
                instance.add("tickers", tag)
            # Check if it's a file reference
            elif any(tag.endswith(ext) for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".md"]):
                instance.add("files", tag)
            # Check if it's a technology
            elif tag_lower in tech_keywords:
                instance.add("technologies", tag_lower)
            # Check if it's an intent
            elif tag_lower in intent_keywords:
                instance.set("intent", [tag_lower])
            # Check if it's a status
            elif tag_lower in status_keywords:
                instance.set("status", [tag_lower])
            # Default to topics
            else:
                instance.add("topics", tag)

        return instance

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "groups": {dim: g.to_dict() for dim, g in self._groups.items()},
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TagGroupSet:
        """Deserialize from dictionary."""
        instance = cls()
        instance._groups = {dim: TagGroup.from_dict(g) for dim, g in data.get("groups", {}).items()}
        instance.extraction_method = data.get("extraction_method")
        instance.extraction_confidence = data.get("extraction_confidence", 1.0)
        instance.extracted_at = datetime.fromisoformat(data["extracted_at"]) if data.get("extracted_at") else None
        return instance

    def __repr__(self) -> str:
        dims = ", ".join(f"{d}={len(g.values)}" for d, g in self._groups.items())
        return f"TagGroupSet({dims})"


# ============================================================================
# TAGGABLE MIXIN
# ============================================================================


@dataclass
class TaggableMixin:
    """
    Mixin that adds tagging capability to any content class.

    Use this to add TagGroupSet support to existing models.

    Example:
        @dataclass
        class NewsArticle(TaggableMixin):
            headline: str
            body: str
            published_at: datetime

        article = NewsArticle(
            headline="Apple beats estimates",
            body="...",
            published_at=datetime.now(),
        )
        article.add_tags("tickers", ["AAPL"])
        article.add_tags("event_types", ["earnings"])
    """

    tag_groups: TagGroupSet = field(default_factory=TagGroupSet)

    def add_tags(
        self,
        dimension: str,
        values: list[str] | str,
        method: str = "manual",
    ) -> None:
        """Add tags to a dimension."""
        if isinstance(values, str):
            values = [values]
        self.tag_groups.add(dimension, *values, method=method)

    def set_tags(
        self,
        dimension: str,
        values: list[str] | str,
        method: str = "manual",
    ) -> None:
        """Set (replace) tags for a dimension."""
        self.tag_groups.set(dimension, values, method=method)

    def get_tags(self, dimension: str) -> list[str]:
        """Get tags for a dimension."""
        return self.tag_groups.get(dimension)

    def matches_tags(
        self,
        other: TaggableMixin,
        weights: dict[str, float] | None = None,
    ) -> float:
        """Calculate tag similarity with another taggable."""
        return self.tag_groups.matches(other.tag_groups, weights)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Example 1: Chat session tags
    chat_tags = TagGroupSet.for_chat(
        topics=["authentication", "jwt", "refresh-tokens"],
        technologies=["fastapi", "pyjwt"],
        projects=["capture-spine"],
        intent="bug-fix",
        status="resolved",
    )

    print(f"Chat tags: {chat_tags}")
    print(f"  Topics: {chat_tags.topics}")
    print(f"  Technologies: {chat_tags.technologies}")
    print(f"  Intent: {chat_tags.intent}")

    # Example 2: News article tags
    news_tags = TagGroupSet.for_news(
        tickers=["AAPL", "MSFT"],
        sectors=["Technology"],
        event_types=["earnings", "guidance"],
        sentiment="positive",
    )

    print(f"\nNews tags: {news_tags}")
    print(f"  Tickers: {news_tags.tickers}")
    print(f"  Event types: {news_tags.event_types}")

    # Example 3: SEC filing tags
    sec_tags = TagGroupSet.for_sec_filing(
        companies=["Apple Inc."],
        filing_types=["10-K"],
        risk_categories=["competition", "supply_chain", "regulatory"],
        regions=["US", "China", "EU"],
    )

    print(f"\nSEC tags: {sec_tags}")
    print(f"  Risk categories: {sec_tags.get('risk_categories')}")

    # Example 4: Similarity matching
    other_chat = TagGroupSet.for_chat(
        topics=["authentication", "oauth"],
        technologies=["fastapi", "authlib"],
        intent="feature",
    )

    similarity = chat_tags.matches(other_chat)
    print(f"\nSimilarity between chat sessions: {similarity:.2f}")

    # Example 5: From flat tags
    flat_tags = ["AAPL", "earnings", "python", "api.py", "bug-fix"]
    inferred = TagGroupSet.from_flat(flat_tags)
    print(f"\nInferred from flat: {inferred}")
    print(f"  Tickers: {inferred.tickers}")
    print(f"  Files: {inferred.get('files')}")

    # Example 6: Merge
    merged = chat_tags.merge(news_tags)
    print(f"\nMerged tags: {merged}")
    print(f"  All dimensions: {merged.dimensions()}")
