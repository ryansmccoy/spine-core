"""
Parser module for documentation automation.

Provides tools to parse Python code and extract structured documentation
from extended docstrings.
"""

from doc_automation.parser.ast_walker import ASTWalker, ClassInfo, MethodInfo
from doc_automation.parser.docstring_parser import DocstringParser, DocumentationFragment
from doc_automation.parser.section_extractors import SectionExtractor

__all__ = [
    "ASTWalker",
    "ClassInfo",
    "MethodInfo",
    "DocstringParser",
    "DocumentationFragment",
    "SectionExtractor",
]
