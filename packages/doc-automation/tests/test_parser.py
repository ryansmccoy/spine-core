"""Tests for the parser module."""

import pytest
from pathlib import Path

from doc_automation.parser.ast_walker import ASTWalker, ClassInfo, MethodInfo
from doc_automation.parser.docstring_parser import DocstringParser, DocumentationFragment
from doc_automation.parser.section_extractors import SectionExtractor


# =============================================================================
# ASTWalker Tests
# =============================================================================

class TestASTWalker:
    """Tests for ASTWalker class."""
    
    @pytest.fixture
    def walker(self):
        """Create a walker instance."""
        return ASTWalker()
    
    @pytest.fixture
    def sample_file(self):
        """Path to sample annotated class file."""
        return Path(__file__).parent / "fixtures" / "sample_annotated_class.py"
    
    def test_walk_file_extracts_classes(self, walker, sample_file):
        """Test that walk_file extracts classes from Python file."""
        classes = walker.walk_file(sample_file)
        
        assert len(classes) >= 2
        class_names = [c.name for c in classes]
        assert "EntityResolver" in class_names
        assert "FeedAdapter" in class_names
    
    def test_class_has_docstring(self, walker, sample_file):
        """Test that extracted classes have docstrings."""
        classes = walker.walk_file(sample_file)
        
        resolver = next(c for c in classes if c.name == "EntityResolver")
        assert resolver.docstring is not None
        assert "Resolve any identifier" in resolver.docstring
    
    def test_has_extended_docstring_detection(self, walker, sample_file):
        """Test detection of extended docstring format."""
        classes = walker.walk_file(sample_file)
        
        resolver = next(c for c in classes if c.name == "EntityResolver")
        assert resolver.has_extended_docstring is True
    
    def test_methods_extracted(self, walker, sample_file):
        """Test that methods are extracted from classes."""
        classes = walker.walk_file(sample_file)
        
        resolver = next(c for c in classes if c.name == "EntityResolver")
        method_names = [m.name for m in resolver.methods]
        
        assert "__init__" in method_names
        assert "resolve" in method_names
    
    def test_method_signatures(self, walker, sample_file):
        """Test that method signatures are extracted."""
        classes = walker.walk_file(sample_file)
        
        resolver = next(c for c in classes if c.name == "EntityResolver")
        resolve_method = next(m for m in resolver.methods if m.name == "resolve")
        
        assert "identifier" in resolve_method.signature
        assert "as_of" in resolve_method.signature
    
    def test_public_methods_filtered(self, walker, sample_file):
        """Test filtering of public methods."""
        classes = walker.walk_file(sample_file)
        
        resolver = next(c for c in classes if c.name == "EntityResolver")
        public_names = [m.name for m in resolver.public_methods]
        
        assert "resolve" in public_names
        assert "_normalize" not in public_names  # Private method
    
    def test_file_not_found_error(self, walker):
        """Test that FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            walker.walk_file(Path("nonexistent.py"))
    
    def test_non_python_file_error(self, walker, tmp_path):
        """Test that ValueError is raised for non-Python files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not python")
        
        with pytest.raises(ValueError):
            walker.walk_file(txt_file)


# =============================================================================
# DocstringParser Tests
# =============================================================================

class TestDocstringParser:
    """Tests for DocstringParser class."""
    
    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return DocstringParser()
    
    @pytest.fixture
    def sample_docstring(self):
        """Sample extended docstring."""
        return '''
        Summary line describing the class.
        
        Manifesto:
            This is the core principle.
            It explains why this exists.
            
            Another paragraph of manifesto.
        
        Architecture:
            ```
            Box ──► Arrow ──► Result
            ```
        
        Features:
            - Feature one
            - Feature two
            - Feature three
        
        Examples:
            >>> obj = MyClass()
            >>> obj.method()
            'result'
        
        Guardrails:
            - Do NOT do bad thing
              ✅ Instead do good thing
        
        Tags:
            - core_concept
            - important
            - testing
        
        Doc-Types:
            - MANIFESTO (section: "Core Principles", priority: 10)
            - FEATURES (section: "Main Features", priority: 8)
        '''
    
    @pytest.fixture
    def source_info(self):
        """Sample source info."""
        return {
            "file": "test.py",
            "class": "TestClass",
            "method": None,
            "line": 42,
        }
    
    def test_parse_extracts_manifesto(self, parser, sample_docstring, source_info):
        """Test extraction of Manifesto section."""
        fragments = parser.parse(sample_docstring, source_info)
        
        manifesto = next((f for f in fragments if f.fragment_type == "manifesto"), None)
        assert manifesto is not None
        assert "core principle" in manifesto.content
    
    def test_parse_extracts_architecture(self, parser, sample_docstring, source_info):
        """Test extraction of Architecture section."""
        fragments = parser.parse(sample_docstring, source_info)
        
        arch = next((f for f in fragments if f.fragment_type == "architecture"), None)
        assert arch is not None
        assert "Box" in arch.content or "Arrow" in arch.content
    
    def test_parse_extracts_features(self, parser, sample_docstring, source_info):
        """Test extraction of Features section."""
        fragments = parser.parse(sample_docstring, source_info)
        
        features = next((f for f in fragments if f.fragment_type == "features"), None)
        assert features is not None
        assert "Feature one" in features.content
    
    def test_parse_extracts_tags(self, parser, sample_docstring, source_info):
        """Test extraction of tags."""
        fragments = parser.parse(sample_docstring, source_info)
        
        # All fragments should have the same tags
        manifesto = next((f for f in fragments if f.fragment_type == "manifesto"), None)
        assert manifesto is not None
        assert "core_concept" in manifesto.tags
        assert "important" in manifesto.tags
        assert "testing" in manifesto.tags
    
    def test_parse_extracts_doc_types(self, parser, sample_docstring, source_info):
        """Test extraction of doc types."""
        fragments = parser.parse(sample_docstring, source_info)
        
        manifesto = next((f for f in fragments if f.fragment_type == "manifesto"), None)
        assert manifesto is not None
        assert "MANIFESTO" in manifesto.doc_types
        assert "FEATURES" in manifesto.doc_types
    
    def test_parse_detects_format(self, parser, sample_docstring, source_info):
        """Test format detection."""
        fragments = parser.parse(sample_docstring, source_info)
        
        arch = next((f for f in fragments if f.fragment_type == "architecture"), None)
        assert arch is not None
        assert arch.format in ("ascii_diagram", "markdown")
        
        examples = next((f for f in fragments if f.fragment_type == "examples"), None)
        assert examples is not None
        assert examples.format == "python"
    
    def test_parse_empty_docstring(self, parser, source_info):
        """Test parsing empty docstring."""
        fragments = parser.parse("", source_info)
        assert fragments == []
    
    def test_parse_none_docstring(self, parser, source_info):
        """Test parsing None docstring."""
        fragments = parser.parse(None, source_info)
        assert fragments == []
    
    def test_fragment_ids_unique(self, parser, sample_docstring, source_info):
        """Test that fragment IDs are unique."""
        fragments = parser.parse(sample_docstring, source_info)
        
        ids = [f.fragment_id for f in fragments]
        assert len(ids) == len(set(ids))  # All unique


# =============================================================================
# SectionExtractor Tests
# =============================================================================

class TestSectionExtractor:
    """Tests for SectionExtractor class."""
    
    @pytest.fixture
    def extractor(self):
        """Create an extractor instance."""
        return SectionExtractor()
    
    def test_extract_examples_doctest(self, extractor):
        """Test extraction of doctest examples."""
        content = '''
        >>> resolver = EntityResolver()
        >>> resolver.resolve("AAPL")
        'Apple Inc.'
        '''
        
        examples = extractor.extract_examples(content)
        
        assert len(examples) >= 1
        assert examples[0].is_doctest is True
        assert "EntityResolver" in examples[0].code
    
    def test_extract_examples_codeblock(self, extractor):
        """Test extraction of code block examples."""
        content = '''
        ```python
        resolver = EntityResolver()
        result = resolver.resolve("AAPL")
        ```
        '''
        
        examples = extractor.extract_examples(content)
        
        assert len(examples) >= 1
        assert examples[0].language == "python"
    
    def test_extract_adr_references(self, extractor):
        """Test extraction of ADR references."""
        content = '''
        - 003-identifier-claims.md: Why we model identifiers as claims
        - 008-resolution-pipeline.md: Resolution algorithm design
        '''
        
        refs = extractor.extract_adr_references(content)
        
        assert len(refs) >= 2
        assert refs[0].number == 3
        assert "claims" in refs[0].title.lower()
    
    def test_extract_changelog_entries(self, extractor):
        """Test extraction of changelog entries."""
        content = '''
        - v0.3.0: Added fuzzy name matching
        - v0.4.0: Added CUSIP/ISIN support
        - v0.5.0: Breaking change - removed deprecated method
        '''
        
        entries = extractor.extract_changelog_entries(content)
        
        assert len(entries) >= 3
        assert entries[0].version == "0.3.0"
        assert "fuzzy" in entries[0].description.lower()
        
        # Check breaking change detection
        breaking_entry = next((e for e in entries if e.breaking), None)
        assert breaking_entry is not None
    
    def test_extract_guardrails(self, extractor):
        """Test extraction of guardrails."""
        content = '''
        - Do NOT use ticker as primary key (tickers change!)
          ✅ Use CIK as primary, map tickers via claims
        - Do NOT assume 1:1 mapping
          ✅ Handle multiple entities
        '''
        
        guardrails = extractor.extract_guardrails(content)
        
        assert len(guardrails) >= 2
        assert "ticker" in guardrails[0]["anti_pattern"].lower()
        assert "CIK" in guardrails[0]["correct_approach"]
