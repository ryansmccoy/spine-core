# 📝 EXTENDED CODE ANNOTATION PROMPT

**For LLM: How to annotate Python code with comprehensive documentation metadata**

*You are annotating code to enable automatic generation of ALL documentation types via knowledge graph*

---

## 🎯 Your Mission

Add **extended docstrings** to Python classes and methods that include structured sections for:

1. **Core Docs**: Manifesto, Features, Guardrails
2. **Architecture**: Diagrams, primitives, data models
3. **Guides**: Feature guides, tutorials, examples
4. **ADRs**: Architecture Decision Records
5. **Changelog**: Version history
6. **API Reference**: Auto-generated from signatures

These annotations feed an **EntitySpine knowledge graph** that assembles documentation from code metadata.

---

## 📋 Extended Docstring Format

### Full Template (Use ALL applicable sections)

```python
class YourClass:
    """
    [ONE-LINE SUMMARY - REQUIRED]
    
    [DETAILED DESCRIPTION - 2-3 paragraphs explaining what this class does]
    
    Manifesto:
        [WHY THIS EXISTS - Core principles, philosophy, design rationale]
        
        [Include specific principles from project philosophy]
        [Explain trade-offs made]
        [Reference historical context or problems solved]
    
    Architecture:
        [HOW IT FITS IN THE SYSTEM - Structure, relationships, dependencies]
        
        ```
        [ASCII DIAGRAM showing structure or data flow]
        ```
        
        ```mermaid
        [MERMAID DIAGRAM - class diagram, sequence diagram, etc.]
        ```
        
        Storage: [Where/how data is stored]
        Caching: [Caching strategy if applicable]
        Concurrency: [Thread-safety, async patterns]
        Dependencies: [What this depends on]
        Dependents: [What depends on this]
    
    Features:
        - [FEATURE 1 - Brief description]
        - [FEATURE 2 - Brief description]
        - [FEATURE 3 - Brief description with example: `code_snippet()`]
        
        [For complex features, include sub-bullets with details]
    
    Examples:
        >>> [BASIC USAGE - Most common use case]
        >>> obj = YourClass()
        >>> result = obj.method()
        >>> result
        ExpectedOutput(...)
        
        >>> [ADVANCED USAGE - More complex scenario]
        >>> obj.advanced_method(param1, param2)
        ComplexOutput(...)
    
    Performance:
        - Latency: [Typical operation time]
        - Throughput: [Operations per second]
        - Memory: [Memory footprint]
        - Scaling: [How it scales with data size]
    
    Guardrails:
        - Do NOT [ANTI-PATTERN 1 - Why it's bad]
          ✅ Instead: [CORRECT APPROACH]
        
        - Do NOT [ANTI-PATTERN 2 - Why it's bad]
          ✅ Instead: [CORRECT APPROACH]
        
        - ALWAYS [REQUIRED PATTERN - Why it's necessary]
    
    Context:
        Problem: [What problem does this solve?]
        
        Solution: [How does this class solve it?]
        
        Alternatives Considered: [What else was tried? Why rejected?]
    
    ADR:
        - [NUMBER]-[slug].md: [Why this ADR is relevant]
        - [NUMBER]-[slug].md: [Another related ADR]
    
    Changelog:
        - v[VERSION]: [Major change]
        - v[VERSION]: [Breaking change]
        - v[VERSION]: [New feature]
    
    Feature-Guide:
        Target: guides/[GUIDE_NAME].md
        Section: "[SECTION NAME]"
        Include-Example: [True/False]
        Priority: [1-10]
    
    Unified-Data-Model:
        Target: architecture/UNIFIED_DATA_MODEL.md
        Section: "[SECTION NAME]"
        Diagram: [diagram_name]
        Schema-DDL: [True if includes SQL/schema]
    
    Architecture-Doc:
        Target: architecture/[DOC_NAME].md
        Section: "[SECTION NAME]"
        Diagram-Type: [ascii|mermaid|both]
    
    Tags:
        - [tag1]  # For retrieval/filtering
        - [tag2]
        - [tag3]
    
    Doc-Types:
        - MANIFESTO (section: "[SECTION]", priority: [1-10])
        - FEATURES (section: "[SECTION]", priority: [1-10])
        - ARCHITECTURE (section: "[SECTION]", priority: [1-10])
        - [OTHER_DOC_TYPE] (section: "[SECTION]", priority: [1-10])
    """
    
    def your_method(self, param: Type) -> ReturnType:
        """
        [ONE-LINE SUMMARY]
        
        [DETAILED DESCRIPTION]
        
        Args:
            param: [Description with type info and constraints]
        
        Returns:
            [Description of return value]
        
        Raises:
            ErrorType: [When this error is raised]
        
        Examples:
            >>> obj.your_method(value)
            ExpectedOutput(...)
        
        Feature-Guide:
            Target: guides/[GUIDE].md
            Section: "[SECTION]"
        
        Tags:
            - [method_tag1]
            - [method_tag2]
        """
        ...
```

---

## 🔍 Section-by-Section Guide

### **Manifesto Section**

**Purpose**: Explain WHY this class exists, what principles it embodies.

**What to include:**
- Core philosophy/principles it implements
- Design rationale and trade-offs
- Historical context or problems it solves
- References to project-wide principles

**Example (EntitySpine):**
```python
Manifesto:
    Entity ≠ Security ≠ Listing is fundamental to EntitySpine.
    
    This separation exists because:
    - One entity (Apple Inc.) can have multiple securities (stock, bonds, warrants)
    - One security (AAPL common) can have multiple listings (NASDAQ, BATS, IEX)
    - Conflating these leads to incorrect data joins and broken analytics
    
    We use CIK as the stable entity identifier because tickers change,
    companies reorganize, and securities get relisted.
    
    This decision prioritizes data integrity over convenience.
```

### **Architecture Section**

**Purpose**: Explain HOW this fits into the system, structure, relationships.

**What to include:**
- System architecture diagram (ASCII or Mermaid)
- Data flow diagrams
- Storage strategy
- Caching approach
- Dependencies and dependents
- Concurrency model

**Example (FeedSpine):**
```python
Architecture:
    ```
    External Feed (SEC EDGAR, FactSet, etc.)
              ↓
    FeedAdapter.fetch()
              ↓
    ┌─────────────────────────┐
    │  Normalization:         │
    │  1. Schema validation   │
    │  2. Type conversion     │
    │  3. Deduplication       │
    └───────────┬─────────────┘
                ↓
    FeedStore.insert()
              ↓
    ┌─────────────────────────┐
    │  Storage (Medallion):   │
    │  Bronze: Raw (S3)       │
    │  Silver: Clean (DuckDB) │
    │  Gold: Curated (PG)     │
    └─────────────────────────┘
    ```
    
    Storage: Medallion architecture (bronze/silver/gold)
    Caching: TTL-based (5min for metadata, 1hr for historical)
    Concurrency: Async/await with semaphore (max 10 concurrent)
    Dependencies: Pydantic (validation), DuckDB (storage)
```

### **Features Section**

**Purpose**: List WHAT this class can do - capabilities, API surface.

**What to include:**
- Bullet list of capabilities
- Brief description per feature
- Inline code examples for clarity
- Grouping by category if many features

**Example (EntitySpine):**
```python
Features:
    - Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
    - Fuzzy name matching (Levenshtein distance < 3)
    - Ticker disambiguation (AAPL 1980 ≠ AAPL 2020)
    - Historical ticker resolution (time-aware)
    - Bulk resolution (batch API for 1000+ identifiers)
    - Entity metadata (industry, SIC code, filing status)
    - Caching (LRU 10K entities, ~50MB memory)
    - Fallback to SEC EDGAR API for missing entities
```

### **Examples Section**

**Purpose**: Show runnable code demonstrating usage.

**What to include:**
- Basic usage (most common case)
- Advanced usage (complex scenarios)
- Edge cases if relevant
- Use doctest format (`>>>`)

**Example:**
```python
Examples:
    >>> resolver = EntityResolver()
    >>> entity = resolver.resolve("AAPL")
    >>> entity.cik
    '0000320193'
    >>> entity.name
    'Apple Inc.'
    
    # Historical resolution
    >>> entity = resolver.resolve("FB", as_of=date(2021, 1, 1))
    >>> entity.name
    'Facebook Inc'  # Pre-Meta rebrand
    
    # Bulk resolution
    >>> entities = resolver.resolve_bulk(["AAPL", "MSFT", "GOOGL"])
    >>> len(entities)
    3
```

### **Performance Section**

**Purpose**: Set expectations for speed, resource usage, scaling.

**What to include:**
- Typical latency (cached vs uncached)
- Throughput (operations/second)
- Memory footprint
- Scaling behavior with data size
- Benchmarks if available

**Example:**
```python
Performance:
    - Single lookup: <1ms (cached), <10ms (uncached)
    - Bulk resolution: ~50 identifiers/second
    - Memory: ~50MB for 10K cached entities
    - Storage: ~500MB for full SEC entity universe (18K issuers)
    - Scaling: O(1) for CIK lookup, O(log n) for name search
```

### **Guardrails Section**

**Purpose**: Warn about anti-patterns, constraints, what NOT to do.

**What to include:**
- Common mistakes and why they fail
- Correct alternative for each anti-pattern
- Required patterns ("ALWAYS do X")
- Constraints and limitations

**Example:**
```python
Guardrails:
    - Do NOT use ticker as primary key (tickers change!)
      ✅ Instead: Use CIK as stable entity identifier
    
    - Do NOT assume one-to-one ticker → entity
      ✅ Instead: Always call resolve() which handles disambiguation
    
    - Do NOT skip validation (always check resolve() returns non-None)
      ✅ Instead: Handle None case explicitly
    
    - Do NOT mix entity and security identifiers
      ✅ Instead: Use EntityResolver for entities, SecurityResolver for securities
    
    - ALWAYS provide as_of date for backtesting
      (prevents lookahead bias with restated data)
```

### **Context Section**

**Purpose**: Background - problem space, motivation, alternatives considered.

**What to include:**
- What problem does this solve?
- Why was this approach chosen?
- What alternatives were considered and rejected?
- Evolution over time

**Example:**
```python
Context:
    Problem: Most financial systems treat "ticker" as primary key,
    causing breakage when companies change tickers (e.g., FB → META),
    merge, or reorganize.
    
    Solution: Use CIK (Central Index Key) as stable entity identifier,
    map all other identifiers (ticker, CUSIP, name) to CIK via
    claims-based resolution.
    
    Alternatives Considered:
    - LEI (Legal Entity Identifier): Not available for all US issuers
    - CUSIP: Changes with security issuance, not entity-level
    - Name: Too unstable (frequent minor changes)
    
    Why CIK: Assigned by SEC, never changes, required for all filers,
    publicly available, covers full SEC universe.
```

### **ADR Section**

**Purpose**: Link to Architecture Decision Records that explain key decisions.

**What to include:**
- ADR numbers and slugs
- Brief explanation of why each ADR is relevant

**Example:**
```python
ADR:
    - 003-identifier-claims.md: Why we model identifiers as claims
    - 008-resolution-pipeline-and-claims.md: Resolution algorithm design
    - 001-stdlib-only-domain.md: Why no dependencies in entity resolution
```

### **Changelog Section**

**Purpose**: Track major changes to this class over versions.

**What to include:**
- Version number and change description
- Focus on breaking changes and major features
- Keep brief (detailed changelog in CHANGELOG.md)

**Example:**
```python
Changelog:
    - v0.3.0: Added fuzzy name matching
    - v0.4.0: Implemented claims-based resolution (BREAKING: API change)
    - v0.5.0: Added historical ticker support (as_of parameter)
    - v0.6.0: Bulk resolution API for performance
```

### **Feature-Guide Section**

**Purpose**: Specify which feature guide(s) should include this class.

**What to include:**
- Target guide file
- Section name within guide
- Whether to include examples
- Priority (1-10, higher = more important)

**Example:**
```python
Feature-Guide:
    Target: guides/RESOLUTION_GUIDE.md
    Section: "How Entity Resolution Works"
    Include-Example: True
    Priority: 10
```

### **Unified-Data-Model Section**

**Purpose**: Include this in UNIFIED_DATA_MODEL.md if it defines core schema.

**What to include:**
- Target document
- Section name
- Diagram name (for architecture diagrams)
- Whether to include DDL/schema

**Example:**
```python
Unified-Data-Model:
    Target: architecture/UNIFIED_DATA_MODEL.md
    Section: "Entity Resolution Schema"
    Diagram: entity-security-listing-hierarchy
    Schema-DDL: True
```

### **Tags Section**

**Purpose**: Enable multi-dimensional retrieval and filtering.

**What to include:**
- Functional tags (what it does)
- Domain tags (what area)
- Technical tags (how it works)

**Example:**
```python
Tags:
    - core_concept
    - entity_resolution
    - identifier_disambiguation
    - claims_based_identity
    - sec_data
    - caching
```

### **Doc-Types Section**

**Purpose**: Specify which document types should include this class and where.

**What to include:**
- Document type (MANIFESTO, FEATURES, ARCHITECTURE, etc.)
- Section name within that doc
- Priority (1-10, controls ordering)

**Example:**
```python
Doc-Types:
    - MANIFESTO (section: "Core Principles", priority: 10)
    - FEATURES (section: "Resolution", priority: 9)
    - ARCHITECTURE (section: "Data Model", priority: 8)
    - GUARDRAILS (section: "Identity Management", priority: 9)
    - API_REFERENCE (section: "Core APIs", priority: 10)
```

---

## 🎯 Annotation Strategy

### Step 1: Identify Annotation Targets (15 minutes)

For the assigned project, identify:

**Tier 1 (MUST annotate - 5-10 classes):**
- Core domain classes
- Public API classes
- Classes that embody key principles

**Tier 2 (SHOULD annotate - 20-30 classes):**
- Important utilities
- Storage/persistence classes
- Integration points

**Tier 3 (NICE TO HAVE - remaining classes):**
- Helper classes
- Internal utilities
- Simple data classes

### Step 2: Research Before Annotating (10 min per class)

Before writing docstring:

1. **Read the code** - Understand what it does
2. **Check existing docs** - Look in `docs/` and `docs/archive/`
3. **Check ADRs** - Look in `docs/adrs/`
4. **Check tests** - See how it's used
5. **Check git history** - See why it was created (`git log -p <file>`)

### Step 3: Write Extended Docstring (20-30 min per Tier 1 class)

Use the full template above. Include ALL applicable sections:

**Required for Tier 1 classes:**
- ✅ Summary and detailed description
- ✅ Manifesto
- ✅ Architecture
- ✅ Features
- ✅ Examples
- ✅ Guardrails
- ✅ Tags
- ✅ Doc-Types

**Optional but recommended:**
- Performance (if relevant)
- Context (if design rationale exists)
- ADR (if related ADRs exist)
- Changelog (if major version changes)
- Feature-Guide (if should be in guide)
- Unified-Data-Model (if defines schema)

### Step 4: Validate (5 min per class)

**Self-check:**
- [ ] Manifesto explains WHY (not just what)
- [ ] Architecture shows HOW it fits
- [ ] Features list WHAT it can do
- [ ] Examples are runnable (use doctest format)
- [ ] Guardrails warn about anti-patterns
- [ ] Tags enable retrieval
- [ ] Doc-Types specify where this appears

**Completeness check:**
```python
# Required sections present?
required = ["Manifesto", "Architecture", "Features", "Examples", "Guardrails"]
# At least 3 tags?
# At least 2 doc-types?
```

### Step 5: Test Extraction (When parser is ready)

```bash
docbuilder extract src/your_class.py --validate
# Should show structured extraction with all sections
```

---

## 📚 Project-Specific Examples

### EntitySpine Example

```python
class EntityResolver:
    """
    Resolve any identifier (CIK, ticker, name, CUSIP, ISIN) to canonical entity.
    
    Central component of EntitySpine implementing the Entity ≠ Security ≠ Listing
    separation principle. Maps identifiers to stable CIK-based entities.
    
    Manifesto:
        Entity ≠ Security ≠ Listing is fundamental to EntitySpine.
        
        This separation exists because:
        - One entity (Apple Inc.) can issue multiple securities
        - One security can have multiple listings (exchanges)
        - Conflating these breaks analytics and data joins
        
        We use CIK as stable identifier because tickers change,
        securities relist, and companies reorganize.
    
    Architecture:
        ```
        Identifier (any type: CIK, ticker, CUSIP, name)
              ↓
        EntityResolver.resolve()
              ↓
        ┌─────────────────────────┐
        │  Resolution Pipeline:   │
        │  1. CIK direct lookup   │
        │  2. Ticker → CIK map    │
        │  3. Name fuzzy match    │
        │  4. CUSIP → CIK map     │
        │  5. Fallback: SEC API   │
        └───────────┬─────────────┘
                    ↓
          Canonical Entity (with CIK)
        ```
        
        Storage: SQLite (T1), DuckDB (T2), PostgreSQL (T3)
        Caching: LRU 10K entities (~50MB)
        Dependencies: None (stdlib only per ADR-001)
    
    Features:
        - Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
        - Fuzzy name matching (Levenshtein < 3)
        - Ticker disambiguation (time-aware)
        - Historical resolution (as_of parameter)
        - Bulk API (1000+ identifiers)
        - SEC API fallback (missing entities)
    
    Examples:
        >>> resolver = EntityResolver()
        >>> entity = resolver.resolve("AAPL")
        >>> entity.cik
        '0000320193'
        
        # Historical
        >>> entity = resolver.resolve("FB", as_of=date(2021, 1, 1))
        >>> entity.name
        'Facebook Inc'
    
    Performance:
        - Single: <1ms cached, <10ms uncached
        - Bulk: ~50 identifiers/sec
        - Memory: ~50MB (10K entities)
        - Scaling: O(1) CIK, O(log n) name
    
    Guardrails:
        - Do NOT use ticker as primary key
          ✅ Instead: Use CIK
        - Do NOT assume ticker → entity is 1:1
          ✅ Instead: Handle disambiguation
        - ALWAYS check resolve() returns non-None
    
    Context:
        Problem: Ticker-as-primary-key breaks on reorganizations
        Solution: CIK-based stable identity with claim resolution
        Alternatives: LEI (incomplete), CUSIP (security-level)
    
    ADR:
        - 003-identifier-claims.md: Claims-based resolution
        - 008-resolution-pipeline-and-claims.md: Pipeline design
    
    Changelog:
        - v0.4.0: Claims-based resolution (BREAKING)
        - v0.5.0: Historical ticker support
    
    Feature-Guide:
        Target: guides/RESOLUTION_GUIDE.md
        Section: "How Entity Resolution Works"
        Include-Example: True
        Priority: 10
    
    Unified-Data-Model:
        Target: architecture/UNIFIED_DATA_MODEL.md
        Section: "Entity Resolution"
        Diagram: entity-security-listing-hierarchy
    
    Tags:
        - core_concept
        - entity_resolution
        - identifier_claims
        - sec_data
    
    Doc-Types:
        - MANIFESTO (section: "Core Principles", priority: 10)
        - FEATURES (section: "Resolution", priority: 9)
        - ARCHITECTURE (section: "Data Model", priority: 8)
        - API_REFERENCE (section: "Core APIs", priority: 10)
    """
```

### FeedSpine Example

```python
class FeedAdapter:
    """
    Base adapter for financial data feeds with medallion architecture.
    
    Abstract base defining interface for fetching, normalizing, and storing
    data from external sources (SEC EDGAR, FactSet, Bloomberg, etc.).
    
    Manifesto:
        Data quality gates prevent garbage-in-garbage-out.
        
        The medallion architecture (bronze/silver/gold) ensures:
        - Bronze: Preserve raw data exactly as received
        - Silver: Apply validation and normalization
        - Gold: Curate for analytics (denormalize, aggregate)
        
        This multi-tier approach enables data lineage tracking and
        debugging when issues arise.
    
    Architecture:
        ```
        External Feed → fetch() → validate() → normalize() → store()
                                      ↓            ↓           ↓
                                  [BRONZE]    [SILVER]    [GOLD]
                                  Raw S3      Clean       Curated
                                              DuckDB      PostgreSQL
        ```
        
        Storage: Medallion (bronze/silver/gold)
        Validation: Pydantic schemas per feed
        Deduplication: Content-addressed hashing
        Concurrency: Async with semaphore (max 10)
    
    Features:
        - Schema validation (Pydantic)
        - Automatic retry with exponential backoff
        - Rate limiting (per-feed configurable)
        - Deduplication (content-addressed)
        - Medallion storage (bronze/silver/gold)
        - Provenance tracking (source, timestamp, version)
    
    Examples:
        >>> adapter = SECFeedAdapter()
        >>> async for item in adapter.fetch(since="2024-01-01"):
        ...     await adapter.store(item)
    
    Performance:
        - Throughput: ~100 items/sec (network-bound)
        - Memory: <100MB per adapter instance
        - Storage: ~1GB/day for SEC EDGAR (all forms)
    
    Guardrails:
        - Do NOT skip bronze layer (always preserve raw)
          ✅ Instead: Store raw in S3, then transform
        - Do NOT mutate raw data
          ✅ Instead: Create new normalized version
        - ALWAYS track provenance (source, timestamp)
    
    Context:
        Problem: Data quality issues compound downstream
        Solution: Multi-tier medallion with quality gates
        Alternatives: Single-tier (no lineage), schema-on-read (slow)
    
    ADR:
        - 002-medallion-architecture.md: Bronze/silver/gold design
    
    Changelog:
        - v0.2.0: Added medallion architecture
        - v0.3.0: Pydantic validation
    
    Feature-Guide:
        Target: guides/FEED_ADAPTER_GUIDE.md
        Section: "Creating Custom Adapters"
        Include-Example: True
        Priority: 10
    
    Architecture-Doc:
        Target: architecture/FEED_ARCHITECTURE.md
        Section: "Adapter Pattern"
        Diagram-Type: mermaid
    
    Tags:
        - core_concept
        - data_ingestion
        - medallion_architecture
        - validation
    
    Doc-Types:
        - MANIFESTO (section: "Data Quality", priority: 9)
        - FEATURES (section: "Adapters", priority: 10)
        - ARCHITECTURE (section: "Feed System", priority: 10)
        - API_REFERENCE (section: "Adapters", priority: 8)
    """
```

---

## ✅ Validation Checklist

Before submitting annotated code:

### Completeness
- [ ] All Tier 1 classes have extended docstrings
- [ ] Manifesto section explains WHY
- [ ] Architecture section shows HOW
- [ ] Features section lists WHAT
- [ ] Examples are runnable (doctest format)
- [ ] Guardrails warn about anti-patterns
- [ ] At least 3 tags per class
- [ ] At least 2 doc-types per class

### Quality
- [ ] Manifesto references project principles
- [ ] Architecture includes diagram (ASCII or Mermaid)
- [ ] Features are complete and accurate
- [ ] Examples cover basic and advanced usage
- [ ] Guardrails include both "Don't" and "Do" alternatives
- [ ] Tags enable retrieval
- [ ] Doc-Types specify section and priority

### Consistency
- [ ] Terminology matches project glossary
- [ ] Examples use consistent variable names
- [ ] Section names match across classes
- [ ] Priority scores are calibrated (10 = most important)

### Extraction Test
```bash
# When parser is ready:
docbuilder extract src/ --validate
# Should show:
# - All sections parsed correctly
# - No syntax errors in examples
# - Tags and doc-types recognized
```

---

## 🚀 Getting Started

### 1. Choose Your Project
Pick one of: entityspine, feedspine, genai-spine, capture-spine, market-spine

### 2. Read Project Docs
- MANIFESTO.md (if exists)
- docs/architecture/
- docs/guides/
- docs/adrs/
- README.md

### 3. Identify Tier 1 Classes (5-10 classes)
Look for classes that:
- Implement core domain logic
- Are public API entry points
- Embody key design principles

### 4. Annotate First Class (30-40 min)
Use full extended template with ALL sections

### 5. Get Feedback
Submit one annotated class for review before batch

### 6. Batch Annotate Remaining
Once format approved, annotate remaining classes

---

## 📖 Additional Resources

- **KNOWLEDGE_GRAPH_DOCUMENTATION.md** - How annotations become docs
- **IMPLEMENTATION_PROMPT.md** - How to build the doc generator
- **Template Examples** - See `feedspine/docs/archive/design/DATA_ARCHETYPES_GUIDE.md`

---

*Structured annotations → Knowledge graph → Beautiful documentation*
