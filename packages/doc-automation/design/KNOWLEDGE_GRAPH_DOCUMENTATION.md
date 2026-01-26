# Knowledge Graph-Based Documentation System

**Advanced documentation automation using EntitySpine to model code → docs relationships**

*Part of Documentation Automation Package - February 2026*

---

## 🎯 Vision: Documentation as a Knowledge Graph

Instead of treating documentation as flat files, model it as a **knowledge graph** where:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   DOCUMENTATION KNOWLEDGE GRAPH                             │
│                                                                             │
│   Code Class ──────► Documentation Entity ──────► Generated Document       │
│   (Python)           (EntitySpine model)          (Markdown file)           │
│                                                                             │
│   EntityResolver ──► manifesto_principle_1 ──────► MANIFESTO.md (section)  │
│        │             (Entity type: doc_fragment)                            │
│        ├──────────► architecture_diagram_1 ──────► ARCHITECTURE.md         │
│        ├──────────► adr_003_identifier_claims ───► adrs/003-...md          │
│        ├──────────► feature_resolution ──────────► FEATURES.md             │
│        └──────────► changelog_v0_4_0 ────────────► CHANGELOG.md            │
│                                                                             │
│   Query the graph: "Give me all doc fragments tagged 'architecture'"       │
│   Result: Set of entities to assemble into ARCHITECTURE.md                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📚 Extended Document Types

Not just 3 basic docs - generate **all project documentation types**:

### Core Documents (Basic)
1. **MANIFESTO.md** - Philosophy, principles, "why this exists"
2. **FEATURES.md** - What it can do, capabilities, examples
3. **GUARDRAILS.md** - What NOT to do, constraints, anti-patterns

### Architecture Documents (Advanced)
4. **ARCHITECTURE.md** - High-level system design
5. **CORE_PRIMITIVES.md** - Foundational building blocks
6. **UNIFIED_DATA_MODEL.md** - Canonical schema, data contracts
7. **TIER_STRATEGY.md** - Progressive complexity (T0 → T1 → T2 → T3)
8. **API_REFERENCE.md** - Auto-generated from docstrings

### Process Documents
9. **ADRs/** - Architecture Decision Records (adrs/001-*.md, adrs/002-*.md)
10. **CHANGELOG.md** - Version history, what changed
11. **MIGRATION_GUIDES.md** - How to upgrade between versions
12. **DEPRECATION_NOTICES.md** - What's being sunset

### Feature Documentation
13. **FEATURE_GUIDES/** - In-depth guides per feature
    - `guides/RESOLUTION_GUIDE.md` - How entity resolution works
    - `guides/CLAIMS_GUIDE.md` - Claims-based identity system
    - `guides/DATA_ARCHETYPES_GUIDE.md` - Understanding data types
14. **EXAMPLES/** - Runnable code examples
15. **TUTORIALS/** - Step-by-step walkthroughs

### Developer Documentation
16. **CONTRIBUTING.md** - How to contribute
17. **CODE_STANDARDS.md** - Coding conventions
18. **TESTING_GUIDE.md** - How to test
19. **DEBUGGING.md** - Common issues and solutions

### Context/Background
20. **CONTEXT.md** - Problem space, motivation
21. **GLOSSARY.md** - Terms and definitions
22. **FAQ.md** - Frequently asked questions

---

## 🏗️ EntitySpine-Based Documentation Model

Use **EntitySpine itself** to model documentation as entities and relationships:

### Schema: Documentation Entities

```python
from entityspine import Entity, IdentifierClaim, Relationship

# 1. Documentation Fragment (the atomic unit)
doc_fragment = Entity(
    primary_name="Entity ≠ Security ≠ Listing Principle",
    entity_type="DOC_FRAGMENT",
    source_system="code_annotations",
    source_id="entityspine.resolver.EntityResolver.manifesto.separation"
)

# 2. Identifier Claims (where this fragment appears)
IdentifierClaim(
    entity_id=doc_fragment.entity_id,
    scheme="DOC_TYPE",
    identifier="MANIFESTO",
    section="Core Principles",
    confidence=1.0
)

IdentifierClaim(
    entity_id=doc_fragment.entity_id,
    scheme="DOC_TYPE",
    identifier="ARCHITECTURE",
    section="Data Model",
    confidence=0.8  # Also relevant to architecture
)

IdentifierClaim(
    entity_id=doc_fragment.entity_id,
    scheme="SOURCE_FILE",
    identifier="src/entityspine/resolver.py",
    line_number=42,
    confidence=1.0
)

# 3. Relationships (how fragments connect)
Relationship(
    from_entity_id=doc_fragment.entity_id,
    relationship_type="IMPLEMENTS",
    to_entity_id=code_class_entity_id,  # Links to EntityResolver class
    source_system="doc_automation",
    confidence=1.0
)

Relationship(
    from_entity_id=doc_fragment.entity_id,
    relationship_type="REFERENCES",
    to_entity_id=adr_003_entity_id,  # Links to ADR about identifier claims
    source_system="doc_automation",
    confidence=1.0
)

Relationship(
    from_entity_id=doc_fragment.entity_id,
    relationship_type="EXAMPLE_OF",
    to_entity_id=feature_guide_entity_id,  # Featured in resolution guide
    source_system="doc_automation",
    confidence=1.0
)
```

### Documentation Fragment Structure

```python
@dataclass
class DocumentationFragment:
    """A piece of documentation extracted from code."""
    
    fragment_id: str  # EntitySpine entity_id
    fragment_type: str  # manifesto | architecture | feature | example | adr
    content: str  # The actual text/code
    format: str  # markdown | python | ascii_diagram | mermaid
    
    # Source provenance
    source_file: str  # src/entityspine/resolver.py
    source_class: str | None  # EntityResolver
    source_method: str | None  # resolve()
    source_line: int | None  # Line number
    
    # Tags for retrieval
    tags: list[str]  # ['core_concept', 'entity_resolution', 'identifier_disambiguation']
    doc_types: list[str]  # ['MANIFESTO', 'FEATURES', 'ARCHITECTURE']
    sections: dict[str, str]  # {'MANIFESTO': 'Core Principles', 'ARCHITECTURE': 'Data Model'}
    
    # Metadata
    priority: int  # 1-10 (importance for inclusion)
    confidence: float  # 0-1 (how confident we are about categorization)
    last_updated: datetime
    version: str  # Code version when extracted
```

---

## 🏷️ Enhanced Code Annotation Format

Expand docstring format to include **all** documentation metadata:

```python
class EntityResolver:
    """
    Resolve any identifier (CIK, ticker, name) to a canonical entity.
    
    Manifesto:
        Entity ≠ Security ≠ Listing is fundamental to EntitySpine.
        
        This separation exists because:
        - One entity (Apple Inc.) can have multiple securities (stock, bonds, warrants)
        - One security (AAPL common) can have multiple listings (NASDAQ, BATS, IEX)
        - Conflating these leads to incorrect data joins and broken analytics
        
        We use CIK as the stable entity identifier because tickers change,
        companies reorganize, and securities get relisted.
    
    Architecture:
        ```
        Identifier (any type)
              ↓
        EntityResolver.resolve()
              ↓
        ┌─────────────────────────┐
        │  Lookup Strategies:     │
        │  1. CIK direct lookup   │
        │  2. Ticker → CIK        │
        │  3. Name fuzzy match    │
        │  4. CUSIP → CIK         │
        └───────────┬─────────────┘
                    ↓
          Canonical Entity (with CIK)
        ```
        
        Storage: SQLite (Tier 1), DuckDB (Tier 2), PostgreSQL (Tier 3)
        Caching: In-memory LRU (10K entities)
        Fallback: SEC EDGAR API for missing entities
    
    Features:
        - Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
        - Fuzzy name matching (Levenshtein distance < 3)
        - Ticker disambiguation (AAPL 1980 ≠ AAPL 2020)
        - Historical ticker resolution (time-aware)
        - Bulk resolution (batch API for 1000+ identifiers)
        - Entity metadata (industry, SIC code, filing status)
    
    Examples:
        >>> resolver = EntityResolver()
        >>> entity = resolver.resolve("AAPL")
        >>> entity.cik
        '0000320193'
        >>> entity.name
        'Apple Inc.'
    
    Performance:
        - Single lookup: <1ms (cached), <10ms (uncached)
        - Bulk resolution: ~50 identifiers/second
        - Memory: ~50MB for 10K cached entities
        - Storage: ~500MB for full SEC entity universe
    
    Guardrails:
        - Do NOT use ticker as primary key (tickers change!)
        - Do NOT assume one-to-one ticker → entity (disambiguation needed)
        - Do NOT skip validation (always check resolve() returns non-None)
        - Do NOT mix entity and security identifiers
    
    Context:
        Problem: Most financial systems treat "ticker" as primary key,
        causing breakage when companies change tickers, merge, or reorganize.
        
        Solution: Use CIK (Central Index Key) as stable entity identifier,
        map all other identifiers to CIK.
    
    ADR:
        - 003-identifier-claims.md: Why we model identifiers as claims
        - 008-resolution-pipeline-and-claims.md: Resolution algorithm design
    
    Changelog:
        - v0.3.0: Added fuzzy name matching
        - v0.4.0: Implemented claims-based resolution
        - v0.5.0: Added historical ticker support
    
    Feature-Guide:
        Target: guides/RESOLUTION_GUIDE.md
        Section: "How Entity Resolution Works"
        Include-Example: True
    
    Unified-Data-Model:
        Target: UNIFIED_DATA_MODEL.md
        Section: "Entity Resolution"
        Diagram: entity-security-listing-hierarchy
    
    Tags:
        - core_concept
        - entity_resolution
        - identifier_disambiguation
        - claims_based_identity
    
    Doc-Types:
        - MANIFESTO (section: "Core Principles", priority: 10)
        - FEATURES (section: "Resolution", priority: 9)
        - ARCHITECTURE (section: "Data Model", priority: 8)
        - API_REFERENCE (auto-generate from signature)
    """
    
    def resolve(self, identifier: str, as_of: date | None = None) -> Entity | None:
        """
        Resolve identifier to canonical entity.
        
        Args:
            identifier: CIK, ticker, CUSIP, ISIN, or company name
            as_of: Optional date for historical resolution
        
        Returns:
            Entity if found, None otherwise
        
        Raises:
            ValueError: If identifier format is invalid
            AmbiguousIdentifierError: If multiple entities match
        
        Examples:
            >>> resolver.resolve("AAPL")
            Entity(cik='0000320193', name='Apple Inc.')
            
            >>> resolver.resolve("0000320193")
            Entity(cik='0000320193', name='Apple Inc.')
            
            # Historical resolution
            >>> resolver.resolve("FB", as_of=date(2021, 1, 1))
            Entity(cik='0001326801', name='Meta Platforms Inc')
        
        Feature-Guide:
            Target: guides/RESOLUTION_GUIDE.md
            Section: "Basic Resolution"
        
        Changelog:
            - v0.4.0: Added as_of parameter for historical resolution
        
        Tags:
            - api
            - resolution
            - historical_queries
        """
        ...
```

---

## 🔍 Knowledge Graph Queries

Build documentation by querying the EntitySpine graph:

### Query 1: Generate MANIFESTO.md

```python
from entityspine import EntityGraph

graph = EntityGraph()

# Query all fragments tagged for MANIFESTO
manifesto_fragments = graph.query("""
    MATCH (frag:Entity {entity_type: 'DOC_FRAGMENT'})-[:TAGGED_FOR]->(doc:Entity {name: 'MANIFESTO'})
    RETURN frag.content, frag.section, frag.priority
    ORDER BY frag.priority DESC, frag.section ASC
""")

# Assemble into document
manifesto_md = generate_document(
    template="templates/MANIFESTO_template.md",
    fragments=manifesto_fragments,
    metadata={
        "project": "entityspine",
        "version": "0.5.0",
        "generated_at": datetime.now()
    }
)
```

### Query 2: Generate Feature Guide with Examples

```python
# Query all fragments for a specific feature guide
resolution_guide_fragments = graph.query("""
    MATCH (frag:Entity {entity_type: 'DOC_FRAGMENT'})
    WHERE 'guides/RESOLUTION_GUIDE.md' IN frag.target_docs
    RETURN frag
    ORDER BY frag.section_order, frag.priority DESC
""")

# Get related code examples
examples = graph.query("""
    MATCH (frag)-[:HAS_EXAMPLE]->(example:Entity {entity_type: 'CODE_EXAMPLE'})
    WHERE frag.target_doc = 'guides/RESOLUTION_GUIDE.md'
    RETURN example.code, example.language, example.description
""")

# Get related ADRs
related_adrs = graph.query("""
    MATCH (frag)-[:REFERENCES]->(adr:Entity {entity_type: 'ADR'})
    WHERE frag.target_doc = 'guides/RESOLUTION_GUIDE.md'
    RETURN adr.number, adr.title, adr.file_path
""")

# Assemble complete guide
resolution_guide = generate_document(
    template="templates/FEATURE_GUIDE_template.md",
    fragments=resolution_guide_fragments,
    examples=examples,
    related_adrs=related_adrs,
    metadata={"feature": "entity_resolution"}
)
```

### Query 3: Generate CHANGELOG.md from Git + Code Annotations

```python
# Get git commits
git_commits = get_git_commits(since="v0.4.0", until="v0.5.0")

# Match commits to code changes
changelog_fragments = graph.query("""
    MATCH (frag:Entity {entity_type: 'DOC_FRAGMENT'})
    WHERE frag.changelog_version = '0.5.0'
    RETURN frag.content, frag.change_type, frag.breaking
""")

# Assemble changelog
changelog = generate_changelog(
    version="0.5.0",
    date=date(2025, 2, 15),
    commits=git_commits,
    fragments=changelog_fragments,
    template="templates/CHANGELOG_template.md"
)
```

### Query 4: Generate Architecture Diagrams

```python
# Get all architecture fragments
arch_fragments = graph.query("""
    MATCH (frag:Entity {entity_type: 'DOC_FRAGMENT'})
    WHERE 'ARCHITECTURE' IN frag.doc_types AND frag.format = 'ascii_diagram'
    RETURN frag
""")

# Also find relationships between components
component_relationships = graph.query("""
    MATCH (class1:Entity {entity_type: 'CODE_CLASS'})-[r:DEPENDS_ON|INHERITS_FROM]->(class2:Entity)
    RETURN class1.name, type(r), class2.name
""")

# Generate Mermaid diagram
mermaid_diagram = generate_architecture_diagram(
    fragments=arch_fragments,
    relationships=component_relationships,
    format="mermaid"
)
```

---

## 📖 Mining Existing Documentation

Use **existing docs in archive/** as templates and examples:

### Step 1: Extract Templates from Archive

```python
from doc_automation.template_extractor import extract_template

# Mine DATA_ARCHETYPES_GUIDE.md structure
template = extract_template(
    source_file="feedspine/docs/archive/design/DATA_ARCHETYPES_GUIDE.md",
    template_name="data_archetype_guide"
)

# Extracted structure:
{
    "sections": [
        {"title": "Why Data Types Matter", "type": "motivation"},
        {"title": "The Five Data Archetypes", "type": "overview"},
        {"title": "Archetype 1: Observations", "type": "detail", "repeats": True},
        {"title": "Storage Backend Selection", "type": "implementation"},
        {"title": "Putting It All Together", "type": "synthesis"}
    ],
    "patterns": {
        "archetype_section": """
### What They Are
[explanation]

### Why [X] Matters
[rationale]

### FeedSpine [X] Storage
```python
[code example]
```

### Common Queries
```python
[query examples]
```
"""
    }
}
```

### Step 2: Generate New Docs from Template

```python
# Use extracted template to generate new archetype guide
new_guide = generate_from_template(
    template="data_archetype_guide",
    data_source="code_annotations",  # Get content from docstrings
    project="market-spine",
    output="market-spine/docs/guides/DATA_ARCHETYPES_GUIDE.md"
)
```

### Step 3: Preserve Good Examples

```python
# Archive has excellent examples - extract and reuse them
examples_db = ExampleExtractor()

# Extract from CORE_CONCEPTS.md
examples_db.extract(
    source="entityspine/docs/guides/CORE_CONCEPTS.md",
    sections=["Pattern 1: Load SEC Data", "Pattern 2: Cross-Reference Identifiers"]
)

# Reuse in generated docs
generate_document(
    template="CORE_CONCEPTS",
    examples=examples_db.get_matching(tags=["sec_data", "identifier_resolution"]),
    output="entityspine/docs/guides/CORE_CONCEPTS.md"
)
```

---

## 🎨 Document Templates

Create Jinja2 templates for each document type:

### Template: ADR (Architecture Decision Record)

```markdown
{# templates/ADR_template.md #}
# {{ adr.number }}. {{ adr.title }}

**Date**: {{ adr.date }}
**Status**: {{ adr.status }}
**Deciders**: {{ adr.deciders | join(", ") }}

---

## Context

{{ adr.context }}

## Decision

{{ adr.decision }}

## Rationale

{% for reason in adr.rationale %}
- {{ reason }}
{% endfor %}

## Consequences

### Positive

{% for consequence in adr.positive_consequences %}
- {{ consequence }}
{% endfor %}

### Negative

{% for consequence in adr.negative_consequences %}
- {{ consequence }}
{% endfor %}

## Implementation

```python
{{ adr.example_code }}
```

## Related

{% for related in adr.related_adrs %}
- [{{ related.number }}: {{ related.title }}]({{ related.file_path }})
{% endfor %}

---

*Generated from code annotations on {{ generated_at }}*
```

### Template: Feature Guide

```markdown
{# templates/FEATURE_GUIDE_template.md #}
# {{ feature.title }}

> {{ feature.tagline }}

---

## 🎯 What Is This?

{{ feature.overview }}

## 🏛️ Core Concepts

{% for concept in feature.concepts %}
### {{ concept.title }}

{{ concept.explanation }}

{% if concept.diagram %}
```
{{ concept.diagram }}
```
{% endif %}

{% if concept.examples %}
**Examples:**

{% for example in concept.examples %}
```{{ example.language }}
{{ example.code }}
```

{{ example.description }}
{% endfor %}
{% endif %}

{% endfor %}

## 📚 How It Works

{{ feature.how_it_works }}

## 🚀 Quick Start

```python
{{ feature.quick_start_code }}
```

## 🔍 Advanced Usage

{% for advanced_topic in feature.advanced_topics %}
### {{ advanced_topic.title }}

{{ advanced_topic.content }}
{% endfor %}

## ⚠️ Common Pitfalls

{% for pitfall in feature.guardrails %}
- **{{ pitfall.anti_pattern }}**: {{ pitfall.why_bad }}
  - ✅ Instead: {{ pitfall.correct_approach }}
{% endfor %}

## 🔗 Related

{% for related in feature.related_docs %}
- [{{ related.title }}]({{ related.path }})
{% endfor %}

---

*Auto-generated from `{{ feature.source_file }}` on {{ generated_at }}*
```

---

## 🔧 Implementation: Knowledge Graph Builder

```python
from entityspine import Entity, IdentifierClaim, Relationship
from doc_automation.parser import DocstringParser
from doc_automation.graph import DocumentationGraph

class KnowledgeGraphBuilder:
    """Build documentation knowledge graph from code annotations."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.graph = DocumentationGraph()
        self.parser = DocstringParser()
    
    def build(self) -> DocumentationGraph:
        """Scan all Python files and build graph."""
        
        for py_file in self.project_root.rglob("*.py"):
            self._process_file(py_file)
        
        return self.graph
    
    def _process_file(self, file_path: Path):
        """Extract documentation fragments from file."""
        
        module = self.parser.parse_file(file_path)
        
        for cls in module.classes:
            # Create entity for the code class
            class_entity = Entity(
                primary_name=f"{module.name}.{cls.name}",
                entity_type="CODE_CLASS",
                source_system="code_scanner",
                source_id=str(file_path)
            )
            self.graph.add_entity(class_entity)
            
            # Extract documentation fragments from docstring
            fragments = self.parser.extract_fragments(cls.docstring)
            
            for fragment in fragments:
                # Create entity for documentation fragment
                frag_entity = Entity(
                    primary_name=fragment.title,
                    entity_type="DOC_FRAGMENT",
                    source_system="code_annotations",
                    source_id=f"{file_path}:{cls.name}:{fragment.type}"
                )
                self.graph.add_entity(frag_entity)
                
                # Link fragment to class
                self.graph.add_relationship(Relationship(
                    from_entity_id=frag_entity.entity_id,
                    relationship_type="EXTRACTED_FROM",
                    to_entity_id=class_entity.entity_id,
                    source_system="doc_automation"
                ))
                
                # Add claims for document types
                for doc_type in fragment.doc_types:
                    self.graph.add_claim(IdentifierClaim(
                        entity_id=frag_entity.entity_id,
                        scheme="DOC_TYPE",
                        identifier=doc_type,
                        value=fragment.sections.get(doc_type),  # Section name
                        confidence=fragment.priority / 10.0
                    ))
                
                # Add tags
                for tag in fragment.tags:
                    self.graph.add_claim(IdentifierClaim(
                        entity_id=frag_entity.entity_id,
                        scheme="TAG",
                        identifier=tag,
                        confidence=1.0
                    ))
```

---

## 📊 Document Generation Orchestrator

```python
from doc_automation.orchestrator import DocumentationOrchestrator
from doc_automation.renderers import (
    ManifestoRenderer,
    FeaturesRenderer,
    ArchitectureRenderer,
    ADRRenderer,
    ChangelogRenderer,
    FeatureGuideRenderer
)

class DocumentationOrchestrator:
    """Orchestrate documentation generation across all types."""
    
    def __init__(self, project_root: Path, output_dir: Path):
        self.project_root = project_root
        self.output_dir = output_dir
        self.graph = None
    
    def generate_all(self):
        """Generate all documentation types."""
        
        # 1. Build knowledge graph
        builder = KnowledgeGraphBuilder(self.project_root)
        self.graph = builder.build()
        
        # 2. Generate core docs
        self._generate_manifesto()
        self._generate_features()
        self._generate_guardrails()
        
        # 3. Generate architecture docs
        self._generate_architecture()
        self._generate_core_primitives()
        self._generate_unified_data_model()
        
        # 4. Generate ADRs
        self._generate_adrs()
        
        # 5. Generate changelog
        self._generate_changelog()
        
        # 6. Generate feature guides
        self._generate_feature_guides()
        
        # 7. Generate API reference
        self._generate_api_reference()
        
        # 8. Update MkDocs nav
        self._update_mkdocs_nav()
    
    def _generate_manifesto(self):
        """Generate MANIFESTO.md from tagged fragments."""
        
        renderer = ManifestoRenderer(self.graph)
        content = renderer.render()
        
        output_path = self.output_dir / "MANIFESTO.md"
        output_path.write_text(content)
    
    def _generate_feature_guides(self):
        """Generate feature guides (e.g., RESOLUTION_GUIDE.md)."""
        
        # Query for all unique feature guide targets
        guide_targets = self.graph.query("""
            MATCH (frag:Entity {entity_type: 'DOC_FRAGMENT'})
            WHERE frag.feature_guide_target IS NOT NULL
            RETURN DISTINCT frag.feature_guide_target AS guide
        """)
        
        for guide_name in guide_targets:
            renderer = FeatureGuideRenderer(self.graph, guide_name)
            content = renderer.render()
            
            output_path = self.output_dir / "guides" / f"{guide_name}.md"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
    
    def _generate_changelog(self):
        """Generate CHANGELOG.md from git commits + annotations."""
        
        renderer = ChangelogRenderer(
            graph=self.graph,
            git_repo=self.project_root,
            since_version="v0.4.0"
        )
        content = renderer.render()
        
        output_path = self.output_dir / "CHANGELOG.md"
        output_path.write_text(content)
```

---

## 🚀 CLI: `docbuilder` Commands

Extended CLI for all document types:

```bash
# Generate all documentation
docbuilder build --all

# Generate specific doc type
docbuilder build MANIFESTO.md
docbuilder build guides/RESOLUTION_GUIDE.md
docbuilder build adrs/

# Generate from knowledge graph query
docbuilder query "fragments tagged 'architecture'" --output ARCHITECTURE.md

# Extract templates from existing docs
docbuilder extract-template \
    --source feedspine/docs/archive/design/DATA_ARCHETYPES_GUIDE.md \
    --template data_archetype_guide

# Generate from template
docbuilder generate \
    --template data_archetype_guide \
    --project market-spine \
    --output market-spine/docs/guides/DATA_ARCHETYPES_GUIDE.md

# Visualize knowledge graph
docbuilder graph --format mermaid > docs/DOC_GRAPH.md
docbuilder graph --format neo4j-cypher > docs/graph.cypher

# Update MkDocs navigation
docbuilder update-mkdocs --nav-from-graph

# Validate consistency
docbuilder validate --check-links --check-examples --check-versions
```

---

## 📈 Migration Strategy

### Phase 1: Template Extraction (Week 1-2)

```bash
# Extract templates from best existing docs
docbuilder extract-template \
    --source entityspine/docs/CORE_CONCEPTS.md \
    --template core_concepts

docbuilder extract-template \
    --source feedspine/docs/archive/design/DATA_ARCHETYPES_GUIDE.md \
    --template data_archetype_guide

docbuilder extract-template \
    --source entityspine/docs/architecture/UNIFIED_DATA_MODEL.md \
    --template unified_data_model
```

### Phase 2: Knowledge Graph Build (Week 3-4)

```python
# Annotate 10-20 core classes with extended format
# Build knowledge graph from annotations
# Verify fragments extracted correctly
```

### Phase 3: Generate First Docs (Week 5-6)

```bash
# Generate core docs from graph
docbuilder build MANIFESTO.md
docbuilder build FEATURES.md
docbuilder build guides/RESOLUTION_GUIDE.md

# Compare to hand-written versions
diff entityspine/docs/MANIFESTO.md entityspine/docs/MANIFESTO.md.generated
```

### Phase 4: Full Rollout (Week 7-12)

```bash
# Generate all doc types
docbuilder build --all

# CI/CD integration
# - Pre-commit hook: validate annotations
# - PR check: generate docs, diff against committed
# - Post-merge: regenerate and commit updated docs
```

---

## 🔗 Integration with MkDocs

Auto-update `mkdocs.yml` navigation from graph:

```yaml
# mkdocs.yml (auto-generated section)
nav:
  - Home: index.md
  - Core Docs:
      - Manifesto: MANIFESTO.md           # 🤖 Auto-generated
      - Features: FEATURES.md             # 🤖 Auto-generated
      - Guardrails: GUARDRAILS.md         # 🤖 Auto-generated
  - Architecture:
      - Overview: architecture/ARCHITECTURE.md  # 🤖 Auto-generated
      - Core Primitives: architecture/CORE_PRIMITIVES.md  # 🤖 Auto-generated
      - Data Model: architecture/UNIFIED_DATA_MODEL.md    # 🤖 Auto-generated
      - Tier Strategy: architecture/TIER_STRATEGY.md      # 🤖 Auto-generated
  - Guides:
      - Core Concepts: guides/CORE_CONCEPTS.md            # 🤖 Auto-generated
      - Resolution Guide: guides/RESOLUTION_GUIDE.md      # 🤖 Auto-generated
      - Data Archetypes: guides/DATA_ARCHETYPES_GUIDE.md  # 🤖 Auto-generated
  - ADRs:
      - Index: adrs/README.md             # 🤖 Auto-generated
      - 001: adrs/001-stdlib-only-domain.md  # 🤖 Auto-generated
      - 003: adrs/003-identifier-claims.md   # 🤖 Auto-generated
      - 008: adrs/008-resolution-pipeline.md # 🤖 Auto-generated
  - API Reference: api/                   # 🤖 Auto-generated from docstrings
  - Changelog: CHANGELOG.md               # 🤖 Auto-generated from git + annotations

# Comment in mkdocs.yml:
# ⚠️ Do not edit nav manually - regenerate with: docbuilder update-mkdocs
```

---

## 🎯 Success Metrics

**Month 3:**
- [ ] 20+ classes annotated with extended format
- [ ] Knowledge graph contains 100+ fragments
- [ ] 3 document types auto-generated (MANIFESTO, FEATURES, CHANGELOG)
- [ ] Templates extracted from 5+ existing docs

**Month 6:**
- [ ] All core docs auto-generated
- [ ] 5+ feature guides generated
- [ ] ADRs templated and generated
- [ ] MkDocs nav auto-updated

**Month 12:**
- [ ] All 8 projects using knowledge graph system
- [ ] 15+ document types auto-generated
- [ ] Zero manual doc updates for 3 months
- [ ] Documentation quality > hand-written (team feedback)

---

## 🔮 Future Enhancements

1. **Interactive Documentation**: Query graph in real-time via web UI
2. **Diff Visualization**: Show how docs changed between versions
3. **Search Integration**: Full-text search across knowledge graph
4. **Cross-Project Queries**: "Show me all classes that implement entity resolution across all projects"
5. **Doc Quality Metrics**: Completeness, freshness, example coverage
6. **LLM-Enhanced Diagrams**: Generate Mermaid/PlantUML from code structure

---

*Knowledge graphs: Because documentation is just another kind of entity.*
