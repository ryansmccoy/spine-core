"""
FEATURES.md renderer.

Generates the features document listing all capabilities and
functionality extracted from code annotations.
"""

from datetime import datetime
from typing import Any

from doc_automation.renderers.base import BaseRenderer


class FeaturesRenderer(BaseRenderer):
    """Render FEATURES.md from knowledge graph.
    
    Features:
        - List all features from annotated classes
        - Group by category/section
        - Include code examples where available
        - Link to source code
    
    Tags:
        - renderer
        - features
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 6)
    """
    
    doc_type = "FEATURES"
    template_name = "FEATURES_template.md"
    
    def render(self) -> str:
        """Generate FEATURES.md content.
        
        Returns:
            Rendered features document
        """
        # Get only 'features' type fragments to avoid duplication
        fragments = []
        seen_content = set()
        
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                # Only include 'features' fragment type
                if frag_type == 'features':
                    content = self._get_content(frag)
                    content_hash = hash(content)
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        fragments.append(frag)
        
        # Group by section
        sections = self._group_by_section(fragments)
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_features"] = self._count_features(fragments)
        metadata["total_sections"] = len(sections)
        
        # Try to load template
        try:
            template = self._get_template()
            content = template.render(
                sections=sections,
                fragments=fragments,
                **metadata,
            )
        except Exception:
            content = self._render_inline(sections, metadata)
        
        return content
    
    def _count_features(self, fragments: list[Any]) -> int:
        """Count total features (bullet points).
        
        Args:
            fragments: List of fragments
            
        Returns:
            Count of features
        """
        count = 0
        for frag in fragments:
            content = self._get_content(frag)
            # Count lines starting with -
            count += sum(1 for line in content.split('\n') if line.strip().startswith('-'))
        return count
    
    def _render_inline(self, sections: dict[str, list[Any]], metadata: dict[str, Any]) -> str:
        """Render without template (fallback).
        
        Args:
            sections: Grouped sections
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = [
            "# FEATURES",
            "",
            "**What This Project Can Do**",
            "",
            f"*Auto-generated from code annotations on {metadata['generated_at'].strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
        ]
        
        for section_name, frags in sections.items():
            lines.append(f"## {section_name}")
            lines.append("")
            
            for frag in frags:
                # Get source class name for heading
                source_class = frag.source_class if hasattr(frag, 'source_class') else frag.get('source_class')
                if source_class:
                    lines.append(f"### {source_class}")
                    lines.append("")
                
                content = self._get_content(frag)
                lines.append(content)
                lines.append("")
                
                # Add source link
                source_link = self._source_link_filter(frag)
                if source_link:
                    lines.append(f"*From {source_link}*")
                    lines.append("")
        
        lines.extend([
            "---",
            "",
            f"*{metadata['total_features']} features documented across {metadata['total_sections']} categories*",
        ])
        
        return "\n".join(lines)
