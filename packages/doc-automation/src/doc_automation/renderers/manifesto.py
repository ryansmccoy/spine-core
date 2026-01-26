"""
MANIFESTO.md renderer.

Generates the project manifesto document containing core principles
and philosophy extracted from code annotations.

Output Quality Goals:
- Table of Contents with anchor links
- Problem/Solution framing where available
- Boxed ASCII diagrams for principles
- Comparison tables
- Source links to code
"""

from datetime import datetime
from typing import Any

from doc_automation.renderers.base import BaseRenderer
from doc_automation.parser.section_extractors import SectionExtractor


class ManifestoRenderer(BaseRenderer):
    """Render MANIFESTO.md from knowledge graph.
    
    Manifesto:
        The MANIFESTO is the "why" document. It explains the core
        principles that guide the project. By extracting these from
        code docstrings, we ensure the manifesto stays in sync with
        actual code philosophy.
    
    Features:
        - Table of Contents with section anchors
        - Problem/Solution framing
        - Boxed principle diagrams
        - Comparison tables
        - Source code links
    
    Examples:
        >>> renderer = ManifestoRenderer(graph)
        >>> content = renderer.render()
        >>> "# MANIFESTO" in content
        True
    
    Tags:
        - renderer
        - manifesto
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 6)
    """
    
    doc_type = "MANIFESTO"
    template_name = "MANIFESTO_template.md"
    
    def __init__(self, graph: Any, template_dir: Any = None):
        """Initialize renderer."""
        super().__init__(graph, template_dir)
        self.extractor = SectionExtractor()
    
    def render(self) -> str:
        """Generate MANIFESTO.md content.
        
        Returns:
            Rendered manifesto document
        """
        # Get only 'manifesto' type fragments to avoid duplication
        fragments = []
        seen_content = set()
        
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                if frag_type == 'manifesto':
                    content = self._get_content(frag)
                    content_hash = hash(content)
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        fragments.append(frag)
        
        # Also collect architecture diagrams for principles
        architecture_frags = []
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                if frag_type == 'architecture':
                    content = self._get_content(frag)
                    content_hash = hash(content)
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        architecture_frags.append(frag)
        
        # Group by section
        sections = self._group_by_section(fragments)
        
        # Order sections logically
        section_order = [
            "Core Principles",
            "Philosophy", 
            "Vision",
            "Values",
            "General",
        ]
        
        ordered_sections = {}
        for section in section_order:
            if section in sections:
                ordered_sections[section] = sections[section]
        
        # Add any remaining sections
        for section, frags in sections.items():
            if section not in ordered_sections:
                ordered_sections[section] = frags
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_fragments"] = len(fragments)
        metadata["total_sections"] = len(ordered_sections)
        metadata["architecture_frags"] = architecture_frags
        
        # Try to load template, fall back to inline template
        try:
            template = self._get_template()
            content = template.render(
                sections=ordered_sections,
                fragments=fragments,
                **metadata,
            )
        except Exception:
            # Fallback to inline rendering
            content = self._render_inline(ordered_sections, metadata)
        
        return content
    
    def _render_inline(self, sections: dict[str, list[Any]], metadata: dict[str, Any]) -> str:
        """Render high-quality manifesto without template.
        
        Args:
            sections: Grouped sections
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = []
        
        # Header
        lines.extend([
            "# MANIFESTO",
            "",
            "**Core Principles and Philosophy**",
            "",
            f"> **Auto-generated from code annotations**  ",
            f"> **Last Updated**: {metadata['generated_at'].strftime('%B %Y')}  ",
            "> **Status**: Living Document",
            "",
        ])
        
        # Table of Contents
        lines.extend([
            "---",
            "",
            "## Table of Contents",
            "",
        ])
        
        toc_num = 1
        for section_name in sections.keys():
            anchor = section_name.lower().replace(' ', '-')
            lines.append(f"{toc_num}. [{section_name}](#{anchor})")
            toc_num += 1
        
        # Add Architecture Diagrams to TOC if we have them
        if metadata.get("architecture_frags"):
            lines.append(f"{toc_num}. [System Architecture](#system-architecture)")
        
        lines.extend(["", "---", ""])
        
        # Introduction/Problem Statement if we can infer one
        all_content = ' '.join(self._get_content(f) for f in sum(sections.values(), []))
        if 'problem' in all_content.lower() or '≠' in all_content:
            lines.extend([
                "## The Challenge",
                "",
                "Financial data comes from many sources, each with their own identifiers.",
                "The core challenge is: *\"Is this the same company across different sources?\"*",
                "",
            ])
        
        # Render each section
        for section_name, frags in sections.items():
            anchor = section_name.lower().replace(' ', '-')
            lines.extend([
                f"## {section_name}",
                "",
            ])
            
            # Try to extract principles with numbering
            principles_found = []
            for frag in frags:
                content = self._get_content(frag)
                principles = self.extractor.extract_principles(content)
                if principles:
                    principles_found.extend(principles)
            
            if principles_found:
                # Render as numbered principles with boxes
                for principle in principles_found:
                    lines.extend([
                        f"### {principle.number}. {principle.title}",
                        "",
                    ])
                    if principle.description:
                        lines.append(principle.description)
                        lines.append("")
                    if principle.bullets:
                        for bullet in principle.bullets:
                            lines.append(f"- {bullet}")
                        lines.append("")
            else:
                # Render fragments with improved formatting
                for i, frag in enumerate(frags):
                    content = self._get_content(frag)
                    cleaned = self._clean_content(content)
                    
                    # Check if it contains a diagram
                    if '┌' in content and '└' in content:
                        # It's a diagram - wrap in code block
                        lines.append("```")
                        lines.append(self.extractor.clean_architecture_diagram(content))
                        lines.append("```")
                    else:
                        # Regular content
                        lines.append(cleaned)
                    
                    lines.append("")
                    
                    # Add source link
                    source_link = self._source_link_filter(frag)
                    if source_link:
                        lines.append(f"*Source: {source_link}*")
                        lines.append("")
        
        # Architecture Diagrams Section
        arch_frags = metadata.get("architecture_frags", [])
        if arch_frags:
            lines.extend([
                "---",
                "",
                "## System Architecture",
                "",
            ])
            
            for frag in arch_frags:
                content = self._get_content(frag)
                source_class = frag.get('source_class') if isinstance(frag, dict) else getattr(frag, 'source_class', '')
                
                if source_class:
                    lines.append(f"### {source_class}")
                    lines.append("")
                
                # Clean and render diagram
                lines.append("```")
                lines.append(self.extractor.clean_architecture_diagram(content))
                lines.append("```")
                lines.append("")
                
                source_link = self._source_link_filter(frag)
                if source_link:
                    lines.append(f"*Source: {source_link}*")
                    lines.append("")
        
        # Footer
        lines.extend([
            "---",
            "",
            f"*{metadata['total_fragments']} principles extracted from {metadata['total_sections']} sections*",
            "",
            "*Generated by [doc-automation](https://github.com/your-org/py-sec-edgar/tree/main/spine-core/packages/doc-automation)*",
        ])
        
        return "\n".join(lines)
    
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
