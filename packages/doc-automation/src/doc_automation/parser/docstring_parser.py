"""
Docstring Parser for extended documentation format.

Parses Python docstrings that contain structured documentation sections
like Manifesto, Architecture, Features, etc., and extracts them as
DocumentationFragment objects.

Example:
    >>> parser = DocstringParser()
    >>> fragments = parser.parse(docstring, source_info)
    >>> for frag in fragments:
    ...     print(f"{frag.fragment_type}: {len(frag.content)} chars")
"""

import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DocumentationFragment:
    """A piece of documentation extracted from code.
    
    Represents an atomic unit of documentation that can be assembled
    into larger documents. Fragments are tagged with doc-types to
    indicate which documents they should appear in.
    
    Attributes:
        fragment_id: Unique identifier (generated from source)
        fragment_type: Type of fragment (manifesto, architecture, etc.)
        content: The actual text/code content
        format: Content format (markdown, python, ascii_diagram, mermaid)
        source_file: Path to source file
        source_class: Class name (if from class docstring)
        source_method: Method name (if from method docstring)
        source_line: Line number in source
        tags: Tags for retrieval
        doc_types: Document types this should appear in
        sections: Mapping of doc_type -> section name
        priority: Importance for inclusion (1-10, higher = more important)
        confidence: How confident categorization is (0.0-1.0)
        last_updated: When fragment was extracted
        version: Code version when extracted
    """
    
    fragment_id: str
    fragment_type: str
    content: str
    format: str = "markdown"
    
    # Source provenance
    source_file: str = ""
    source_class: str | None = None
    source_method: str | None = None
    source_line: int | None = None
    
    # Tags for retrieval
    tags: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    
    # Metadata
    priority: int = 5
    confidence: float = 1.0
    last_updated: datetime = field(default_factory=datetime.now)
    version: str = ""


class DocstringParser:
    """Parse extended docstrings into structured fragments.
    
    Manifesto:
        Documentation belongs WITH code. Extended docstrings let us
        embed rich, structured documentation directly in Python classes.
        This parser extracts that structure and makes it queryable.
    
    Architecture:
        ```
        Docstring Text
              │
              ▼
        _split_sections() ──► {"Manifesto": "...", "Features": "..."}
              │
              ▼
        For each section:
              │
              ├──► Create DocumentationFragment
              │        - fragment_type = section name
              │        - content = section text
              │        - format = detect (md/python/diagram)
              │
              └──► Extract metadata
                       - tags from Tags: section
                       - doc_types from Doc-Types: section
                       - sections mapping
        ```
    
    Features:
        - Parse all standard sections (Manifesto, Architecture, Features, etc.)
        - Detect content format (markdown, python code, ASCII diagrams, mermaid)
        - Extract tags and doc-types
        - Generate unique fragment IDs
        - Track source provenance
    
    Examples:
        >>> parser = DocstringParser()
        >>> docstring = '''
        ... Summary line.
        ... 
        ... Manifesto:
        ...     Core principle here.
        ... 
        ... Tags:
        ...     - important
        ...     - core
        ... '''
        >>> frags = parser.parse(docstring, {"file": "test.py", "class": "Test", "line": 1})
        >>> frags[0].fragment_type
        'manifesto'
    
    Guardrails:
        - Do NOT parse None or empty docstrings
          ✅ Return empty list immediately
        - Do NOT fail on malformed sections
          ✅ Handle gracefully, skip malformed
    
    Tags:
        - parser
        - docstring
        - documentation
        - core_infrastructure
    
    Doc-Types:
        - API_REFERENCE (section: "Parser Module", priority: 9)
        - ARCHITECTURE (section: "Documentation Extraction", priority: 7)
    """
    
    # Section markers we recognize
    SECTIONS = [
        "Manifesto",
        "Architecture", 
        "Features",
        "Examples",
        "Performance",
        "Guardrails",
        "Context",
        "ADR",
        "Changelog",
        "Feature-Guide",
        "Unified-Data-Model",
        "Architecture-Doc",
        "Tags",
        "Doc-Types",
    ]
    
    # Map section names to fragment types
    SECTION_TO_FRAGMENT_TYPE = {
        "Manifesto": "manifesto",
        "Architecture": "architecture",
        "Features": "features",
        "Examples": "examples",
        "Performance": "performance",
        "Guardrails": "guardrails",
        "Context": "context",
        "ADR": "adr",
        "Changelog": "changelog",
        "Feature-Guide": "feature_guide",
        "Unified-Data-Model": "data_model",
        "Architecture-Doc": "architecture_doc",
    }
    
    def parse(self, docstring: str, source_info: dict[str, Any]) -> list[DocumentationFragment]:
        """Parse docstring into fragments.
        
        Args:
            docstring: The docstring text to parse
            source_info: Source information dict with keys:
                - file: Source file path
                - class: Class name (optional)
                - method: Method name (optional)
                - line: Line number
                
        Returns:
            List of DocumentationFragment objects
        """
        if not docstring:
            return []
        
        # Split into sections
        sections = self._split_sections(docstring)
        
        # Extract metadata from Tags and Doc-Types sections
        tags = self._extract_tags(sections)
        doc_types = self._extract_doc_types(sections)
        section_mappings = self._extract_section_mappings(sections)
        
        # Create fragments for each documentation section
        fragments = []
        
        for section_name, fragment_type in self.SECTION_TO_FRAGMENT_TYPE.items():
            if section_name in sections:
                content = sections[section_name]
                
                frag = DocumentationFragment(
                    fragment_id=self._generate_id(source_info, fragment_type),
                    fragment_type=fragment_type,
                    content=content,
                    format=self._detect_format(content),
                    source_file=source_info.get("file", ""),
                    source_class=source_info.get("class"),
                    source_method=source_info.get("method"),
                    source_line=source_info.get("line"),
                    tags=tags.copy(),
                    doc_types=doc_types.copy(),
                    sections=section_mappings.copy(),
                    priority=self._get_priority(section_mappings, fragment_type),
                    confidence=1.0,
                )
                fragments.append(frag)
        
        # Also create a summary fragment if there's content before first section
        if "summary" in sections and sections["summary"]:
            frag = DocumentationFragment(
                fragment_id=self._generate_id(source_info, "summary"),
                fragment_type="summary",
                content=sections["summary"],
                format="markdown",
                source_file=source_info.get("file", ""),
                source_class=source_info.get("class"),
                source_method=source_info.get("method"),
                source_line=source_info.get("line"),
                tags=tags.copy(),
                doc_types=doc_types.copy(),
                sections=section_mappings.copy(),
                priority=3,  # Summaries are lower priority
                confidence=1.0,
            )
            fragments.append(frag)
        
        return fragments
    
    def _split_sections(self, docstring: str) -> dict[str, str]:
        """Split docstring into sections.
        
        Args:
            docstring: Full docstring text
            
        Returns:
            Dict mapping section name to content
        """
        sections = {}
        current_section = "summary"
        current_content: list[str] = []
        
        # Build regex pattern for section headers
        section_pattern = re.compile(
            r"^\s*(" + "|".join(re.escape(s) for s in self.SECTIONS) + r"):\s*$",
            re.MULTILINE
        )
        
        for line in docstring.splitlines():
            # Check if line is a section header
            stripped = line.strip()
            match = section_pattern.match(line) or (stripped.rstrip(":") in self.SECTIONS and stripped.endswith(":"))
            
            if stripped.rstrip(":") in self.SECTIONS and stripped.endswith(":"):
                # Save previous section
                if current_content:
                    sections[current_section] = "\n".join(current_content).strip()
                
                # Start new section
                current_section = stripped.rstrip(":")
                current_content = []
            else:
                current_content.append(line)
        
        # Save last section
        if current_content:
            sections[current_section] = "\n".join(current_content).strip()
        
        return sections
    
    def _extract_tags(self, sections: dict[str, str]) -> list[str]:
        """Extract tags from Tags section.
        
        Args:
            sections: Dict of section content
            
        Returns:
            List of tag strings
        """
        if "Tags" not in sections:
            return []
        
        tags = []
        for line in sections["Tags"].splitlines():
            line = line.strip()
            if line.startswith("-"):
                tag = line[1:].strip()
                if tag:
                    tags.append(tag)
        
        return tags
    
    def _extract_doc_types(self, sections: dict[str, str]) -> list[str]:
        """Extract doc types from Doc-Types section.
        
        Args:
            sections: Dict of section content
            
        Returns:
            List of doc type strings (e.g., ['MANIFESTO', 'FEATURES'])
        """
        if "Doc-Types" not in sections:
            return []
        
        doc_types = []
        for line in sections["Doc-Types"].splitlines():
            line = line.strip()
            if line.startswith("-"):
                # Parse: "- MANIFESTO (section: 'Core', priority: 10)"
                parts = line[1:].strip().split("(")
                doc_type = parts[0].strip()
                if doc_type:
                    doc_types.append(doc_type)
        
        return doc_types
    
    def _extract_section_mappings(self, sections: dict[str, str]) -> dict[str, str]:
        """Extract section mappings from Doc-Types section.
        
        Args:
            sections: Dict of section content
            
        Returns:
            Dict mapping doc type to section name
        """
        if "Doc-Types" not in sections:
            return {}
        
        mappings = {}
        for line in sections["Doc-Types"].splitlines():
            line = line.strip()
            if line.startswith("-"):
                # Parse: "- MANIFESTO (section: 'Core Principles', priority: 10)"
                match = re.search(r"(\w+)\s*\(.*?section:\s*['\"]?([^'\"]+)['\"]?", line)
                if match:
                    doc_type = match.group(1)
                    section = match.group(2).strip()
                    mappings[doc_type] = section
        
        return mappings
    
    def _get_priority(self, section_mappings: dict[str, str], fragment_type: str) -> int:
        """Get priority for fragment type.
        
        Args:
            section_mappings: Section mapping dict (may contain priority info)
            fragment_type: The fragment type
            
        Returns:
            Priority value 1-10
        """
        # Default priorities by fragment type
        default_priorities = {
            "manifesto": 10,
            "architecture": 8,
            "features": 7,
            "guardrails": 6,
            "examples": 5,
            "context": 4,
            "performance": 4,
            "adr": 3,
            "changelog": 3,
            "summary": 2,
        }
        
        return default_priorities.get(fragment_type, 5)
    
    def _detect_format(self, content: str) -> str:
        """Detect content format.
        
        Args:
            content: Content string
            
        Returns:
            Format string: 'markdown', 'python', 'ascii_diagram', or 'mermaid'
        """
        if "```mermaid" in content:
            return "mermaid"
        elif "```python" in content or ">>>" in content:
            return "python"
        elif self._looks_like_ascii_diagram(content):
            return "ascii_diagram"
        else:
            return "markdown"
    
    def _looks_like_ascii_diagram(self, content: str) -> bool:
        """Check if content looks like an ASCII diagram.
        
        Args:
            content: Content string
            
        Returns:
            True if content appears to be ASCII art/diagram
        """
        # Box drawing characters and common diagram elements
        indicators = ['┌', '└', '│', '─', '→', '↓', '▼', '┬', '┴', '├', '┤', '╔', '╗', '╚', '╝']
        
        # Count indicator chars
        count = sum(1 for char in content if char in indicators)
        
        # If more than 5 diagram chars, probably a diagram
        return count > 5
    
    def _generate_id(self, source_info: dict[str, Any], fragment_type: str) -> str:
        """Generate unique fragment ID.
        
        Args:
            source_info: Source information dict
            fragment_type: Type of fragment
            
        Returns:
            Unique ID string
        """
        parts = [
            source_info.get("file", "unknown"),
            source_info.get("class", ""),
            source_info.get("method", ""),
            fragment_type,
        ]
        
        # Create hash for uniqueness
        content = ":".join(str(p) for p in parts if p)
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
        
        # Build readable ID
        readable_parts = [p for p in parts[:3] if p]
        readable = ".".join(readable_parts) if readable_parts else "unknown"
        
        return f"{readable}:{fragment_type}:{hash_suffix}"
