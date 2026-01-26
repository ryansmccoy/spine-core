"""
CHANGELOG renderer.

Generates changelog from code annotations and git history.
"""

from typing import Any

from doc_automation.renderers.base import BaseRenderer
from doc_automation.parser.section_extractors import SectionExtractor


class ChangelogRenderer(BaseRenderer):
    """Render CHANGELOG.md from knowledge graph.
    
    Features:
        - Extract version history from code annotations
        - Group by version
        - Highlight breaking changes
        - Link to relevant code
    
    Tags:
        - renderer
        - changelog
        - version_history
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 5)
    """
    
    doc_type = "CHANGELOG"
    template_name = "CHANGELOG_template.md"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extractor = SectionExtractor()
    
    def render(self) -> str:
        """Generate CHANGELOG.md content.
        
        Returns:
            Rendered changelog document
        """
        # Get changelog fragments
        fragments = self._get_fragments()
        
        # Also include fragments with fragment_type == 'changelog'
        all_frags = []
        for frag in self.query.entities:
            entity_type = frag.get('entity_type') if isinstance(frag, dict) else getattr(frag, 'entity_type', '')
            if entity_type == 'DOC_FRAGMENT':
                frag_type = frag.get('fragment_type') if isinstance(frag, dict) else getattr(frag, 'fragment_type', '')
                if frag_type == 'changelog':
                    if frag not in fragments:
                        all_frags.append(frag)
        
        fragments = list(fragments) + all_frags
        
        # Extract changelog entries
        entries_by_version: dict[str, list[dict]] = {}
        
        for frag in fragments:
            content = self._get_content(frag)
            source_class = frag.source_class if hasattr(frag, 'source_class') else frag.get('source_class')
            
            entries = self.extractor.extract_changelog_entries(content)
            for entry in entries:
                version = entry.version
                if version not in entries_by_version:
                    entries_by_version[version] = []
                entries_by_version[version].append({
                    'description': entry.description,
                    'breaking': entry.breaking,
                    'source_class': source_class,
                    'source_link': self._source_link_filter(frag),
                })
        
        # Sort versions (newest first)
        sorted_versions = sorted(
            entries_by_version.keys(),
            key=lambda v: [int(x) for x in v.split('.')],
            reverse=True,
        )
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_versions"] = len(sorted_versions)
        metadata["total_entries"] = sum(len(e) for e in entries_by_version.values())
        
        # Try to load template
        try:
            template = self._get_template()
            content = template.render(
                versions=sorted_versions,
                entries_by_version=entries_by_version,
                fragments=fragments,
                **metadata,
            )
        except Exception:
            content = self._render_inline(sorted_versions, entries_by_version, metadata)
        
        return content
    
    def _render_inline(
        self,
        versions: list[str],
        entries_by_version: dict[str, list[dict]],
        metadata: dict[str, Any],
    ) -> str:
        """Render without template (fallback).
        
        Args:
            versions: Sorted list of versions
            entries_by_version: Entries grouped by version
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = [
            "# CHANGELOG",
            "",
            "**Version History**",
            "",
            f"*Auto-generated from code annotations on {metadata['generated_at'].strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
        ]
        
        for version in versions:
            entries = entries_by_version[version]
            has_breaking = any(e['breaking'] for e in entries)
            
            breaking_badge = " ⚠️ BREAKING" if has_breaking else ""
            lines.append(f"## v{version}{breaking_badge}")
            lines.append("")
            
            for entry in entries:
                prefix = "💥" if entry['breaking'] else "-"
                lines.append(f"{prefix} {entry['description']}")
                
                if entry.get('source_class'):
                    lines.append(f"  - *In {entry['source_class']}*")
            
            lines.append("")
        
        lines.extend([
            "---",
            "",
            f"*{metadata['total_entries']} changes across {metadata['total_versions']} versions*",
        ])
        
        return "\n".join(lines)
