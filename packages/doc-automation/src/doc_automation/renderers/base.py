"""
Base renderer for documentation generation.

Provides common functionality for all document renderers, including
template loading and graph querying.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from doc_automation.graph.queries import DocumentationQuery


class BaseRenderer(ABC):
    """Base class for document renderers.
    
    Manifesto:
        Renderers transform knowledge graph queries into documents.
        Each renderer knows how to assemble one type of document
        from fragments. Templates handle formatting; renderers handle
        the query logic and data assembly.
    
    Architecture:
        ```
        Graph ──► DocumentationQuery
                       │
                       ▼
               get_fragments_for_doc_type()
                       │
                       ▼
               Renderer._group_by_section()
                       │
                       ▼
               Jinja2 Template
                       │
                       ▼
               Rendered Markdown
        ```
    
    Features:
        - Load Jinja2 templates from configurable directory
        - Query graph for fragments
        - Group fragments by section
        - Add metadata (timestamps, version, etc.)
        - Support custom template overrides
    
    Tags:
        - renderer
        - template
        - jinja2
        - core_infrastructure
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers Module", priority: 7)
    """
    
    # Document type this renderer produces
    doc_type: str = ""
    
    # Template file name
    template_name: str = ""
    
    def __init__(
        self,
        graph: dict[str, Any],
        template_dir: Path | None = None,
    ):
        """Initialize the renderer.
        
        Args:
            graph: Knowledge graph dict
            template_dir: Directory containing templates
        """
        self.graph = graph
        self.query = DocumentationQuery(graph)
        
        # Setup template directory
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates"
        self.template_dir = Path(template_dir)
        
        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        
        # Add custom filters
        self.env.filters['source_link'] = self._source_link_filter
    
    @abstractmethod
    def render(self) -> str:
        """Render the document.
        
        Returns:
            Rendered document content as string
        """
        pass
    
    def _get_template(self, template_name: str | None = None):
        """Load a Jinja2 template.
        
        Args:
            template_name: Template file name (uses self.template_name if not specified)
            
        Returns:
            Jinja2 Template object
        """
        name = template_name or self.template_name
        return self.env.get_template(name)
    
    def _get_fragments(self, sort_by_priority: bool = True) -> list[Any]:
        """Get fragments for this renderer's doc type.
        
        Args:
            sort_by_priority: Whether to sort by priority
            
        Returns:
            List of fragment entities
        """
        return self.query.get_fragments_for_doc_type(
            self.doc_type,
            sort_by_priority=sort_by_priority,
        )
    
    def _group_by_section(self, fragments: list[Any]) -> dict[str, list[Any]]:
        """Group fragments by their section.
        
        Args:
            fragments: List of fragment entities
            
        Returns:
            Dict mapping section name to list of fragments
        """
        sections: dict[str, list[Any]] = {}
        
        for frag in fragments:
            # Get section for this doc type
            frag_sections = frag.sections if hasattr(frag, 'sections') else frag.get('sections', {})
            section = frag_sections.get(self.doc_type, "General")
            
            if section not in sections:
                sections[section] = []
            sections[section].append(frag)
        
        # Sort each section by priority
        for section in sections:
            sections[section].sort(
                key=lambda f: f.priority if hasattr(f, 'priority') else f.get('priority', 5),
                reverse=True,
            )
        
        return sections
    
    def _get_metadata(self) -> dict[str, Any]:
        """Get common metadata for templates.
        
        Returns:
            Dict with metadata
        """
        return {
            "generated_at": datetime.now(),
            "doc_type": self.doc_type,
            "stats": self.query.get_stats(),
        }
    
    def _source_link_filter(self, fragment: Any) -> str:
        """Jinja2 filter to create source link.
        
        Args:
            fragment: Fragment entity
            
        Returns:
            Markdown link to source
        """
        if hasattr(fragment, 'source_file'):
            file_path = fragment.source_file
            line = fragment.source_line
            class_name = fragment.source_class
        else:
            file_path = fragment.get('source_file', '')
            line = fragment.get('source_line')
            class_name = fragment.get('source_class')
        
        if not file_path:
            return ""
        
        # Create relative path
        path = Path(file_path)
        try:
            rel_path = path.relative_to(Path.cwd())
        except ValueError:
            rel_path = path
        
        link_text = class_name if class_name else rel_path.name
        
        if line:
            return f"[`{link_text}`]({rel_path}#L{line})"
        return f"[`{link_text}`]({rel_path})"
    
    def _get_content(self, fragment: Any) -> str:
        """Get content from a fragment.
        
        Args:
            fragment: Fragment entity
            
        Returns:
            Content string
        """
        if hasattr(fragment, 'content'):
            return fragment.content
        return fragment.get('content', '')
    
    def _get_fragment_type(self, fragment: Any) -> str:
        """Get fragment type.
        
        Args:
            fragment: Fragment entity
            
        Returns:
            Fragment type string
        """
        if hasattr(fragment, 'fragment_type'):
            return fragment.fragment_type
        return fragment.get('fragment_type', '')
