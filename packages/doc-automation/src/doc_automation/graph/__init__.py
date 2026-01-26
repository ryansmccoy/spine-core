"""
Graph module for documentation knowledge graph.

Provides tools to build and query a knowledge graph of documentation
fragments extracted from code.
"""

from doc_automation.graph.schema import (
    DocFragmentEntity,
    CodeClassEntity,
    IdentifierClaim,
    Relationship,
)
from doc_automation.graph.builder import KnowledgeGraphBuilder
from doc_automation.graph.queries import DocumentationQuery

__all__ = [
    "DocFragmentEntity",
    "CodeClassEntity",
    "IdentifierClaim",
    "Relationship",
    "KnowledgeGraphBuilder",
    "DocumentationQuery",
]
