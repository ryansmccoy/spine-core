"""Tests for renderers and full pipeline."""

import pytest
from pathlib import Path

from doc_automation.graph.builder import KnowledgeGraphBuilder
from doc_automation.renderers import (
    ManifestoRenderer,
    FeaturesRenderer,
    ArchitectureRenderer,
    GuardrailsRenderer,
)
from doc_automation.orchestrator import DocumentationOrchestrator


# =============================================================================
# Renderer Tests
# =============================================================================

class TestManifestoRenderer:
    """Tests for ManifestoRenderer."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def graph(self, fixtures_dir):
        """Build graph from fixtures."""
        builder = KnowledgeGraphBuilder(fixtures_dir)
        return builder.build()
    
    def test_render_produces_markdown(self, graph):
        """Test that render produces markdown content."""
        renderer = ManifestoRenderer(graph)
        content = renderer.render()
        
        assert content is not None
        assert "# MANIFESTO" in content
    
    def test_render_includes_timestamp(self, graph):
        """Test that render includes timestamp."""
        renderer = ManifestoRenderer(graph)
        content = renderer.render()
        
        assert "Auto-generated" in content or "generated" in content.lower()
    
    def test_render_includes_sections(self, graph):
        """Test that render includes section headers."""
        renderer = ManifestoRenderer(graph)
        content = renderer.render()
        
        # Should have some section headers
        assert "##" in content


class TestFeaturesRenderer:
    """Tests for FeaturesRenderer."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def graph(self, fixtures_dir):
        """Build graph from fixtures."""
        builder = KnowledgeGraphBuilder(fixtures_dir)
        return builder.build()
    
    def test_render_produces_markdown(self, graph):
        """Test that render produces markdown content."""
        renderer = FeaturesRenderer(graph)
        content = renderer.render()
        
        assert content is not None
        assert "# FEATURES" in content
    
    def test_render_includes_bullet_points(self, graph):
        """Test that render includes feature bullets."""
        renderer = FeaturesRenderer(graph)
        content = renderer.render()
        
        # Features should have bullet points
        assert "-" in content


class TestArchitectureRenderer:
    """Tests for ArchitectureRenderer."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def graph(self, fixtures_dir):
        """Build graph from fixtures."""
        builder = KnowledgeGraphBuilder(fixtures_dir)
        return builder.build()
    
    def test_render_produces_markdown(self, graph):
        """Test that render produces markdown content."""
        renderer = ArchitectureRenderer(graph)
        content = renderer.render()
        
        assert content is not None
        assert "# ARCHITECTURE" in content


# =============================================================================
# Orchestrator Tests
# =============================================================================

class TestDocumentationOrchestrator:
    """Tests for DocumentationOrchestrator."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def output_dir(self, tmp_path):
        """Temporary output directory."""
        return tmp_path / "docs"
    
    @pytest.fixture
    def orchestrator(self, fixtures_dir, output_dir):
        """Create orchestrator instance."""
        return DocumentationOrchestrator(
            project_root=fixtures_dir,
            output_dir=output_dir,
        )
    
    def test_build_graph(self, orchestrator):
        """Test building knowledge graph."""
        graph = orchestrator.build_graph()
        
        assert graph is not None
        assert "entities" in graph
        assert "claims" in graph
        assert "relationships" in graph
    
    def test_generate_single_doc(self, orchestrator):
        """Test generating a single document."""
        content = orchestrator.generate_doc("MANIFESTO")
        
        assert content is not None
        assert "# MANIFESTO" in content
    
    def test_generate_all(self, orchestrator, output_dir):
        """Test generating all documents."""
        results = orchestrator.generate_all()
        
        # Should have results for multiple doc types
        assert len(results) > 0
        
        # Output files should exist
        assert output_dir.exists()
    
    def test_generate_creates_files(self, orchestrator, output_dir):
        """Test that generate_all creates output files."""
        orchestrator.generate_all(doc_types=["MANIFESTO"])
        
        manifesto_file = output_dir / "MANIFESTO.md"
        assert manifesto_file.exists()
        
        content = manifesto_file.read_text(encoding="utf-8")
        assert "# MANIFESTO" in content
    
    def test_get_stats(self, orchestrator):
        """Test getting statistics."""
        stats = orchestrator.get_stats()
        
        assert "total_entities" in stats
        assert "doc_types" in stats
    
    def test_validate(self, orchestrator):
        """Test validation."""
        result = orchestrator.validate()
        
        assert "valid" in result
        assert "issues" in result
        assert "warnings" in result
        assert "stats" in result


# =============================================================================
# Full Pipeline Tests
# =============================================================================

class TestFullPipeline:
    """Tests for the complete documentation pipeline."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def output_dir(self, tmp_path):
        """Temporary output directory."""
        return tmp_path / "generated_docs"
    
    def test_full_pipeline(self, fixtures_dir, output_dir):
        """Test complete pipeline: code → graph → docs."""
        # 1. Build graph
        builder = KnowledgeGraphBuilder(fixtures_dir)
        graph = builder.build()
        
        assert len(graph["entities"]) > 0
        
        # 2. Render MANIFESTO
        renderer = ManifestoRenderer(graph)
        content = renderer.render()
        
        assert "# MANIFESTO" in content
        
        # 3. Write to file
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "MANIFESTO.md"
        output_path.write_text(content, encoding="utf-8")
        
        assert output_path.exists()
        
        # 4. Verify content quality
        written_content = output_path.read_text(encoding="utf-8")
        assert len(written_content) > 100
    
    def test_pipeline_with_orchestrator(self, fixtures_dir, output_dir):
        """Test pipeline using orchestrator."""
        orchestrator = DocumentationOrchestrator(
            project_root=fixtures_dir,
            output_dir=output_dir,
        )
        
        results = orchestrator.generate_all()
        
        # Should generate multiple docs
        successful = [k for k, v in results.items() if v > 0]
        assert len(successful) >= 1
        
        # Validate
        validation = orchestrator.validate()
        # Validation may have warnings, but should complete
        assert "valid" in validation
