"""
ARCHITECTURE.md renderer.

Generates architecture documentation with diagrams extracted from
code annotations.

Output Quality Goals:
- Table of Contents with layer navigation
- Layered architecture overview diagram
- Component relationship tables
- Clean ASCII diagram rendering
- Source links to code
"""

from typing import Any

from doc_automation.renderers.base import BaseRenderer
from doc_automation.parser.section_extractors import SectionExtractor


class ArchitectureRenderer(BaseRenderer):
    """Render ARCHITECTURE.md from knowledge graph.
    
    Features:
        - Table of Contents with anchors
        - Layered architecture overview
        - Clean ASCII diagram extraction
        - Component relationship tables
        - Source code links
    
    Tags:
        - renderer
        - architecture
        - diagrams
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 6)
    """
    
    doc_type = "ARCHITECTURE"
    template_name = "ARCHITECTURE_template.md"
    
    def __init__(self, graph: Any, template_dir: Any = None):
        """Initialize renderer."""
        super().__init__(graph, template_dir)
        self.extractor = SectionExtractor()
    
    def render(self) -> str:
        """Generate ARCHITECTURE.md content.
        
        Returns:
            Rendered architecture document
        """
        # Get architecture fragments
        fragments = self._get_fragments()
        
        # Also include fragments with fragment_type == 'architecture'
        seen_content = set()
        all_frags = []
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                if frag_type == 'architecture':
                    content = self._get_content(frag)
                    content_hash = hash(content)
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        all_frags.append(frag)
        
        fragments = all_frags
        
        # Separate diagrams from text based on content
        diagrams = []
        text_frags = []
        
        for frag in fragments:
            content = self._get_content(frag)
            # Check if content contains ASCII box characters
            if '┌' in content or '└' in content or '│' in content:
                diagrams.append(frag)
            else:
                text_frags.append(frag)
        
        # Group text by source class (component)
        components = {}
        for frag in text_frags:
            source_class = frag.get('source_class') if isinstance(frag, dict) else getattr(frag, 'source_class', 'General')
            if source_class not in components:
                components[source_class] = []
            components[source_class].append(frag)
        
        # Group diagrams by source class
        diagram_by_class = {}
        for diag in diagrams:
            source_class = diag.get('source_class') if isinstance(diag, dict) else getattr(diag, 'source_class', 'Overview')
            if source_class not in diagram_by_class:
                diagram_by_class[source_class] = []
            diagram_by_class[source_class].append(diag)
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_diagrams"] = len(diagrams)
        metadata["total_components"] = len(components)
        
        # Try to load template
        try:
            template = self._get_template()
            content = template.render(
                components=components,
                diagram_by_class=diagram_by_class,
                diagrams=diagrams,
                fragments=fragments,
                **metadata,
            )
        except Exception:
            content = self._render_inline(components, diagram_by_class, metadata)
        
        return content
    
    def _render_inline(
        self,
        components: dict[str, list[Any]],
        diagram_by_class: dict[str, list[Any]],
        metadata: dict[str, Any],
    ) -> str:
        """Render high-quality architecture doc without template.
        
        Args:
            components: Text fragments grouped by source class
            diagram_by_class: Diagrams grouped by source class
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = []
        
        # Header
        lines.extend([
            "# ARCHITECTURE",
            "",
            "**System Design and Structure**",
            "",
            f"> **Auto-generated from code annotations**  ",
            f"> **Last Updated**: {metadata['generated_at'].strftime('%B %Y')}  ",
            "> **Status**: Living Document",
            "",
        ])
        
        # Collect all unique class names for TOC
        all_classes = set(components.keys()) | set(diagram_by_class.keys())
        
        # Table of Contents
        lines.extend([
            "---",
            "",
            "## Table of Contents",
            "",
            "1. [System Overview](#system-overview)",
        ])
        
        toc_num = 2
        for class_name in sorted(all_classes):
            anchor = class_name.lower().replace(' ', '-').replace('_', '-')
            lines.append(f"{toc_num}. [{class_name}](#{anchor})")
            toc_num += 1
        
        lines.extend(["", "---", ""])
        
        # System Overview with high-level diagram if available
        lines.extend([
            "## System Overview",
            "",
        ])
        
        # Look for any overview-type diagram
        overview_added = False
        for class_name, diags in diagram_by_class.items():
            for diag in diags:
                content = self._get_content(diag)
                # Check if it looks like a high-level overview
                if ('layer' in content.lower() or 
                    'tier' in content.lower() or 
                    'frontend' in content.lower() or 
                    'api' in content.lower()):
                    lines.append("```")
                    lines.append(self.extractor.clean_architecture_diagram(content))
                    lines.append("```")
                    lines.append("")
                    
                    source_link = self._source_link_filter(diag)
                    if source_link:
                        lines.append(f"*Source: {source_link}*")
                        lines.append("")
                    overview_added = True
                    break
            if overview_added:
                break
        
        if not overview_added:
            lines.append("*See component sections below for detailed diagrams.*")
            lines.append("")
        
        # Component sections - combine diagrams and text for each class
        for class_name in sorted(all_classes):
            anchor = class_name.lower().replace(' ', '-').replace('_', '-')
            lines.extend([
                f"## {class_name}",
                "",
            ])
            
            # First add any diagrams for this class
            if class_name in diagram_by_class:
                for diag in diagram_by_class[class_name]:
                    content = self._get_content(diag)
                    
                    # Try to extract title from the diagram content
                    diagram_title = self._extract_diagram_title(content)
                    if diagram_title:
                        lines.append(f"### {diagram_title}")
                        lines.append("")
                    
                    lines.append("```")
                    lines.append(self.extractor.clean_architecture_diagram(content))
                    lines.append("```")
                    lines.append("")
                    
                    source_link = self._source_link_filter(diag)
                    if source_link:
                        lines.append(f"*Source: {source_link}*")
                        lines.append("")
            
            # Then add text fragments
            if class_name in components:
                for frag in components[class_name]:
                    content = self._get_content(frag)
                    cleaned = self._clean_content(content)
                    lines.append(cleaned)
                    lines.append("")
        
        # Footer
        lines.extend([
            "---",
            "",
            f"*{metadata['total_diagrams']} architectural diagrams from {metadata['total_components']} components*",
            "",
            "*Generated by [doc-automation](https://github.com/your-org/py-sec-edgar/tree/main/spine-core/packages/doc-automation)*",
        ])
        
        return "\n".join(lines)
    
    def _extract_diagram_title(self, content: str) -> str | None:
        """Extract title from ASCII box diagram.
        
        Looks for title row pattern:
        │          TITLE TEXT          │
        
        Args:
            content: Diagram content
            
        Returns:
            Title string or None
        """
        import re
        
        # Look for box title pattern
        pattern = re.compile(r'│\s*([A-Z][A-Z\s]+[A-Z])\s*│', re.MULTILINE)
        match = pattern.search(content)
        if match:
            title = match.group(1).strip()
            # Convert SCREAMING_CASE to Title Case
            return title.title()
        
        return None
    
    def _clean_content(self, content: str) -> str:
        """Clean content for better markdown rendering.
        
        Args:
            content: Raw content from docstring
            
        Returns:
            Cleaned content
        """
        lines = content.splitlines()
        
        # Remove common indentation
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)
        
        if min_indent == float('inf'):
            min_indent = 0
        
        cleaned = []
        for line in lines:
            if line.strip():
                cleaned.append(line[min_indent:])
            else:
                cleaned.append('')
        
        return '\n'.join(cleaned)
