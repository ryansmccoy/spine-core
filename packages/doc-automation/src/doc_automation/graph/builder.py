"""
Knowledge Graph Builder.

Builds a documentation knowledge graph by scanning Python code,
extracting documentation fragments from docstrings, and creating
entities, claims, and relationships.

Example:
    >>> builder = KnowledgeGraphBuilder(Path("src"))
    >>> graph = builder.build()
    >>> len(graph["entities"])
    42
"""

from pathlib import Path
from typing import Any

from doc_automation.parser.ast_walker import ASTWalker, ClassInfo
from doc_automation.parser.docstring_parser import DocstringParser, DocumentationFragment
from doc_automation.graph.schema import (
    DocFragmentEntity,
    CodeClassEntity,
    IdentifierClaim,
    Relationship,
    RelationshipType,
    ClaimScheme,
)


class KnowledgeGraphBuilder:
    """Build documentation knowledge graph from code.
    
    Manifesto:
        Documentation IS code metadata. By modeling docs as a knowledge
        graph, we can query relationships, ensure completeness, and
        generate documents dynamically. The graph is the source of truth
        for what documentation exists and how it relates.
    
    Architecture:
        ```
        Python Source Files
              │
              ▼
        ASTWalker.walk_directory()
              │
              ├──► ClassInfo objects
              │         │
              │         ▼
              │    DocstringParser.parse()
              │         │
              │         ▼
              │    DocumentationFragment objects
              │
              ▼
        For each class:
              ├──► Create CodeClassEntity
              │         │
              │         ▼
              │    For each fragment:
              │         ├──► Create DocFragmentEntity
              │         ├──► Create IdentifierClaims (tags, doc-types)
              │         └──► Create Relationship (EXTRACTED_FROM)
              │
              └──► Graph = {entities, claims, relationships}
        ```
    
    Features:
        - Scan entire project directory
        - Skip test files and virtual environments
        - Create entities for classes and fragments
        - Create claims for tags and doc-types
        - Create relationships linking fragments to classes
        - Track source provenance (file, line, class)
    
    Examples:
        >>> builder = KnowledgeGraphBuilder(Path("src"))
        >>> graph = builder.build()
        >>> graph["entities"][0].entity_type
        'CODE_CLASS'
    
    Guardrails:
        - Do NOT include test files (confusing examples)
          ✅ Skip patterns include "test_"
        - Do NOT fail on malformed Python
          ✅ SyntaxError caught and logged
    
    Tags:
        - graph
        - builder
        - knowledge_graph
        - core_infrastructure
    
    Doc-Types:
        - ARCHITECTURE (section: "Knowledge Graph", priority: 9)
        - API_REFERENCE (section: "Graph Module", priority: 8)
    """
    
    def __init__(
        self,
        project_root: Path,
        skip_patterns: list[str] | None = None,
    ):
        """Initialize the builder.
        
        Args:
            project_root: Root directory to scan
            skip_patterns: File/directory patterns to skip
        """
        self.project_root = Path(project_root)
        self.skip_patterns = skip_patterns or [
            "test_", "__pycache__", ".pyc", "venv", ".venv",
            "node_modules", ".git", "build", "dist", "archive"
        ]
        
        self.walker = ASTWalker()
        self.parser = DocstringParser()
        
        # Graph components
        self.entities: dict[str, DocFragmentEntity | CodeClassEntity] = {}
        self.claims: list[IdentifierClaim] = []
        self.relationships: list[Relationship] = []
    
    def build(self) -> dict[str, Any]:
        """Scan all Python files and build the knowledge graph.
        
        Returns:
            Dict with keys:
                - entities: List of all entities
                - claims: List of all claims
                - relationships: List of all relationships
                - stats: Build statistics
        """
        # Reset graph
        self.entities = {}
        self.claims = []
        self.relationships = []
        
        # Track stats
        stats = {
            "files_scanned": 0,
            "classes_found": 0,
            "annotated_classes": 0,
            "fragments_extracted": 0,
            "tags_found": set(),
            "doc_types_found": set(),
        }
        
        # Find all Python files
        for py_file in self.project_root.rglob("*.py"):
            # Check skip patterns
            if self._should_skip(py_file):
                continue
            
            stats["files_scanned"] += 1
            
            try:
                self._process_file(py_file, stats)
            except (SyntaxError, UnicodeDecodeError) as e:
                # Log but continue
                print(f"Warning: Skipping {py_file}: {e}")
                continue
        
        # Convert sets to lists for serialization
        stats["tags_found"] = list(stats["tags_found"])
        stats["doc_types_found"] = list(stats["doc_types_found"])
        
        return {
            "entities": list(self.entities.values()),
            "claims": self.claims,
            "relationships": self.relationships,
            "stats": stats,
        }
    
    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be skipped
        """
        path_str = str(file_path)
        return any(pattern in path_str for pattern in self.skip_patterns)
    
    def _process_file(self, file_path: Path, stats: dict[str, Any]) -> None:
        """Process a single Python file.
        
        Args:
            file_path: Path to Python file
            stats: Stats dict to update
        """
        classes = self.walker.walk_file(file_path)
        
        for cls in classes:
            stats["classes_found"] += 1
            
            # Create entity for code class
            class_entity = self._create_class_entity(cls)
            self.entities[class_entity.entity_id] = class_entity
            
            # Check for extended docstring
            if cls.has_extended_docstring:
                stats["annotated_classes"] += 1
                
                # Parse docstring into fragments
                source_info = {
                    "file": str(cls.file_path),
                    "class": cls.name,
                    "method": None,
                    "line": cls.line_number,
                }
                
                fragments = self.parser.parse(cls.docstring, source_info)
                
                for frag in fragments:
                    stats["fragments_extracted"] += 1
                    
                    # Create fragment entity
                    frag_entity = self._create_fragment_entity(frag)
                    self.entities[frag_entity.entity_id] = frag_entity
                    
                    # Create claims for tags
                    for tag in frag.tags:
                        stats["tags_found"].add(tag)
                        claim = IdentifierClaim(
                            entity_id=frag_entity.entity_id,
                            scheme=ClaimScheme.TAG,
                            identifier=tag,
                            confidence=1.0,
                        )
                        self.claims.append(claim)
                    
                    # Create claims for doc-types
                    for doc_type in frag.doc_types:
                        stats["doc_types_found"].add(doc_type)
                        section = frag.sections.get(doc_type, "General")
                        claim = IdentifierClaim(
                            entity_id=frag_entity.entity_id,
                            scheme=ClaimScheme.DOC_TYPE,
                            identifier=doc_type,
                            confidence=1.0,
                            metadata={"section": section},
                        )
                        self.claims.append(claim)
                    
                    # Create relationship to class
                    rel = Relationship(
                        from_entity_id=frag_entity.entity_id,
                        relationship_type=RelationshipType.EXTRACTED_FROM,
                        to_entity_id=class_entity.entity_id,
                        confidence=1.0,
                    )
                    self.relationships.append(rel)
    
    def _create_class_entity(self, cls: ClassInfo) -> CodeClassEntity:
        """Create a CodeClassEntity from ClassInfo.
        
        Args:
            cls: ClassInfo object
            
        Returns:
            CodeClassEntity
        """
        return CodeClassEntity(
            primary_name=cls.name,
            module=cls.module,
            file_path=str(cls.file_path),
            line_number=cls.line_number,
            bases=cls.bases,
            is_annotated=cls.has_extended_docstring,
        )
    
    def _create_fragment_entity(self, frag: DocumentationFragment) -> DocFragmentEntity:
        """Create a DocFragmentEntity from DocumentationFragment.
        
        Args:
            frag: DocumentationFragment object
            
        Returns:
            DocFragmentEntity
        """
        # Create readable name
        parts = []
        if frag.source_class:
            parts.append(frag.source_class)
        parts.append(frag.fragment_type)
        name = " - ".join(parts) if parts else frag.fragment_id
        
        return DocFragmentEntity(
            entity_id=frag.fragment_id,
            primary_name=name,
            fragment_type=frag.fragment_type,
            content=frag.content,
            format=frag.format,
            source_file=frag.source_file,
            source_class=frag.source_class,
            source_method=frag.source_method,
            source_line=frag.source_line,
            tags=frag.tags,
            doc_types=frag.doc_types,
            sections=frag.sections,
            priority=frag.priority,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Export graph as dictionary.
        
        Returns:
            Dict representation of the graph
        """
        return {
            "entities": [e.to_dict() for e in self.entities.values()],
            "claims": [c.to_dict() for c in self.claims],
            "relationships": [r.to_dict() for r in self.relationships],
        }
