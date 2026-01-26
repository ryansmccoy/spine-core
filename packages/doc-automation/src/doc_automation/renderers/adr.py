"""
ADR (Architecture Decision Record) renderer.

Generates ADR documents from code annotations.
"""

from typing import Any

from doc_automation.renderers.base import BaseRenderer
from doc_automation.parser.section_extractors import SectionExtractor


class ADRRenderer(BaseRenderer):
    """Render ADR documents from knowledge graph.
    
    Features:
        - Generate individual ADR files
        - Create ADR index
        - Extract ADR references from code
        - Link ADRs to implementing code
    
    Tags:
        - renderer
        - adr
        - architecture_decisions
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 5)
    """
    
    doc_type = "ADR"
    template_name = "ADR_template.md"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extractor = SectionExtractor()
    
    def render(self) -> str:
        """Generate ADR index content.
        
        Returns:
            Rendered ADR index document
        """
        # Get ADR fragments
        fragments = self._get_fragments()
        
        # Also include fragments with fragment_type == 'adr'
        all_frags = []
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                if frag_type == 'adr':
                    if frag not in fragments:
                        all_frags.append(frag)
        
        fragments = list(fragments) + all_frags
        
        # Extract ADR references
        adrs = []
        for frag in fragments:
            content = self._get_content(frag)
            source_class = frag.source_class if hasattr(frag, 'source_class') else frag.get('source_class')
            
            refs = self.extractor.extract_adr_references(content)
            for ref in refs:
                adrs.append({
                    'number': ref.number,
                    'title': ref.title,
                    'file_path': ref.file_path,
                    'referenced_by': source_class,
                    'source_link': self._source_link_filter(frag),
                })
        
        # Deduplicate by number
        seen = {}
        for adr in adrs:
            num = adr['number']
            if num not in seen:
                seen[num] = adr
            else:
                # Merge referenced_by
                existing = seen[num]
                if adr['referenced_by'] and adr['referenced_by'] not in str(existing.get('referenced_by', '')):
                    existing['referenced_by'] = f"{existing.get('referenced_by', '')}, {adr['referenced_by']}"
        
        unique_adrs = sorted(seen.values(), key=lambda a: a['number'])
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_adrs"] = len(unique_adrs)
        
        # Try to load template
        try:
            template = self._get_template("ADR_INDEX_template.md")
            content = template.render(
                adrs=unique_adrs,
                fragments=fragments,
                **metadata,
            )
        except Exception:
            content = self._render_inline(unique_adrs, metadata)
        
        return content
    
    def _render_inline(self, adrs: list[dict], metadata: dict[str, Any]) -> str:
        """Render without template (fallback).
        
        Args:
            adrs: List of ADR references
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = [
            "# Architecture Decision Records",
            "",
            "**Record of Architectural Decisions**",
            "",
            f"*Auto-generated from code annotations on {metadata['generated_at'].strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
            "## Index",
            "",
            "| # | Title | Referenced By |",
            "|---|-------|---------------|",
        ]
        
        for adr in adrs:
            ref_by = adr.get('referenced_by', '')
            lines.append(f"| [{adr['number']:03d}]({adr['file_path']}) | {adr['title']} | {ref_by} |")
        
        lines.extend([
            "",
            "---",
            "",
            f"*{metadata['total_adrs']} ADRs referenced in codebase*",
        ])
        
        return "\n".join(lines)
