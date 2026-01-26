"""
Query interface for documentation knowledge graph.

Provides methods to query the graph for documentation fragments,
filtered by doc-type, tags, section, etc.

Example:
    >>> query = DocumentationQuery(graph)
    >>> manifesto_frags = query.get_fragments_for_doc_type("MANIFESTO")
    >>> len(manifesto_frags)
    5
"""

from typing import Any

from doc_automation.graph.schema import (
    DocFragmentEntity,
    CodeClassEntity,
    IdentifierClaim,
    Relationship,
    ClaimScheme,
)


class DocumentationQuery:
    """Query interface for documentation knowledge graph.
    
    Manifesto:
        The power of a knowledge graph is in querying it. This class
        provides a clean interface to retrieve documentation fragments
        by various criteria - doc-type, tags, section, priority, etc.
        No need to learn a query language; just call methods.
    
    Architecture:
        ```
        Graph Data (entities, claims, relationships)
              │
              ▼
        DocumentationQuery
              │
              ├──► get_fragments_for_doc_type("MANIFESTO")
              │         │
              │         ▼
              │    Filter entities by DOC_TYPE claims
              │         │
              │         ▼
              │    Sort by priority
              │         │
              │         ▼
              │    Return List[DocFragmentEntity]
              │
              ├──► get_fragments_by_tag("core_concept")
              │
              └──► get_fragments_for_section("ARCHITECTURE", "Data Model")
        ```
    
    Features:
        - Query by doc-type (MANIFESTO, FEATURES, etc.)
        - Query by tag
        - Query by section within doc-type
        - Get all fragments for a class
        - Get statistics about the graph
        - Sort results by priority
    
    Examples:
        >>> query = DocumentationQuery(graph)
        >>> frags = query.get_fragments_for_doc_type("MANIFESTO")
        >>> frags[0].priority  # Highest priority first
        10
    
    Tags:
        - graph
        - query
        - retrieval
        - core_infrastructure
    
    Doc-Types:
        - API_REFERENCE (section: "Graph Module", priority: 8)
    """
    
    def __init__(self, graph: dict[str, Any]):
        """Initialize query interface.
        
        Args:
            graph: Graph dict with entities, claims, relationships
        """
        self.entities: list[DocFragmentEntity | CodeClassEntity] = graph.get("entities", [])
        self.claims: list[IdentifierClaim] = graph.get("claims", [])
        self.relationships: list[Relationship] = graph.get("relationships", [])
        
        # Build indexes for efficient querying
        self._entity_by_id: dict[str, Any] = {}
        self._claims_by_entity: dict[str, list[IdentifierClaim]] = {}
        self._claims_by_scheme: dict[str, list[IdentifierClaim]] = {}
        self._rels_by_from: dict[str, list[Relationship]] = {}
        self._rels_by_to: dict[str, list[Relationship]] = {}
        
        self._build_indexes()
    
    def _build_indexes(self) -> None:
        """Build indexes for efficient querying."""
        # Index entities by ID
        for entity in self.entities:
            if isinstance(entity, dict):
                self._entity_by_id[entity["entity_id"]] = entity
            else:
                self._entity_by_id[entity.entity_id] = entity
        
        # Index claims
        for claim in self.claims:
            if isinstance(claim, dict):
                entity_id = claim["entity_id"]
                scheme = claim["scheme"]
            else:
                entity_id = claim.entity_id
                scheme = claim.scheme
            
            # By entity
            if entity_id not in self._claims_by_entity:
                self._claims_by_entity[entity_id] = []
            self._claims_by_entity[entity_id].append(claim)
            
            # By scheme
            if scheme not in self._claims_by_scheme:
                self._claims_by_scheme[scheme] = []
            self._claims_by_scheme[scheme].append(claim)
        
        # Index relationships
        for rel in self.relationships:
            if isinstance(rel, dict):
                from_id = rel["from_entity_id"]
                to_id = rel["to_entity_id"]
            else:
                from_id = rel.from_entity_id
                to_id = rel.to_entity_id
            
            if from_id not in self._rels_by_from:
                self._rels_by_from[from_id] = []
            self._rels_by_from[from_id].append(rel)
            
            if to_id not in self._rels_by_to:
                self._rels_by_to[to_id] = []
            self._rels_by_to[to_id].append(rel)
    
    def get_fragments_for_doc_type(
        self,
        doc_type: str,
        sort_by_priority: bool = True,
    ) -> list[DocFragmentEntity]:
        """Get all fragments tagged for a specific doc type.
        
        Args:
            doc_type: Document type (e.g., "MANIFESTO", "FEATURES")
            sort_by_priority: Whether to sort by priority (highest first)
            
        Returns:
            List of DocFragmentEntity objects
        """
        # Find entities with DOC_TYPE claim matching
        entity_ids = set()
        
        for claim in self._claims_by_scheme.get(ClaimScheme.DOC_TYPE, []):
            identifier = claim["identifier"] if isinstance(claim, dict) else claim.identifier
            if identifier == doc_type:
                entity_id = claim["entity_id"] if isinstance(claim, dict) else claim.entity_id
                entity_ids.add(entity_id)
        
        # Get the entities
        fragments = []
        for entity_id in entity_ids:
            entity = self._entity_by_id.get(entity_id)
            if entity:
                entity_type = entity.get("entity_type") if isinstance(entity, dict) else entity.entity_type
                if entity_type == "DOC_FRAGMENT":
                    fragments.append(entity)
        
        # Sort by priority
        if sort_by_priority:
            fragments.sort(
                key=lambda f: f.get("priority", 5) if isinstance(f, dict) else f.priority,
                reverse=True,
            )
        
        return fragments
    
    def get_fragments_by_tag(
        self,
        tag: str,
        sort_by_priority: bool = True,
    ) -> list[DocFragmentEntity]:
        """Get all fragments with a specific tag.
        
        Args:
            tag: Tag to search for
            sort_by_priority: Whether to sort by priority
            
        Returns:
            List of DocFragmentEntity objects
        """
        entity_ids = set()
        
        for claim in self._claims_by_scheme.get(ClaimScheme.TAG, []):
            identifier = claim["identifier"] if isinstance(claim, dict) else claim.identifier
            if identifier == tag:
                entity_id = claim["entity_id"] if isinstance(claim, dict) else claim.entity_id
                entity_ids.add(entity_id)
        
        fragments = []
        for entity_id in entity_ids:
            entity = self._entity_by_id.get(entity_id)
            if entity:
                entity_type = entity.get("entity_type") if isinstance(entity, dict) else entity.entity_type
                if entity_type == "DOC_FRAGMENT":
                    fragments.append(entity)
        
        if sort_by_priority:
            fragments.sort(
                key=lambda f: f.get("priority", 5) if isinstance(f, dict) else f.priority,
                reverse=True,
            )
        
        return fragments
    
    def get_fragments_for_section(
        self,
        doc_type: str,
        section: str,
    ) -> list[DocFragmentEntity]:
        """Get fragments for a specific section within a doc type.
        
        Args:
            doc_type: Document type
            section: Section name within the doc type
            
        Returns:
            List of DocFragmentEntity objects
        """
        # First get all fragments for doc type
        all_frags = self.get_fragments_for_doc_type(doc_type, sort_by_priority=False)
        
        # Filter by section
        filtered = []
        for frag in all_frags:
            sections = frag.get("sections", {}) if isinstance(frag, dict) else frag.sections
            if sections.get(doc_type) == section:
                filtered.append(frag)
        
        # Sort by priority
        filtered.sort(
            key=lambda f: f.get("priority", 5) if isinstance(f, dict) else f.priority,
            reverse=True,
        )
        
        return filtered
    
    def get_fragments_for_class(
        self,
        class_name: str,
    ) -> list[DocFragmentEntity]:
        """Get all fragments extracted from a specific class.
        
        Args:
            class_name: Name of the class
            
        Returns:
            List of DocFragmentEntity objects
        """
        # Find the class entity
        class_entity = None
        for entity in self.entities:
            entity_type = entity.get("entity_type") if isinstance(entity, dict) else entity.entity_type
            name = entity.get("primary_name") if isinstance(entity, dict) else entity.primary_name
            
            if entity_type == "CODE_CLASS" and name == class_name:
                class_entity = entity
                break
        
        if not class_entity:
            return []
        
        # Find relationships pointing to this class
        class_id = class_entity.get("entity_id") if isinstance(class_entity, dict) else class_entity.entity_id
        
        fragments = []
        for rel in self._rels_by_to.get(class_id, []):
            from_id = rel.get("from_entity_id") if isinstance(rel, dict) else rel.from_entity_id
            entity = self._entity_by_id.get(from_id)
            if entity:
                entity_type = entity.get("entity_type") if isinstance(entity, dict) else entity.entity_type
                if entity_type == "DOC_FRAGMENT":
                    fragments.append(entity)
        
        return fragments
    
    def get_all_doc_types(self) -> list[str]:
        """Get list of all doc types found in the graph.
        
        Returns:
            List of doc type strings
        """
        doc_types = set()
        for claim in self._claims_by_scheme.get(ClaimScheme.DOC_TYPE, []):
            identifier = claim["identifier"] if isinstance(claim, dict) else claim.identifier
            doc_types.add(identifier)
        return sorted(doc_types)
    
    def get_all_tags(self) -> list[str]:
        """Get list of all tags found in the graph.
        
        Returns:
            List of tag strings
        """
        tags = set()
        for claim in self._claims_by_scheme.get(ClaimScheme.TAG, []):
            identifier = claim["identifier"] if isinstance(claim, dict) else claim.identifier
            tags.add(identifier)
        return sorted(tags)
    
    def get_all_classes(self, annotated_only: bool = False) -> list[CodeClassEntity]:
        """Get all code classes in the graph.
        
        Args:
            annotated_only: Only return classes with annotations
            
        Returns:
            List of CodeClassEntity objects
        """
        classes = []
        for entity in self.entities:
            entity_type = entity.get("entity_type") if isinstance(entity, dict) else entity.entity_type
            if entity_type == "CODE_CLASS":
                if annotated_only:
                    is_annotated = entity.get("is_annotated") if isinstance(entity, dict) else entity.is_annotated
                    if is_annotated:
                        classes.append(entity)
                else:
                    classes.append(entity)
        return classes
    
    def get_sections_for_doc_type(self, doc_type: str) -> list[str]:
        """Get all section names used for a doc type.
        
        Args:
            doc_type: Document type
            
        Returns:
            List of section names
        """
        sections = set()
        for claim in self._claims_by_scheme.get(ClaimScheme.DOC_TYPE, []):
            identifier = claim["identifier"] if isinstance(claim, dict) else claim.identifier
            if identifier == doc_type:
                metadata = claim.get("metadata", {}) if isinstance(claim, dict) else claim.metadata
                section = metadata.get("section")
                if section:
                    sections.add(section)
        return sorted(sections)
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the graph.
        
        Returns:
            Dict with statistics
        """
        # Count entities by type
        entity_counts = {"DOC_FRAGMENT": 0, "CODE_CLASS": 0}
        for entity in self.entities:
            entity_type = entity.get("entity_type") if isinstance(entity, dict) else entity.entity_type
            if entity_type in entity_counts:
                entity_counts[entity_type] += 1
        
        # Count claims by scheme
        claim_counts = {}
        for scheme, claims in self._claims_by_scheme.items():
            claim_counts[scheme] = len(claims)
        
        return {
            "total_entities": len(self.entities),
            "entity_counts": entity_counts,
            "total_claims": len(self.claims),
            "claim_counts": claim_counts,
            "total_relationships": len(self.relationships),
            "doc_types": self.get_all_doc_types(),
            "tags": self.get_all_tags(),
        }
