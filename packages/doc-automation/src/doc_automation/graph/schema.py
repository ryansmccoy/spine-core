"""
Schema definitions for documentation knowledge graph.

Defines the entity and relationship types used to model documentation
as a knowledge graph.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass
class DocFragmentEntity:
    """Documentation fragment as a graph entity.
    
    Represents a piece of documentation extracted from code that can
    be assembled into larger documents.
    
    Attributes:
        entity_id: Unique identifier
        primary_name: Human-readable name
        entity_type: Always "DOC_FRAGMENT"
        fragment_type: Type (manifesto, architecture, features, etc.)
        content: The actual documentation content
        format: Content format (markdown, python, ascii_diagram, mermaid)
        source_file: Path to source file
        source_class: Class name (if applicable)
        source_method: Method name (if applicable)
        source_line: Line number in source
        tags: List of tags
        doc_types: Document types this should appear in
        sections: Mapping of doc_type -> section name
        priority: Importance (1-10)
        created_at: When entity was created
    """
    
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    primary_name: str = ""
    entity_type: str = "DOC_FRAGMENT"
    fragment_type: str = ""
    content: str = ""
    format: str = "markdown"
    source_file: str = ""
    source_class: str | None = None
    source_method: str | None = None
    source_line: int | None = None
    tags: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    priority: int = 5
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert entity to dictionary."""
        return {
            "entity_id": self.entity_id,
            "primary_name": self.primary_name,
            "entity_type": self.entity_type,
            "fragment_type": self.fragment_type,
            "content": self.content,
            "format": self.format,
            "source_file": self.source_file,
            "source_class": self.source_class,
            "source_method": self.source_method,
            "source_line": self.source_line,
            "tags": self.tags,
            "doc_types": self.doc_types,
            "sections": self.sections,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CodeClassEntity:
    """Code class as a graph entity.
    
    Represents a Python class that has documentation annotations.
    
    Attributes:
        entity_id: Unique identifier
        primary_name: Class name
        entity_type: Always "CODE_CLASS"
        module: Module path (e.g., 'entityspine.resolver')
        file_path: Path to source file
        line_number: Line number where class is defined
        bases: List of base class names
        is_annotated: Whether class has extended docstring
        created_at: When entity was created
    """
    
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    primary_name: str = ""
    entity_type: str = "CODE_CLASS"
    module: str = ""
    file_path: str = ""
    line_number: int = 0
    bases: list[str] = field(default_factory=list)
    is_annotated: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert entity to dictionary."""
        return {
            "entity_id": self.entity_id,
            "primary_name": self.primary_name,
            "entity_type": self.entity_type,
            "module": self.module,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "bases": self.bases,
            "is_annotated": self.is_annotated,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class IdentifierClaim:
    """An identifier claim on an entity.
    
    Claims represent different ways to identify or categorize an entity.
    For documentation, this includes tags, doc-types, and section assignments.
    
    Attributes:
        claim_id: Unique identifier
        entity_id: ID of entity this claim is for
        scheme: Type of claim (TAG, DOC_TYPE, SECTION, SOURCE_FILE)
        identifier: The identifier value
        confidence: Confidence in this claim (0.0-1.0)
        metadata: Additional claim metadata
        created_at: When claim was created
    """
    
    claim_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str = ""
    scheme: str = ""
    identifier: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert claim to dictionary."""
        return {
            "claim_id": self.claim_id,
            "entity_id": self.entity_id,
            "scheme": self.scheme,
            "identifier": self.identifier,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Relationship:
    """A relationship between two entities.
    
    Represents connections between entities in the documentation graph,
    such as "EXTRACTED_FROM" (fragment → class) or "REFERENCES" (fragment → ADR).
    
    Attributes:
        relationship_id: Unique identifier
        from_entity_id: Source entity ID
        relationship_type: Type of relationship
        to_entity_id: Target entity ID
        source_system: System that created this relationship
        confidence: Confidence in this relationship (0.0-1.0)
        metadata: Additional relationship metadata
        created_at: When relationship was created
    """
    
    relationship_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_entity_id: str = ""
    relationship_type: str = ""
    to_entity_id: str = ""
    source_system: str = "doc_automation"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert relationship to dictionary."""
        return {
            "relationship_id": self.relationship_id,
            "from_entity_id": self.from_entity_id,
            "relationship_type": self.relationship_type,
            "to_entity_id": self.to_entity_id,
            "source_system": self.source_system,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


# Relationship types
class RelationshipType:
    """Standard relationship types for documentation graph."""
    
    EXTRACTED_FROM = "EXTRACTED_FROM"  # Fragment → Code Class
    IMPLEMENTS = "IMPLEMENTS"  # Fragment → Code Interface
    REFERENCES = "REFERENCES"  # Fragment → ADR or other doc
    EXAMPLE_OF = "EXAMPLE_OF"  # Example → Feature
    DEPENDS_ON = "DEPENDS_ON"  # Class → Class
    INHERITS_FROM = "INHERITS_FROM"  # Class → Class
    TAGGED_FOR = "TAGGED_FOR"  # Fragment → Document


# Claim schemes
class ClaimScheme:
    """Standard claim schemes for documentation graph."""
    
    TAG = "TAG"  # Tags for retrieval
    DOC_TYPE = "DOC_TYPE"  # Document types (MANIFESTO, FEATURES, etc.)
    SECTION = "SECTION"  # Section assignment within a doc type
    SOURCE_FILE = "SOURCE_FILE"  # Source file path
    VERSION = "VERSION"  # Code version
