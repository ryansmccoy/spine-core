# FEATURES

**What This Project Can Do**

*Auto-generated from code annotations on 2026-02-02*

---

## General

### DocumentationOrchestrator

- Build knowledge graph once, use for all docs
    - Generate all doc types or specific ones
    - Create output directory structure
    - Report generation statistics
    - Support custom configurations

*From [`DocumentationOrchestrator`](/app/projects/spine-core/src/doc-automation/src/doc_automation/orchestrator.py#L32)*

### DocumentationQuery

- Query by doc-type (MANIFESTO, FEATURES, etc.)
    - Query by tag
    - Query by section within doc-type
    - Get all fragments for a class
    - Get statistics about the graph
    - Sort results by priority

*From [`DocumentationQuery`](/app/projects/spine-core/src/doc-automation/src/doc_automation/graph/queries.py#L25)*

### ASTWalker

- Extract all classes from Python file
    - Get method signatures and docstrings
    - Track line numbers for source links
    - Detect dataclasses and decorators
    - Filter public vs private methods

*From [`ASTWalker`](/app/projects/spine-core/src/doc-automation/src/doc_automation/parser/ast_walker.py#L90)*

### DocstringParser

- Parse all standard sections (Manifesto, Architecture, Features, etc.)
    - Detect content format (markdown, python code, ASCII diagrams, mermaid)
    - Extract tags and doc-types
    - Generate unique fragment IDs
    - Track source provenance

*From [`DocstringParser`](/app/projects/spine-core/src/doc-automation/src/doc_automation/parser/docstring_parser.py#L71)*

### SectionExtractor

- Extract doctest examples from Examples section
    - Parse ADR references (number, title, path)
    - Parse changelog entries with version info
    - Extract performance metrics

*From [`SectionExtractor`](/app/projects/spine-core/src/doc-automation/src/doc_automation/parser/section_extractors.py#L79)*

### ADRRenderer

- Generate individual ADR files
    - Create ADR index
    - Extract ADR references from code
    - Link ADRs to implementing code

*From [`ADRRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/adr.py#L13)*

### APIReferenceRenderer

- List all public classes
    - Show method signatures
    - Include docstring summaries
    - Group by module

*From [`APIReferenceRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/api_reference.py#L12)*

### ArchitectureRenderer

- Table of Contents with anchors
    - Layered architecture overview
    - Clean ASCII diagram extraction
    - Component relationship tables
    - Source code links

*From [`ArchitectureRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/architecture.py#L21)*

### BaseRenderer

- Load Jinja2 templates from configurable directory
    - Query graph for fragments
    - Group fragments by section
    - Add metadata (timestamps, version, etc.)
    - Support custom template overrides

*From [`BaseRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/base.py#L18)*

### ChangelogRenderer

- Extract version history from code annotations
    - Group by version
    - Highlight breaking changes
    - Link to relevant code

*From [`ChangelogRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/changelog.py#L13)*

### FeaturesRenderer

- List all features from annotated classes
    - Group by category/section
    - Include code examples where available
    - Link to source code

*From [`FeaturesRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/features.py#L14)*

### GuardrailsRenderer

- Extract anti-patterns with "Do NOT"
    - Show correct alternatives with ✅
    - Group by category
    - Include rationale for each guardrail

*From [`GuardrailsRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/guardrails.py#L14)*

### ManifestoRenderer

- Table of Contents with section anchors
    - Problem/Solution framing
    - Boxed principle diagrams
    - Comparison tables
    - Source code links

*From [`ManifestoRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/manifesto.py#L22)*

### ComputeVolumePerDayPipeline

1. Year-boundary semantics: Handles weeks spanning year boundaries
2. Dependency helper: Standardized dependency checking
3. As-of mode: Pin to specific calendar capture_id for replay
4. Exchange code: Configurable exchange (XNYS, XNAS, etc.)

Params:
    week_ending: Week to compute (YYYY-MM-DD Friday)
    tier: Market tier (Tier1, Tier2, OTC)
    exchange_code: Exchange calendar to use (default: XNYS)
    calendar_capture_id: Optional specific calendar capture for as-of queries
    force: Recompute even if already done

*From [`ComputeVolumePerDayPipeline`](/app/projects/spine-core/src/spine-domains/src/spine/domains/finra/otc_transparency/pipelines.py#L1788)*

## Entity Resolution

### EntityResolver

- Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
    - Fuzzy name matching with confidence scores
    - Historical ticker resolution (what was AAPL on 2010-01-01?)
    - Batch resolution for efficiency
    - Entity metadata (industry, SIC code, filing status)

*From [`EntityResolver`](/app/projects/spine-core/src/doc-automation/tests/fixtures/sample_annotated_class.py#L9)*

## Data Feeds

### FeedAdapter

- Support multiple input formats (CSV, JSON, API)
    - Validate data against schema
    - Handle incremental updates
    - Track data lineage

*From [`FeedAdapter`](/app/projects/spine-core/src/doc-automation/tests/fixtures/sample_annotated_class.py#L187)*


---

*69 features documented across 3 categories*

*Generated by [doc-automation](https://github.com/your-org/py-sec-edgar/tree/main/spine-core/packages/doc-automation)*