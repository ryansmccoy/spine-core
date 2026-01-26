"""
Documentation Automation Package

Knowledge graph-based documentation system that automatically generates
documentation from code annotations using EntitySpine.

Example:
    >>> from doc_automation import DocumentationOrchestrator
    >>> from pathlib import Path
    >>> orchestrator = DocumentationOrchestrator(Path("."))
    >>> orchestrator.generate_all()
"""

from doc_automation.parser import DocstringParser, ASTWalker
from doc_automation.graph import KnowledgeGraphBuilder, DocumentationQuery
from doc_automation.orchestrator import DocumentationOrchestrator
from doc_automation.config import DocAutomationConfig

__version__ = "0.1.0"

__all__ = [
    "DocstringParser",
    "ASTWalker",
    "KnowledgeGraphBuilder",
    "DocumentationQuery",
    "DocumentationOrchestrator",
    "DocAutomationConfig",
    "__version__",
]
