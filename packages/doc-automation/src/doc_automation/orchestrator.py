"""
Documentation Orchestrator.

Coordinates the documentation generation process: building the
knowledge graph, running renderers, and writing output files.

Example:
    >>> orchestrator = DocumentationOrchestrator(Path("."))
    >>> orchestrator.generate_all()
    Generated MANIFESTO.md (2.3 KB)
    Generated FEATURES.md (1.8 KB)
    ...
"""

from pathlib import Path
from typing import Any

from doc_automation.config import DocAutomationConfig
from doc_automation.graph.builder import KnowledgeGraphBuilder
from doc_automation.graph.queries import DocumentationQuery
from doc_automation.renderers import (
    ManifestoRenderer,
    FeaturesRenderer,
    ArchitectureRenderer,
    GuardrailsRenderer,
    ADRRenderer,
    ChangelogRenderer,
    APIReferenceRenderer,
)


class DocumentationOrchestrator:
    """Orchestrate documentation generation across all types.
    
    Manifesto:
        One command generates all documentation. The orchestrator
        knows how to build the graph, run all renderers, and write
        output files. No manual steps required.
    
    Architecture:
        ```
        DocumentationOrchestrator
              │
              ├──► KnowledgeGraphBuilder.build()
              │         │
              │         ▼
              │    graph = {entities, claims, relationships}
              │
              ├──► For each doc type:
              │         │
              │         ├──► Renderer.render()
              │         │         │
              │         │         ▼
              │         │    content (string)
              │         │
              │         └──► Write to output_dir/DOC_TYPE.md
              │
              └──► Return summary
        ```
    
    Features:
        - Build knowledge graph once, use for all docs
        - Generate all doc types or specific ones
        - Create output directory structure
        - Report generation statistics
        - Support custom configurations
    
    Examples:
        >>> orch = DocumentationOrchestrator(Path("src"))
        >>> orch.generate_all()
        {'MANIFESTO': 2345, 'FEATURES': 1890, ...}
    
    Guardrails:
        - Do NOT regenerate graph for each doc type
          ✅ Build once, share across renderers
        - Do NOT fail silently on errors
          ✅ Collect and report all errors at end
    
    Tags:
        - orchestrator
        - generation
        - coordination
        - core_infrastructure
    
    Doc-Types:
        - API_REFERENCE (section: "Core Module", priority: 9)
        - ARCHITECTURE (section: "Generation Pipeline", priority: 8)
    """
    
    # Map doc type to renderer class
    RENDERERS = {
        "MANIFESTO": ManifestoRenderer,
        "FEATURES": FeaturesRenderer,
        "ARCHITECTURE": ArchitectureRenderer,
        "GUARDRAILS": GuardrailsRenderer,
        "ADR": ADRRenderer,
        "CHANGELOG": ChangelogRenderer,
        "API_REFERENCE": APIReferenceRenderer,
    }
    
    # Map doc type to output filename
    OUTPUT_FILES = {
        "MANIFESTO": "MANIFESTO.md",
        "FEATURES": "FEATURES.md",
        "ARCHITECTURE": "ARCHITECTURE.md",
        "GUARDRAILS": "GUARDRAILS.md",
        "ADR": "adrs/INDEX.md",
        "CHANGELOG": "CHANGELOG.md",
        "API_REFERENCE": "API_REFERENCE.md",
    }
    
    def __init__(
        self,
        project_root: Path,
        output_dir: Path | None = None,
        config: DocAutomationConfig | None = None,
    ):
        """Initialize the orchestrator.
        
        Args:
            project_root: Root directory to scan for code
            output_dir: Where to write generated docs
            config: Configuration object
        """
        self.project_root = Path(project_root)
        self.output_dir = Path(output_dir) if output_dir else self.project_root / "docs"
        
        if config:
            self.config = config
        else:
            self.config = DocAutomationConfig(
                project_root=self.project_root,
                output_dir=self.output_dir,
            )
        
        self.graph: dict[str, Any] | None = None
        self.errors: list[str] = []
    
    def build_graph(self) -> dict[str, Any]:
        """Build the knowledge graph from code.
        
        Returns:
            Graph dictionary
        """
        print(f"📊 Building knowledge graph from {self.project_root}...")
        
        builder = KnowledgeGraphBuilder(
            self.project_root,
            skip_patterns=self.config.skip_patterns,
        )
        
        self.graph = builder.build()
        
        stats = self.graph.get("stats", {})
        print(f"   Found {stats.get('classes_found', 0)} classes")
        print(f"   {stats.get('annotated_classes', 0)} have extended annotations")
        print(f"   Extracted {stats.get('fragments_extracted', 0)} documentation fragments")
        
        return self.graph
    
    def generate_doc(self, doc_type: str) -> str | None:
        """Generate a single document type.
        
        Args:
            doc_type: Document type to generate (e.g., 'MANIFESTO')
            
        Returns:
            Generated content, or None if failed
        """
        if doc_type not in self.RENDERERS:
            self.errors.append(f"Unknown doc type: {doc_type}")
            return None
        
        if self.graph is None:
            self.build_graph()
        
        renderer_class = self.RENDERERS[doc_type]
        
        try:
            renderer = renderer_class(
                self.graph,
                template_dir=self.config.template_dir,
            )
            content = renderer.render()
            return content
        except Exception as e:
            self.errors.append(f"Error generating {doc_type}: {e}")
            return None
    
    def generate_all(self, doc_types: list[str] | None = None) -> dict[str, int]:
        """Generate all documentation types.
        
        Args:
            doc_types: Specific doc types to generate (all if None)
            
        Returns:
            Dict mapping doc type to content size in bytes
        """
        # Reset errors
        self.errors = []
        
        # Build graph if not already built
        if self.graph is None:
            self.build_graph()
        
        # Determine which docs to generate
        types_to_generate = doc_types or list(self.RENDERERS.keys())
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        for doc_type in types_to_generate:
            print(f"📝 Generating {doc_type}...")
            
            content = self.generate_doc(doc_type)
            
            if content:
                # Write to file
                output_file = self.output_dir / self.OUTPUT_FILES.get(doc_type, f"{doc_type}.md")
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(content, encoding="utf-8")
                
                size = len(content.encode("utf-8"))
                results[doc_type] = size
                print(f"   ✅ {output_file.name} ({size:,} bytes)")
            else:
                results[doc_type] = 0
                print(f"   ❌ Failed to generate {doc_type}")
        
        # Report errors
        if self.errors:
            print("\n⚠️  Errors encountered:")
            for error in self.errors:
                print(f"   - {error}")
        
        # Summary
        total_size = sum(results.values())
        print(f"\n📚 Generated {len([v for v in results.values() if v > 0])} documents ({total_size:,} bytes total)")
        
        return results
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the current graph.
        
        Returns:
            Statistics dictionary
        """
        if self.graph is None:
            self.build_graph()
        
        query = DocumentationQuery(self.graph)
        return query.get_stats()
    
    def validate(self) -> dict[str, Any]:
        """Validate the knowledge graph and annotations.
        
        Returns:
            Validation results
        """
        if self.graph is None:
            self.build_graph()
        
        query = DocumentationQuery(self.graph)
        stats = query.get_stats()
        
        issues = []
        warnings = []
        
        # Check minimum requirements
        if stats["entity_counts"]["DOC_FRAGMENT"] < 1:
            issues.append("No documentation fragments found. Are classes annotated?")
        
        if stats["entity_counts"]["CODE_CLASS"] < 1:
            issues.append("No code classes found. Is project_root correct?")
        
        # Check doc type coverage
        expected_types = ["MANIFESTO", "FEATURES", "ARCHITECTURE", "GUARDRAILS"]
        found_types = stats.get("doc_types", [])
        
        for expected in expected_types:
            if expected not in found_types:
                warnings.append(f"No fragments tagged for {expected}")
        
        # Check tag usage
        if len(stats.get("tags", [])) < 3:
            warnings.append("Very few tags found. Consider adding more for better organization.")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "stats": stats,
        }
