# ✅ VALIDATION PROMPT

**For LLM: How to validate annotated code and generated documentation**

*Quality assurance checklist and automated validation*

---

## 🎯 Your Mission

Validate that:
1. **Code annotations** are complete and follow format
2. **Extracted fragments** parse correctly
3. **Generated documentation** meets quality standards
4. **Knowledge graph** has correct structure
5. **Examples are runnable** and produce expected output

---

## 📋 Validation Checklist

### **Level 1: Annotation Completeness**

For each annotated class, verify:

```python
class ValidationChecker:
    """Validate extended docstring annotations."""
    
    REQUIRED_SECTIONS_TIER_1 = [
        "Manifesto",
        "Architecture",
        "Features",
        "Examples",
        "Guardrails",
        "Tags",
        "Doc-Types"
    ]
    
    OPTIONAL_SECTIONS = [
        "Performance",
        "Context",
        "ADR",
        "Changelog",
        "Feature-Guide",
        "Unified-Data-Model",
        "Architecture-Doc"
    ]
    
    def validate_class(self, class_info: ClassInfo) -> ValidationResult:
        """Validate a single class annotation."""
        
        issues = []
        warnings = []
        
        # Check has docstring
        if not class_info.docstring:
            issues.append(f"{class_info.name}: Missing docstring")
            return ValidationResult(valid=False, issues=issues)
        
        # Parse sections
        parser = DocstringParser()
        sections = parser._split_sections(class_info.docstring)
        
        # Check required sections
        for section in self.REQUIRED_SECTIONS_TIER_1:
            if section not in sections:
                issues.append(f"{class_info.name}: Missing required section '{section}'")
        
        # Check section quality
        if "Manifesto" in sections:
            if len(sections["Manifesto"]) < 100:
                warnings.append(f"{class_info.name}: Manifesto section is very short (<100 chars)")
            if "why" not in sections["Manifesto"].lower():
                warnings.append(f"{class_info.name}: Manifesto should explain WHY")
        
        if "Architecture" in sections:
            has_diagram = any(indicator in sections["Architecture"] 
                            for indicator in ["```", "┌", "→", "↓", "mermaid"])
            if not has_diagram:
                warnings.append(f"{class_info.name}: Architecture section should include diagram")
        
        if "Features" in sections:
            has_bullets = "-" in sections["Features"]
            if not has_bullets:
                warnings.append(f"{class_info.name}: Features should be bullet list")
        
        if "Examples" in sections:
            has_doctest = ">>>" in sections["Examples"]
            if not has_doctest:
                issues.append(f"{class_info.name}: Examples should use doctest format (>>>)")
        
        if "Guardrails" in sections:
            has_do_not = "do not" in sections["Guardrails"].lower()
            has_checkmark = "✅" in sections["Guardrails"]
            if not has_do_not or not has_checkmark:
                warnings.append(f"{class_info.name}: Guardrails should have 'Do NOT' + ✅ alternatives")
        
        if "Tags" in sections:
            tags = parser._extract_tags(sections)
            if len(tags) < 3:
                warnings.append(f"{class_info.name}: Should have at least 3 tags (has {len(tags)})")
        
        if "Doc-Types" in sections:
            doc_types = parser._extract_doc_types(sections)
            if len(doc_types) < 2:
                warnings.append(f"{class_info.name}: Should appear in at least 2 doc types (has {len(doc_types)})")
        
        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            warnings=warnings
        )
```

**Run validation:**
```python
# Validate all annotated classes
validator = ValidationChecker()
for class_info in annotated_classes:
    result = validator.validate_class(class_info)
    if not result.valid:
        print(f"❌ {class_info.name}")
        for issue in result.issues:
            print(f"  - {issue}")
    elif result.warnings:
        print(f"⚠️  {class_info.name}")
        for warning in result.warnings:
            print(f"  - {warning}")
    else:
        print(f"✅ {class_info.name}")
```

---

### **Level 2: Extraction Validation**

Verify parser correctly extracts sections:

```python
def test_extraction():
    """Test that parser extracts all sections."""
    
    # Sample annotated class
    from tests.fixtures.sample_annotated_class import SampleClass
    
    # Extract
    walker = ASTWalker()
    classes = walker.walk_file(Path("tests/fixtures/sample_annotated_class.py"))
    
    parser = DocstringParser()
    fragments = parser.parse(classes[0].docstring, {
        "file": "test.py",
        "class": classes[0].name,
        "line": 1
    })
    
    # Validate extraction
    fragment_types = [f.fragment_type for f in fragments]
    
    assert "manifesto" in fragment_types, "Should extract Manifesto fragment"
    assert "architecture" in fragment_types, "Should extract Architecture fragment"
    assert "features" in fragment_types, "Should extract Features fragment"
    
    # Validate tags extracted
    manifesto_frag = next(f for f in fragments if f.fragment_type == "manifesto")
    assert len(manifesto_frag.tags) >= 3, "Should have at least 3 tags"
    
    # Validate doc types extracted
    assert len(manifesto_frag.doc_types) >= 2, "Should appear in at least 2 doc types"
    
    # Validate sections mapped
    assert "MANIFESTO" in manifesto_frag.sections, "Should map to MANIFESTO section"
```

---

### **Level 3: Knowledge Graph Validation**

Verify graph structure is correct:

```python
def test_knowledge_graph_structure():
    """Validate knowledge graph has correct structure."""
    
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    # Check entities exist
    assert len(graph["entities"]) > 0, "Should have entities"
    
    # Check entity types
    entity_types = {e.entity_type for e in graph["entities"]}
    assert "CODE_CLASS" in entity_types, "Should have CODE_CLASS entities"
    assert "DOC_FRAGMENT" in entity_types, "Should have DOC_FRAGMENT entities"
    
    # Check claims exist
    assert len(graph["claims"]) > 0, "Should have identifier claims"
    
    # Check claim schemes
    claim_schemes = {c.scheme for c in graph["claims"]}
    assert "DOC_TYPE" in claim_schemes, "Should have DOC_TYPE claims"
    assert "TAG" in claim_schemes, "Should have TAG claims"
    
    # Check relationships exist
    assert len(graph["relationships"]) > 0, "Should have relationships"
    
    # Check relationship types
    rel_types = {r.relationship_type for r in graph["relationships"]}
    assert "EXTRACTED_FROM" in rel_types, "Should have EXTRACTED_FROM relationships"
    
    # Validate graph connectivity
    # Every DOC_FRAGMENT should link to a CODE_CLASS
    doc_fragments = [e for e in graph["entities"] if e.entity_type == "DOC_FRAGMENT"]
    for frag in doc_fragments:
        has_link = any(
            r.from_entity_id == frag.entity_id and r.relationship_type == "EXTRACTED_FROM"
            for r in graph["relationships"]
        )
        assert has_link, f"Fragment {frag.entity_id} should link to CODE_CLASS"
```

---

### **Level 4: Generated Documentation Quality**

Validate generated docs meet quality standards:

```python
def test_generated_manifesto_quality():
    """Validate MANIFESTO.md meets quality standards."""
    
    # Generate
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    renderer = ManifestoRenderer(graph, template_dir=Path("templates"))
    content = renderer.render()
    
    # Structure checks
    assert content.startswith("# MANIFESTO"), "Should start with # MANIFESTO"
    assert "## " in content, "Should have section headers"
    assert "Core Principles" in content or "Philosophy" in content, "Should have principles section"
    
    # Content checks
    assert len(content) > 1000, "Should be substantial (>1000 chars)"
    assert content.count("##") >= 2, "Should have multiple sections"
    
    # Metadata checks
    assert "Auto-generated" in content, "Should indicate auto-generated"
    assert "202" in content, "Should have timestamp (year)"
    
    # Link checks
    assert "](" in content, "Should have markdown links to source code"
    assert ".py" in content, "Links should reference .py files"
    
    # Quality checks
    assert content.count("why") >= 3, "Should explain WHY (appears 3+ times)"
    assert "principle" in content.lower(), "Should mention principles"
    
    # No empty sections
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("## "):
            # Next non-empty line should not be another header
            next_content = next((l for l in lines[i+1:] if l.strip()), "")
            assert not next_content.startswith("#"), f"Empty section: {line}"

def test_generated_features_quality():
    """Validate FEATURES.md meets quality standards."""
    
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    renderer = FeaturesRenderer(graph, template_dir=Path("templates"))
    content = renderer.render()
    
    # Should have bullet lists
    assert content.count("-") >= 10, "Should have many features (10+ bullets)"
    
    # Should have code examples
    assert "```python" in content or "```" in content, "Should have code examples"
    
    # Should have examples section
    assert "Example" in content, "Should show examples"

def test_generated_architecture_quality():
    """Validate ARCHITECTURE.md has diagrams."""
    
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    renderer = ArchitectureRenderer(graph, template_dir=Path("templates"))
    content = renderer.render()
    
    # Should have diagrams
    diagram_indicators = ["```", "┌", "└", "│", "─", "→", "↓", "mermaid"]
    has_diagram = any(indicator in content for indicator in diagram_indicators)
    assert has_diagram, "Should have at least one diagram"
```

---

### **Level 5: Example Validation (Doctest)**

Run doctests to verify examples work:

```python
import doctest
import importlib

def test_examples_are_runnable():
    """Run doctests on all annotated classes."""
    
    # Import module with annotated classes
    module = importlib.import_module("tests.fixtures.sample_annotated_class")
    
    # Run doctests
    result = doctest.testmod(module, verbose=True)
    
    # Check all passed
    assert result.failed == 0, f"{result.failed} doctest examples failed"
    assert result.attempted > 0, "Should have at least some doctest examples"
```

**Automated doctest runner:**
```python
def validate_all_examples(project_root: Path):
    """Run all doctests in annotated code."""
    
    results = []
    
    for py_file in project_root.rglob("*.py"):
        if "test_" in str(py_file) or "__pycache__" in str(py_file):
            continue
        
        # Import module
        try:
            spec = importlib.util.spec_from_file_location("module", py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Run doctests
            result = doctest.testmod(module, verbose=False)
            results.append({
                "file": str(py_file),
                "attempted": result.attempted,
                "failed": result.failed
            })
        except Exception as e:
            results.append({
                "file": str(py_file),
                "error": str(e)
            })
    
    # Report
    total_attempted = sum(r.get("attempted", 0) for r in results)
    total_failed = sum(r.get("failed", 0) for r in results)
    
    print(f"Doctest Results:")
    print(f"  Total examples: {total_attempted}")
    print(f"  Failed: {total_failed}")
    print(f"  Pass rate: {100 * (1 - total_failed/total_attempted):.1f}%")
    
    return total_failed == 0
```

---

### **Level 6: Consistency Checks**

Verify consistency across annotations:

```python
def test_terminology_consistency():
    """Check that terminology is consistent."""
    
    # Load all docstrings
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    # Extract all text
    all_text = []
    for entity in graph["entities"]:
        if entity.entity_type == "DOC_FRAGMENT":
            all_text.append(entity.content)
    
    combined = "\n".join(all_text).lower()
    
    # Check for inconsistencies
    issues = []
    
    # Example: Entity vs entity (should be consistent)
    if "Entity" in combined and "entity" in combined:
        # Check ratio
        entity_upper = combined.count("entity")
        entity_lower = combined.count("entity") 
        # (This is simplistic - real check would be smarter)
    
    # Check for conflicting statements
    # (Would need NLP for real implementation)
    
    assert len(issues) == 0, f"Consistency issues: {issues}"

def test_section_naming_consistency():
    """Verify section names are consistent across classes."""
    
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    # Collect all section names
    section_names = {}
    
    for entity in graph["entities"]:
        if entity.entity_type == "DOC_FRAGMENT":
            for doc_type, section in entity.sections.items():
                if doc_type not in section_names:
                    section_names[doc_type] = set()
                section_names[doc_type].add(section)
    
    # Check for variants (e.g., "Core Principles" vs "Core Principle")
    for doc_type, sections in section_names.items():
        print(f"{doc_type} sections: {sections}")
        
        # Warn if too many unique sections
        if len(sections) > 10:
            print(f"  ⚠️  Many unique section names ({len(sections)}) - consider standardizing")
```

---

### **Level 7: Diff Against Hand-Written Docs**

Compare generated to existing docs:

```python
def test_generated_vs_handwritten():
    """Compare generated docs to existing hand-written docs."""
    
    # Generate
    orchestrator = DocumentationOrchestrator(
        project_root=Path("tests/fixtures"),
        output_dir=Path("tests/output/generated")
    )
    orchestrator.generate_all()
    
    # Load hand-written
    handwritten_manifesto = Path("tests/fixtures/docs/MANIFESTO.md").read_text()
    generated_manifesto = Path("tests/output/generated/MANIFESTO.md").read_text()
    
    # Basic similarity check (real implementation would use difflib or NLP)
    handwritten_lines = set(handwritten_manifesto.splitlines())
    generated_lines = set(generated_manifesto.splitlines())
    
    # Check overlap
    overlap = handwritten_lines & generated_lines
    similarity = len(overlap) / max(len(handwritten_lines), len(generated_lines))
    
    print(f"Similarity to hand-written: {similarity:.1%}")
    
    # Should be reasonably similar (but not identical - generated may be better!)
    assert similarity > 0.3, "Generated doc should have some similarity to hand-written"
```

---

## 🎯 Validation Workflow

### Step 1: Pre-Annotation Validation

Before annotating code:

```bash
# Check which classes need annotation
docbuilder analyze --project-root . --show-unannotated

# Output:
# Tier 1 Classes (MUST annotate):
#   ✅ EntityResolver - fully annotated
#   ❌ EntityStore - missing annotation
#   ⚠️  EntityGraph - partial annotation (missing Guardrails)
```

### Step 2: Post-Annotation Validation

After annotating a class:

```bash
# Validate single file
docbuilder validate src/entityspine/resolver.py

# Output:
# ✅ EntityResolver
#   - Manifesto: 450 chars ✓
#   - Architecture: Has diagram ✓
#   - Features: 8 items ✓
#   - Examples: 3 doctests ✓
#   - Tags: 4 tags ✓
#   - Doc-Types: 4 types ✓
```

### Step 3: Extraction Validation

Test parser:

```bash
# Extract and validate
docbuilder extract src/entityspine/resolver.py --validate

# Output:
# Extracted 5 fragments:
#   - manifesto (237 chars, 3 tags, 4 doc-types)
#   - architecture (412 chars, format: ascii_diagram)
#   - features (156 chars, 8 bullets)
#   - examples (89 chars, 3 doctests)
#   - guardrails (134 chars, 4 anti-patterns)
```

### Step 4: Graph Validation

Verify graph structure:

```bash
# Build and validate graph
docbuilder graph --validate

# Output:
# Knowledge Graph:
#   Entities: 47 (23 CODE_CLASS, 24 DOC_FRAGMENT)
#   Claims: 156 (89 TAG, 67 DOC_TYPE)
#   Relationships: 24 (all EXTRACTED_FROM)
#   
# Validation:
#   ✅ All fragments link to classes
#   ✅ All doc-types have ≥1 fragment
#   ✅ No orphaned entities
```

### Step 5: Generation Validation

Generate and validate docs:

```bash
# Generate with validation
docbuilder build --validate

# Output:
# Generated:
#   ✅ MANIFESTO.md (2.3 KB, 4 sections, 12 fragments)
#   ✅ FEATURES.md (1.8 KB, 3 sections, 18 features)
#   ✅ ARCHITECTURE.md (3.1 KB, 5 diagrams)
#   
# Quality Checks:
#   ✅ All sections non-empty
#   ✅ All code links valid
#   ✅ No duplicate content
#   ⚠️  Some sections <200 chars (may need more content)
```

### Step 6: Doctest Validation

Run all examples:

```bash
# Run doctests
docbuilder test-examples

# Output:
# Running doctests...
#   EntityResolver: 3 examples, 0 failed ✅
#   EntityStore: 2 examples, 0 failed ✅
#   FeedAdapter: 4 examples, 1 failed ❌
#     FAILED: example 2 (expected 'success', got 'failure')
#   
# Total: 9 examples, 1 failed (88.9% pass rate)
```

---

## ✅ Success Criteria

**Annotation Quality:**
- [ ] All Tier 1 classes have complete docstrings
- [ ] All required sections present
- [ ] At least 3 tags per class
- [ ] At least 2 doc-types per class
- [ ] All examples use doctest format

**Extraction Quality:**
- [ ] Parser extracts all sections correctly
- [ ] Tags and doc-types recognized
- [ ] Diagrams detected (ASCII/Mermaid)
- [ ] No parsing errors

**Graph Quality:**
- [ ] All fragments link to code classes
- [ ] All doc-types have ≥1 fragment
- [ ] No orphaned entities
- [ ] Claims correctly categorized

**Generated Docs Quality:**
- [ ] All docs ≥1000 chars
- [ ] All sections non-empty
- [ ] Code links valid
- [ ] No duplicate content
- [ ] Diagrams render correctly

**Example Quality:**
- [ ] 90%+ doctest pass rate
- [ ] Examples cover basic usage
- [ ] Examples cover advanced usage
- [ ] Examples are realistic

---

## 🔧 Automated Validation Script

```python
#!/usr/bin/env python3
"""Full validation pipeline."""

from doc_automation.validation import (
    validate_annotations,
    validate_extraction,
    validate_graph,
    validate_generated_docs,
    validate_examples
)

def main():
    print("🔍 Documentation Validation Pipeline\n")
    
    # Level 1: Annotations
    print("Level 1: Validating annotations...")
    annotation_result = validate_annotations(Path("."))
    print(f"  {'✅' if annotation_result.passed else '❌'} {annotation_result.summary}\n")
    
    # Level 2: Extraction
    print("Level 2: Validating extraction...")
    extraction_result = validate_extraction(Path("."))
    print(f"  {'✅' if extraction_result.passed else '❌'} {extraction_result.summary}\n")
    
    # Level 3: Graph
    print("Level 3: Validating knowledge graph...")
    graph_result = validate_graph(Path("."))
    print(f"  {'✅' if graph_result.passed else '❌'} {graph_result.summary}\n")
    
    # Level 4: Generated Docs
    print("Level 4: Validating generated docs...")
    docs_result = validate_generated_docs(Path("."))
    print(f"  {'✅' if docs_result.passed else '❌'} {docs_result.summary}\n")
    
    # Level 5: Examples
    print("Level 5: Validating examples (doctests)...")
    examples_result = validate_examples(Path("."))
    print(f"  {'✅' if examples_result.passed else '❌'} {examples_result.summary}\n")
    
    # Summary
    all_passed = all([
        annotation_result.passed,
        extraction_result.passed,
        graph_result.passed,
        docs_result.passed,
        examples_result.passed
    ])
    
    if all_passed:
        print("🎉 All validation checks passed!")
        return 0
    else:
        print("❌ Some validation checks failed. See above for details.")
        return 1

if __name__ == "__main__":
    exit(main())
```

---

*Quality → Confidence → Adoption*
