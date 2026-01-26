"""
API Reference renderer.

Generates API documentation from class signatures and docstrings.
"""

from typing import Any

from doc_automation.renderers.base import BaseRenderer


class APIReferenceRenderer(BaseRenderer):
    """Render API_REFERENCE.md from knowledge graph.
    
    Features:
        - List all public classes
        - Show method signatures
        - Include docstring summaries
        - Group by module
    
    Tags:
        - renderer
        - api_reference
        - documentation
    
    Doc-Types:
        - API_REFERENCE (section: "Renderers", priority: 5)
    """
    
    doc_type = "API_REFERENCE"
    template_name = "API_REFERENCE_template.md"
    
    def render(self) -> str:
        """Generate API_REFERENCE.md content.
        
        Returns:
            Rendered API reference document
        """
        # Get all annotated classes
        classes = self.query.get_all_classes(annotated_only=True)
        
        # Group by module
        by_module: dict[str, list[Any]] = {}
        for cls in classes:
            module = cls.module if hasattr(cls, 'module') else cls.get('module', 'Unknown')
            if module not in by_module:
                by_module[module] = []
            by_module[module].append(cls)
        
        # Sort modules
        sorted_modules = sorted(by_module.keys())
        
        # Get metadata
        metadata = self._get_metadata()
        metadata["total_classes"] = len(classes)
        metadata["total_modules"] = len(sorted_modules)
        
        # Try to load template
        try:
            template = self._get_template()
            content = template.render(
                modules=sorted_modules,
                by_module=by_module,
                classes=classes,
                **metadata,
            )
        except Exception:
            content = self._render_inline(sorted_modules, by_module, metadata)
        
        return content
    
    def _render_inline(
        self,
        modules: list[str],
        by_module: dict[str, list[Any]],
        metadata: dict[str, Any],
    ) -> str:
        """Render without template (fallback).
        
        Args:
            modules: Sorted list of modules
            by_module: Classes grouped by module
            metadata: Metadata dict
            
        Returns:
            Rendered content
        """
        lines = [
            "# API Reference",
            "",
            "**Public API Documentation**",
            "",
            f"*Auto-generated from code annotations on {metadata['generated_at'].strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
            "## Table of Contents",
            "",
        ]
        
        # TOC
        for module in modules:
            lines.append(f"- [{module}](#{module.replace('.', '')})")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Each module
        for module in modules:
            lines.append(f"## {module}")
            lines.append("")
            
            for cls in by_module[module]:
                name = cls.primary_name if hasattr(cls, 'primary_name') else cls.get('primary_name', 'Unknown')
                file_path = cls.file_path if hasattr(cls, 'file_path') else cls.get('file_path', '')
                line_no = cls.line_number if hasattr(cls, 'line_number') else cls.get('line_number', 0)
                
                lines.append(f"### `{name}`")
                lines.append("")
                
                if file_path:
                    lines.append(f"*Defined in [{file_path}]({file_path}#L{line_no})*")
                    lines.append("")
                
                # Get fragments for this class
                frags = self.query.get_fragments_for_class(name)
                
                # Find summary fragment
                for frag in frags:
                    frag_type = frag.fragment_type if hasattr(frag, 'fragment_type') else frag.get('fragment_type', '')
                    if frag_type == 'summary':
                        content = frag.content if hasattr(frag, 'content') else frag.get('content', '')
                        lines.append(content)
                        lines.append("")
                        break
        
        lines.extend([
            "---",
            "",
            f"*{metadata['total_classes']} classes across {metadata['total_modules']} modules*",
        ])
        
        return "\n".join(lines)
