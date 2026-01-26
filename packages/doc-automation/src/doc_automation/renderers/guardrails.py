"""
GUARDRAILS.md renderer.

Generates documentation about what NOT to do - anti-patterns,
constraints, and common mistakes with their corrections.
"""

from typing import Any

from doc_automation.renderers.base import BaseRenderer
from doc_automation.parser.section_extractors import SectionExtractor


class GuardrailsRenderer(BaseRenderer):
    """Render GUARDRAILS.md from knowledge graph.
    
    Features:
        - Extract anti-patterns with "Do NOT"
        - Show correct alternatives with ✅
        - Group by category
        - Include rationale for each guardrail
    
    Tags:
        - renderer
        - guardrails
        - best_practices
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 6)
    """
    
    doc_type = "GUARDRAILS"
    template_name = "GUARDRAILS_template.md"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extractor = SectionExtractor()
    
    def render(self) -> str:
        """Generate GUARDRAILS.md content.
        
        Returns:
            Rendered guardrails document
        """
        # Get guardrails fragments
        fragments = self._get_fragments()
        
        # Also include fragments with fragment_type == 'guardrails'
        all_frags = []
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                if frag_type == 'guardrails':
                    if frag not in fragments:
                        all_frags.append(frag)
        
        fragments = list(fragments) + all_frags
        
        # Extract structured guardrails
        guardrails = []
        for frag in fragments:
            content = self._get_content(frag)
            source_class = frag.source_class if hasattr(frag, 'source_class') else frag.get('source_class')
            
            extracted = self.extractor.extract_guardrails(content)
            for g in extracted:
                g['source_class'] = source_class
                g['source_link'] = self._source_link_filter(frag)
            guardrails.extend(extracted)
        
        # Group by section
        sections = self._group_by_section(fragments)
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_guardrails"] = len(guardrails)
        
        # Try to load template
        try:
            template = self._get_template()
            content = template.render(
                sections=sections,
                guardrails=guardrails,
                fragments=fragments,
                **metadata,
            )
        except Exception:
            content = self._render_inline(guardrails, metadata)
        
        return content
    
    def _render_inline(self, guardrails: list[dict], metadata: dict[str, Any]) -> str:
        """Render without template (fallback).
        
        Args:
            guardrails: List of extracted guardrails
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = [
            "# GUARDRAILS",
            "",
            "**What NOT to Do - Anti-patterns and Constraints**",
            "",
            f"*Auto-generated from code annotations on {metadata['generated_at'].strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
        ]
        
        # Group by source class
        by_class: dict[str, list[dict]] = {}
        for g in guardrails:
            cls = g.get('source_class', 'General')
            if cls not in by_class:
                by_class[cls] = []
            by_class[cls].append(g)
        
        for class_name, class_guardrails in by_class.items():
            lines.append(f"## {class_name}")
            lines.append("")
            
            for g in class_guardrails:
                lines.append(f"### ❌ {g['anti_pattern']}")
                lines.append("")
                
                if g.get('why_bad'):
                    lines.append(f"**Why:** {g['why_bad']}")
                    lines.append("")
                
                if g.get('correct_approach'):
                    lines.append(f"✅ **Instead:** {g['correct_approach']}")
                    lines.append("")
                
                if g.get('source_link'):
                    lines.append(f"*From {g['source_link']}*")
                    lines.append("")
        
        lines.extend([
            "---",
            "",
            f"*{metadata['total_guardrails']} guardrails documented*",
        ])
        
        return "\n".join(lines)
