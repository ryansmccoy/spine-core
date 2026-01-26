# 📚 Documentation Automation Package - README

**Self-documenting code system using EntitySpine knowledge graphs**

*Automatically generate ALL documentation types from code annotations*

---

## 🎯 What Is This?

A **knowledge graph-based documentation system** that:

1. **Annotates code** with extended docstrings containing structured metadata
2. **Builds EntitySpine graph** modeling documentation fragments as entities
3. **Queries graph** to assemble documents
4. **Generates 20+ doc types**: MANIFESTO, FEATURES, architecture diagrams, ADRs, changelogs, feature guides, API reference, and more
5. **Integrates with MkDocs** for multi-page documentation sites
6. **Preserves examples** from existing docs and reuses them

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE GRAPH WORKFLOW                      │
│                                                                  │
│  Python Code                EntitySpine Graph         Generated │
│  (annotated)                (doc metadata)             Docs     │
│                                                                  │
│  class Entity:              Entity("manifesto_1")    MANIFESTO  │
│    """                           ↓                      .md     │
│    Manifesto:          Claim(DOC_TYPE="MANIFESTO")             │
│      Core principle    Claim(TAG="core_concept")     FEATURES  │
│                                 ↓                       .md     │
│    Architecture:       Relationship(                            │
│      [diagram]           EXTRACTED_FROM → class)     guides/    │
│    """                          ↓                    GUIDE.md   │
│         ↓                       ↓                       ↓        │
│    Docstring Parser    Query Graph Builder      Renderers     │
│         ↓                       ↓                       ↓        │
│    Extract Sections    Assemble by               Templates    │
│    (Manifesto,          doc-type + section           +         │
│     Architecture,                                  Jinja2      │
│     Features, etc.)                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📂 Package Structure

```
doc-automation/
├── README.md                       # 📍 You are here
├── TRACKER.md                      # 12-month implementation roadmap
├── design/
│   ├── KNOWLEDGE_GRAPH_DOCUMENTATION.md   # System architecture & design
│   └── SELF_DOCUMENTING_CODE.md           # Original feature design
├── prompts/                        # 🤖 Prompts for LLM implementation
│   ├── LLM_DECISION_PROMPT.md              # Choose implementation approach
│   ├── EXTENDED_ANNOTATION_PROMPT.md       # How to annotate code
│   ├── IMPLEMENTATION_PROMPT.md            # How to build the system
│   ├── VALIDATION_PROMPT.md                # How to validate quality
│   ├── CODE_ANNOTATION_PROMPT.md           # Original annotation guide
│   └── DOC_CLEANUP_PROMPT.md               # Doc organization guide
├── src/                            # (To be implemented)
│   └── doc_automation/
│       ├── parser/                 # Docstring parsing
│       ├── graph/                  # Knowledge graph builder
│       ├── renderers/              # Document generators
│       ├── templates/              # Jinja2 templates
│       ├── extractors/             # Mine existing docs for templates
│       └── orchestrator.py         # Main orchestration
├── tests/                          # (To be implemented)
│   └── test_*.py
└── examples/                       # (To be implemented)
    └── annotated_class.py
```

---

## 🚀 Quick Start

### For Annotators (Adding Extended Docstrings)

**Read this:**
- [prompts/EXTENDED_ANNOTATION_PROMPT.md](prompts/EXTENDED_ANNOTATION_PROMPT.md) - **START HERE**: Complete guide to annotating code

**Example annotation:**
```python
class EntityResolver:
    """
    Resolve any identifier to canonical entity.
    
    Manifesto:
        Entity ≠ Security ≠ Listing is fundamental.
        We use CIK as stable identifier because tickers change.
    
    Architecture:
        ```
        Identifier → resolve() → CIK lookup → Entity
        ```
        
        Storage: SQLite (T1), DuckDB (T2), PostgreSQL (T3)
        Caching: LRU 10K entities (~50MB)
    
    Features:
        - Multi-identifier support (CIK, ticker, CUSIP, name)
        - Fuzzy name matching (Levenshtein < 3)
        - Historical resolution (as_of parameter)
    
    Examples:
        >>> resolver = EntityResolver()
        >>> entity = resolver.resolve("AAPL")
        >>> entity.cik
        '0000320193'
    
    Guardrails:
        - Do NOT use ticker as primary key
          ✅ Instead: Use CIK
    
    Tags:
        - core_concept
        - entity_resolution
        - sec_data
    
    Doc-Types:
        - MANIFESTO (section: "Core Principles", priority: 10)
        - FEATURES (section: "Resolution", priority: 9)
        - ARCHITECTURE (section: "Data Model", priority: 8)
    """
```

**Commands:**
```bash
# Validate your annotations
docbuilder validate src/your_class.py

# Extract and preview
docbuilder extract src/your_class.py --format json
```

---

### For Implementers (Building the System)

**Read these in order:**

1. **[design/KNOWLEDGE_GRAPH_DOCUMENTATION.md](design/KNOWLEDGE_GRAPH_DOCUMENTATION.md)**
   - Full system architecture
   - EntitySpine integration design
   - Extended document types (20+ types)
   - Query patterns
   - Migration strategy

2. **[prompts/IMPLEMENTATION_PROMPT.md](prompts/IMPLEMENTATION_PROMPT.md)** - **CRITICAL**
   - Step-by-step implementation guide
   - Phase 1: Docstring Parser (Week 1-2)
   - Phase 2: Knowledge Graph Builder (Week 3-4)
   - Phase 3: Document Renderers (Week 5-7)
   - Phase 4: CLI & Orchestration (Week 8-9)
   - Complete code samples for each phase

3. **[prompts/VALIDATION_PROMPT.md](prompts/VALIDATION_PROMPT.md)**
   - How to validate quality
   - Test strategies
   - Success criteria

**Timeline:**
- **Weeks 1-2**: Build docstring parser
- **Weeks 3-4**: Build knowledge graph
- **Weeks 5-7**: Build renderers (MANIFESTO, FEATURES, etc.)
- **Weeks 8-9**: Build CLI & orchestration
- **Month 3+**: See [TRACKER.md](TRACKER.md)

---

## 📖 Documentation Types

This system can generate **20+ documentation types**:

### Core Docs
- **MANIFESTO.md** - Philosophy, principles, "why this exists"
- **FEATURES.md** - What it can do, capabilities
- **GUARDRAILS.md** - What NOT to do, anti-patterns

### Architecture Docs
- **ARCHITECTURE.md** - High-level system design
- **CORE_PRIMITIVES.md** - Foundational building blocks
- **UNIFIED_DATA_MODEL.md** - Canonical schema
- **TIER_STRATEGY.md** - Progressive complexity

### Process Docs
- **ADRs/** - Architecture Decision Records
- **CHANGELOG.md** - Version history
- **MIGRATION_GUIDES.md** - Upgrade guides
- **DEPRECATION_NOTICES.md** - What's being sunset

### Feature Docs
- **guides/RESOLUTION_GUIDE.md** - Feature-specific guides
- **guides/DATA_ARCHETYPES_GUIDE.md** - Domain concepts
- **EXAMPLES/** - Runnable code examples
- **TUTORIALS/** - Step-by-step walkthroughs

### Developer Docs
- **CONTRIBUTING.md** - How to contribute
- **CODE_STANDARDS.md** - Coding conventions
- **TESTING_GUIDE.md** - How to test
- **API_REFERENCE.md** - Auto-generated API docs

### Context Docs
- **CONTEXT.md** - Problem space, motivation
- **GLOSSARY.md** - Terms and definitions
- **FAQ.md** - Frequently asked questions

---

## 🧩 How It Works

### 1. Annotate Code

Add extended docstrings with structured sections:

```python
class YourClass:
    """
    Summary line.
    
    Manifesto:
        [Why this exists, core principles]
    
    Architecture:
        [How it fits in the system, diagrams]
    
    Features:
        - [Feature 1]
        - [Feature 2]
    
    Examples:
        >>> obj = YourClass()
        >>> obj.method()
    
    Guardrails:
        - Do NOT [anti-pattern]
          ✅ Instead: [correct approach]
    
    Tags:
        - [tag1]
        - [tag2]
    
    Doc-Types:
        - MANIFESTO (section: "Core", priority: 10)
        - FEATURES (section: "Capabilities", priority: 9)
    """
```

### 2. Build Knowledge Graph

System scans code and builds EntitySpine graph:

```python
# Entities
Entity(type="CODE_CLASS", name="EntityResolver")
Entity(type="DOC_FRAGMENT", name="Entity ≠ Security principle")

# Claims
IdentifierClaim(scheme="DOC_TYPE", identifier="MANIFESTO", value="Core Principles")
IdentifierClaim(scheme="TAG", identifier="core_concept")

# Relationships
Relationship(from=fragment, to=class, type="EXTRACTED_FROM")
```

### 3. Query Graph & Generate Docs

Renderers query graph and assemble documents:

```python
# Query for MANIFESTO fragments
fragments = graph.query("""
    MATCH (frag:DOC_FRAGMENT)-[:TAGGED_FOR]->(doc {name: 'MANIFESTO'})
    RETURN frag
    ORDER BY frag.priority DESC
""")

# Render using template
content = template.render(fragments=fragments)
```

### 4. Output Beautiful Docs

```markdown
# MANIFESTO

## Core Principles

### Entity ≠ Security ≠ Listing

This separation is fundamental because...

*From [`EntityResolver`](src/entityspine/resolver.py#L42)*

---

*Auto-generated from 15 code annotations on 2026-02-01*
```

---

## 🎯 Key Features

### Knowledge Graph Approach
- Uses **EntitySpine itself** to model documentation metadata
- Documentation fragments are entities with claims and relationships
- Query graph to assemble any document type
- Track provenance (which code generated which docs)

### Extended Annotations
- 15+ docstring sections beyond basic description
- Manifesto (WHY), Architecture (HOW), Features (WHAT)
- Examples, Performance, Guardrails, Context, ADRs, Changelog
- Tags for multi-dimensional retrieval
- Doc-Types specify where content appears

### Template Mining
- Extract structure from existing good docs
- Reuse examples from archive/
- Preserve institutional knowledge
- Apply templates to new projects

### MkDocs Integration
- Auto-generate navigation from graph
- Multi-page documentation sites
- Proper section hierarchy
- Cross-references

### Quality Assurance
- Doctest validation (examples must run)
- Consistency checks
- Completeness metrics
- Automated validation pipeline

---

## 📊 Implementation Status

**Current Status: Design & Prompts Complete** ✅

See [TRACKER.md](TRACKER.md) for detailed 12-month roadmap.

### Completed
- [x] System architecture designed
- [x] Knowledge graph model defined
- [x] Extended annotation format specified
- [x] Implementation guide written
- [x] Validation strategy defined
- [x] CLI commands designed
- [x] Templates structure defined

### Next Steps
1. **Implement docstring parser** (Week 1-2)
2. **Build knowledge graph builder** (Week 3-4)
3. **Create renderers** (Week 5-7)
4. **Build CLI** (Week 8-9)
5. **Annotate first project** (Month 3)
6. **Rollout to all projects** (Month 4-6)

---

## 🤝 Contributing

### Annotating Code

1. Read [prompts/EXTENDED_ANNOTATION_PROMPT.md](prompts/EXTENDED_ANNOTATION_PROMPT.md)
2. Choose a Tier 1 class from your project
3. Add extended docstring with all sections
4. Validate: `docbuilder validate your_file.py`
5. Submit PR with annotated code

### Implementing System

1. Read [prompts/IMPLEMENTATION_PROMPT.md](prompts/IMPLEMENTATION_PROMPT.md)
2. Pick a phase (parser, graph, renderers, CLI)
3. Implement following the guide
4. Write tests (see [prompts/VALIDATION_PROMPT.md](prompts/VALIDATION_PROMPT.md))
5. Submit PR with implementation

### Creating Templates

1. Identify good existing docs in archive/
2. Extract structure and patterns
3. Create Jinja2 template
4. Document in `templates/README.md`
5. Submit PR with template

---

## 📚 Reference Documentation

### For Annotators
- **[prompts/EXTENDED_ANNOTATION_PROMPT.md](prompts/EXTENDED_ANNOTATION_PROMPT.md)** - Complete annotation guide
- **[prompts/CODE_ANNOTATION_PROMPT.md](prompts/CODE_ANNOTATION_PROMPT.md)** - Original format (basic)
- **[design/KNOWLEDGE_GRAPH_DOCUMENTATION.md](design/KNOWLEDGE_GRAPH_DOCUMENTATION.md)** - Understanding the system

### For Implementers
- **[prompts/IMPLEMENTATION_PROMPT.md](prompts/IMPLEMENTATION_PROMPT.md)** - Build the system (9 weeks)
- **[prompts/VALIDATION_PROMPT.md](prompts/VALIDATION_PROMPT.md)** - Validate quality
- **[TRACKER.md](TRACKER.md)** - 12-month roadmap

### For Strategists
- **[prompts/LLM_DECISION_PROMPT.md](prompts/LLM_DECISION_PROMPT.md)** - Choose implementation approach
- **[prompts/DOC_CLEANUP_PROMPT.md](prompts/DOC_CLEANUP_PROMPT.md)** - Organize existing docs
- **[design/SELF_DOCUMENTING_CODE.md](design/SELF_DOCUMENTING_CODE.md)** - Original feature design

---

## 💡 Philosophy

**Core Principle:** Documentation is just another kind of entity.

Instead of treating docs as flat files that drift out of sync, model them as a **knowledge graph** where:
- Code classes are entities
- Documentation fragments are entities
- Tags enable multi-dimensional retrieval
- Relationships track provenance
- Queries assemble any document type

This approach:
- ✅ Keeps docs with code (docstrings)
- ✅ Enables DRY (query graph for any doc type)
- ✅ Tracks provenance (which code generated which docs)
- ✅ Enables evolution (query "show me all features added in v0.5.0")
- ✅ Leverages EntitySpine (dogfooding our own tech)

---

## 🔮 Future Vision

**Short-term (Months 1-6):**
- Build core system (parser, graph, renderers)
- Annotate 5-10 core classes per project
- Generate basic docs (MANIFESTO, FEATURES, GUARDRAILS)

**Medium-term (Months 7-12):**
- Generate all doc types (ADRs, guides, diagrams, changelogs)
- MkDocs integration
- CI/CD integration (pre-commit hooks, PR checks)
- Template library from existing docs

**Long-term (Year 2+):**
- Interactive documentation (query graph in real-time)
- LLM-enhanced generation (improve quality)
- Cross-project queries ("show all entity resolution across all projects")
- Documentation quality metrics
- Visual documentation browser

---

## 📞 Contact & Support

- **Issues**: File in spine-core repo
- **Questions**: See prompts/ directory
- **Design Discussions**: See design/ directory

---

## 📄 License

Same as parent project (py-sec-edgar)

---

**Current Stats:**
- 📁 **8 comprehensive guides** (~141 KB total)
- 🤖 **4 LLM-ready prompts** for implementation
- 🏗️ **System architecture** fully designed
- 📖 **20+ document types** supported
- ⏱️ **12-month roadmap** defined

**Status: Ready for implementation** ✅

---

*Documentation should write itself. Let's make it happen.*
