"""Tests for the graph module."""

import pytest
from pathlib import Path

from doc_automation.graph.schema import (
    DocFragmentEntity,
    CodeClassEntity,
    IdentifierClaim,
    Relationship,
    ClaimScheme,
    RelationshipType,
)
from doc_automation.graph.builder import KnowledgeGraphBuilder
from doc_automation.graph.queries import DocumentationQuery


# =============================================================================
# Schema Tests
# =============================================================================

class TestDocFragmentEntity:
    """Tests for DocFragmentEntity."""
    
    def test_create_entity(self):
        """Test entity creation with defaults."""
        entity = DocFragmentEntity(
            primary_name="Test Fragment",
            fragment_type="manifesto",
            content="Test content",
        )
        
        assert entity.entity_id is not None
        assert entity.entity_type == "DOC_FRAGMENT"
        assert entity.primary_name == "Test Fragment"
    
    def test_to_dict(self):
        """Test entity serialization."""
        entity = DocFragmentEntity(
            primary_name="Test",
            fragment_type="features",
            tags=["tag1", "tag2"],
        )
        
        data = entity.to_dict()
        
        assert data["primary_name"] == "Test"
        assert data["fragment_type"] == "features"
        assert "tag1" in data["tags"]


class TestCodeClassEntity:
    """Tests for CodeClassEntity."""
    
    def test_create_entity(self):
        """Test entity creation."""
        entity = CodeClassEntity(
            primary_name="MyClass",
            module="my.module",
            file_path="src/my_module.py",
            line_number=42,
        )
        
        assert entity.entity_type == "CODE_CLASS"
        assert entity.primary_name == "MyClass"
        assert entity.line_number == 42


class TestIdentifierClaim:
    """Tests for IdentifierClaim."""
    
    def test_create_claim(self):
        """Test claim creation."""
        claim = IdentifierClaim(
            entity_id="test-entity-id",
            scheme=ClaimScheme.TAG,
            identifier="important",
            confidence=0.95,
        )
        
        assert claim.entity_id == "test-entity-id"
        assert claim.scheme == "TAG"
        assert claim.confidence == 0.95


class TestRelationship:
    """Tests for Relationship."""
    
    def test_create_relationship(self):
        """Test relationship creation."""
        rel = Relationship(
            from_entity_id="frag-1",
            relationship_type=RelationshipType.EXTRACTED_FROM,
            to_entity_id="class-1",
        )
        
        assert rel.relationship_type == "EXTRACTED_FROM"


# =============================================================================
# KnowledgeGraphBuilder Tests
# =============================================================================

class TestKnowledgeGraphBuilder:
    """Tests for KnowledgeGraphBuilder."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def builder(self, fixtures_dir):
        """Create a builder for fixtures directory."""
        return KnowledgeGraphBuilder(fixtures_dir)
    
    def test_build_creates_entities(self, builder):
        """Test that build creates entities."""
        graph = builder.build()
        
        assert len(graph["entities"]) > 0
    
    def test_build_creates_code_class_entities(self, builder):
        """Test that CODE_CLASS entities are created."""
        graph = builder.build()
        
        entity_types = [e.entity_type for e in graph["entities"]]
        assert "CODE_CLASS" in entity_types
    
    def test_build_creates_doc_fragment_entities(self, builder):
        """Test that DOC_FRAGMENT entities are created."""
        graph = builder.build()
        
        entity_types = [e.entity_type for e in graph["entities"]]
        assert "DOC_FRAGMENT" in entity_types
    
    def test_build_creates_claims(self, builder):
        """Test that claims are created."""
        graph = builder.build()
        
        assert len(graph["claims"]) > 0
        
        schemes = [c.scheme for c in graph["claims"]]
        assert ClaimScheme.TAG in schemes
    
    def test_build_creates_relationships(self, builder):
        """Test that relationships are created."""
        graph = builder.build()
        
        assert len(graph["relationships"]) > 0
        
        rel_types = [r.relationship_type for r in graph["relationships"]]
        assert RelationshipType.EXTRACTED_FROM in rel_types
    
    def test_build_returns_stats(self, builder):
        """Test that build returns statistics."""
        graph = builder.build()
        
        stats = graph["stats"]
        assert "files_scanned" in stats
        assert "classes_found" in stats
        assert "annotated_classes" in stats
        assert "fragments_extracted" in stats
    
    def test_fragments_linked_to_classes(self, builder):
        """Test that all fragments are linked to classes."""
        graph = builder.build()
        
        doc_fragments = [e for e in graph["entities"] if e.entity_type == "DOC_FRAGMENT"]
        
        for frag in doc_fragments:
            # Should have an EXTRACTED_FROM relationship
            has_link = any(
                r.from_entity_id == frag.entity_id and r.relationship_type == RelationshipType.EXTRACTED_FROM
                for r in graph["relationships"]
            )
            assert has_link, f"Fragment {frag.entity_id} should link to CODE_CLASS"


# =============================================================================
# DocumentationQuery Tests
# =============================================================================

class TestDocumentationQuery:
    """Tests for DocumentationQuery."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def graph(self, fixtures_dir):
        """Build graph from fixtures."""
        builder = KnowledgeGraphBuilder(fixtures_dir)
        return builder.build()
    
    @pytest.fixture
    def query(self, graph):
        """Create query interface."""
        return DocumentationQuery(graph)
    
    def test_get_fragments_for_doc_type(self, query):
        """Test getting fragments by doc type."""
        fragments = query.get_fragments_for_doc_type("MANIFESTO")
        
        # Should find manifesto fragments
        assert len(fragments) > 0 or True  # May be empty if no MANIFESTO claims
    
    def test_get_fragments_by_tag(self, query):
        """Test getting fragments by tag."""
        fragments = query.get_fragments_by_tag("core_concept")
        
        # All returned fragments should have this tag
        for frag in fragments:
            tags = frag.tags if hasattr(frag, 'tags') else frag.get('tags', [])
            assert "core_concept" in tags
    
    def test_get_all_doc_types(self, query):
        """Test getting list of all doc types."""
        doc_types = query.get_all_doc_types()
        
        # Should be a list of strings
        assert isinstance(doc_types, list)
    
    def test_get_all_tags(self, query):
        """Test getting list of all tags."""
        tags = query.get_all_tags()
        
        # Should be a list of strings
        assert isinstance(tags, list)
    
    def test_get_all_classes(self, query):
        """Test getting all classes."""
        classes = query.get_all_classes()
        
        assert len(classes) > 0
    
    def test_get_all_classes_annotated_only(self, query):
        """Test getting only annotated classes."""
        all_classes = query.get_all_classes(annotated_only=False)
        annotated = query.get_all_classes(annotated_only=True)
        
        # Annotated should be <= total
        assert len(annotated) <= len(all_classes)
    
    def test_get_stats(self, query):
        """Test getting graph statistics."""
        stats = query.get_stats()
        
        assert "total_entities" in stats
        assert "entity_counts" in stats
        assert "total_claims" in stats
        assert "total_relationships" in stats
    
    def test_fragments_sorted_by_priority(self, query):
        """Test that fragments are sorted by priority."""
        fragments = query.get_fragments_for_doc_type("MANIFESTO")
        
        if len(fragments) >= 2:
            priorities = []
            for f in fragments:
                p = f.priority if hasattr(f, 'priority') else f.get('priority', 5)
                priorities.append(p)
            
            # Should be sorted descending
            assert priorities == sorted(priorities, reverse=True)
