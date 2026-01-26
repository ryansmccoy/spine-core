# 🏢 EntitySpine - Annotation Guide

**Project-Specific Guide for Annotating EntitySpine Classes**

*For use with Documentation Automation Package - February 2026*

---

## 📋 PROJECT CONTEXT

### What is EntitySpine?

**EntitySpine** is a zero-dependency entity resolution system for SEC EDGAR data that solves the fundamental problem:

> *"Is CIK 0000320193 the same company as ticker AAPL on NASDAQ?"*

### Core Philosophy

**Principle #1: Entity ≠ Security ≠ Listing**

This is THE foundational principle of EntitySpine:
- One **entity** (Apple Inc.) can issue multiple **securities** (common stock, bonds, warrants)
- One **security** (AAPL common stock) can have multiple **listings** (NASDAQ, BATS, IEX)
- Conflating these levels leads to incorrect data joins and broken analytics

**Principle #2: Stdlib-Only Domain Layer**

The core domain (`src/entityspine/domain/`) has ZERO dependencies - uses only Python stdlib. This ensures:
- Portability across projects
- No version conflicts
- Easy to test and maintain

**Principle #3: Tiered Storage Strategy**

Progressive complexity tiers:
- **Tier 0**: JSON files (single-file deployment)
- **Tier 1**: SQLite (embedded database)
- **Tier 2**: DuckDB (analytics-optimized)
- **Tier 3**: PostgreSQL (enterprise scale)

Users choose their tier based on needs, not forced into heavy dependencies.

**Principle #4: Claims-Based Identity**

Identifiers (ticker, CIK, CUSIP) are modeled as **claims** about entities, not rigid properties:
- Same ticker can refer to different companies over time
- Companies can have multiple identifiers
- Confidence scoring for ambiguous cases

**Principle #5: Result[T] Pattern for Error Handling**

All operations return `Result[T]` (Ok/Err) instead of raising exceptions:
- Type-safe error handling
- Forces explicit error handling at call site
- Composable operations (map, flat_map)
- Defined in `domain/workflow.py` - used across ALL Spine projects

### Key Concepts

1. **Entity Resolution** - Map any identifier (CIK, ticker, CUSIP, ISIN, name) to canonical entity
2. **Knowledge Graph** - Model relationships between entities (subsidiary_of, acquired_by, etc.)
3. **Identifier Claims** - Identifiers as probabilistic claims with confidence scores
4. **Sighting History** - Track when/where an identifier was observed
5. **Temporal Queries** - "What was Apple's ticker on this date?"
6. **Result[T] Monad** - Type-safe error handling (Ok/Err) used everywhere
7. **ExecutionContext** - Tracing context for workflow orchestration

### Architecture Decision Records (ADRs)

EntitySpine has **8 ADRs** documenting key decisions:
1. **ADR-001**: Stdlib-Only Domain (no dependencies in core)
2. **ADR-002**: ULID Primary Keys (time-sortable IDs)
3. **ADR-003**: Identifier Claims (probabilistic identity)
4. **ADR-004**: Frozen Dataclasses (immutability)
5. **ADR-005**: String Enums (type-safe constants)
6. **ADR-006**: Time Semantics (week-ending dates)
7. **ADR-007**: Pydantic Wrappers (optional validation)
8. **ADR-008**: Resolution Pipeline (how resolution works)

---

## 🎯 CLASSES TO ANNOTATE

### **Tier 1 (MUST Annotate - 15 classes)**

These classes embody core EntitySpine principles and should have FULL extended docstrings.

#### Core Primitives (`domain/workflow.py`) - **HIGHEST PRIORITY**

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Ok` | `domain/workflow.py` | **10** | Success variant of Result[T] monad - used EVERYWHERE |
| `Err` | `domain/workflow.py` | **10** | Error variant of Result[T] monad - used EVERYWHERE |
| `ExecutionContext` | `domain/workflow.py` | **10** | Tracing context for all workflows |

#### Domain Layer (`domain/`) - Core Models

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Entity` | `domain/entity.py` | **10** | Core domain model, Entity ≠ Security principle |
| `Security` | `domain/security.py` | **10** | Second level of hierarchy |
| `Listing` | `domain/listing.py` | **10** | Third level (where securities trade) |
| `IdentifierClaim` | `domain/claim.py` | **10** | Claims-based identity system |
| `Relationship` | `domain/graph.py` | 9 | Knowledge graph relationships |
| `Observation` | `domain/observation.py` | 9 | Financial metrics (EPS, revenue) |

#### Services Layer (`services/`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `EntityResolver` | `services/resolver.py` | **10** | THE core service - resolves identifiers |
| `GraphService` | `services/graph_service.py` | 9 | Knowledge graph queries |
| `FuzzyMatcher` | `services/fuzzy.py` | 8 | Name matching with confidence |

#### Store Layer (`stores/`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `JsonEntityStore` | `stores/json/json_store.py` | 9 | Tier 0 storage (zero deps) |
| `SqliteStore` | `stores/sqlite/storage.py` | 9 | Tier 1 storage (embedded) |

---

### **Tier 2 (SHOULD Annotate - 25 classes)**

Important supporting classes. Annotate with MOST sections (can skip Context/ADR if not applicable).

#### Domain Enums (`domain/enums/`)
- `EntityType`, `EntityStatus` - Entity classification
- `SecurityType`, `SecurityStatus` - Security classification
- `ListingStatus` - Listing lifecycle
- `IdentifierScheme` - Identifier types (CIK, CUSIP, ISIN, ticker, etc.)
- `MetricCode`, `MetricCategory` - Observation metrics
- `EventType` - Corporate events

#### Graph Models (`domain/graph.py`)
- `NodeKind`, `NodeRef` - Graph node types
- `PersonRole`, `FilingParticipant` - People in filings
- `OwnershipPosition`, `InsiderTransaction` - Ownership data
- `EntityRelationship`, `EntityCluster` - Relationship modeling

#### Domain Support
- `ResolutionCandidate` - Candidate matches during resolution
- `Provenance` - Data lineage tracking
- `MetricSpec`, `FiscalPeriod` - Observation metadata
- `WeekEnding` - Time semantics

#### Services
- `TimelineService` - Entity history over time
- `AuditManager` - Change tracking
- `ClusteringService` - Duplicate detection
- `ConflictResolver` - Merge conflicts
- `DataQualityScorer` - Data quality metrics

#### Adapters & Stores
- `FeedSpineAdapter` - Integration with FeedSpine
- `EntityStoreProtocol` - Storage contract (Protocol class)
- `ElasticsearchStore` - Search backend
- `Neo4jStore` - Graph storage  
- `SqlModelStore` - ORM-based storage (Tier 3)
- `ParquetEntityStore` - Analytics storage

#### Loaders (`loaders/`)
- `SecDataLoader` - Load SEC company tickers
- `FactSetLoader` - Load FactSet data
- `BloombergLoader` - Load Bloomberg data
- `ProvenanceAwareSecLoader` - SEC loader with lineage

#### Sources (`sources/`)
- `LEISnapshot` - Legal Entity Identifiers
- `MICSnapshot` - Market Identifier Codes
- `SECTickerSnapshot` - SEC ticker data

---

### **Tier 3 (NICE TO HAVE - 200+ classes)**

Supporting utilities, repositories, parsers, validators.

- All repository classes in `stores/sqlite/repositories/`
- All adapter Pydantic models in `adapters/pydantic/`
- Validation and cleansing utilities in `domain/validators.py`
- Parser classes in `parser/`
- API request/response models in `api/`
- All error classes in `domain/errors.py`

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES
   - Manifesto: Security ≠ Entity ≠ Listing
   - Tags: `core_concept`, `domain_model`, `securities`

4. **`domain/listing.py` → `Listing`**
   - File: `entityspine/src/entityspine/domain/listing.py`
   - Priority: 9
   - Why: Third level of hierarchy (where securities trade)
   - Manifesto: One security, multiple listings
   - Tags: `core_concept`, `domain_model`, `exchanges`

5. **`domain/relationship.py` → `Relationship`**
   - File: `entityspine/src/entityspine/domain/relationship.py`
   - Priority: 8
   - Why: Knowledge graph relationships (subsidiary_of, acquired_by)
   - Architecture: Directed graph, confidence scores
   - Tags: `knowledge_graph`, `relationships`, `graph_model`

#### Services Layer (`src/entityspine/services/`)

6. **`services/resolver.py` → `EntityResolver`**
   - File: `entityspine/src/entityspine/services/resolver.py`
   - Priority: 10
   - Why: THE core service - resolves identifiers to entities
   - Manifesto: Why CIK is stable, tickers are not
   - Architecture: Resolution pipeline, caching strategy
   - Features: Multi-identifier, fuzzy match, historical resolution
   - Performance: <1ms cached, <10ms uncached
   - Guardrails: Do NOT use ticker as primary key
   - ADR: 008-resolution-pipeline-and-claims.md
   - Tags: `core_service`, `resolution`, `caching`

7. **`services/graph.py` → `KnowledgeGraph`**
   - File: `entityspine/src/entityspine/services/graph.py`
   - Priority: 8
   - Why: Graph queries and traversal
   - Architecture: Adjacency list, relationship types
   - Features: Depth-first search, shortest path, subgraph
   - Tags: `knowledge_graph`, `graph_queries`, `traversal`

#### Store Layer (`src/entityspine/stores/`)

8. **`stores/json_store.py` → `JsonEntityStore`**
   - File: `entityspine/src/entityspine/stores/json/json_store.py`
   - Priority: 9
   - Why: Tier 0 storage (zero dependencies)
   - Manifesto: Single-file deployment, no setup
   - Architecture: JSON Lines format, append-only
   - Features: Fast reads, simple writes, human-readable
   - Guardrails: Not for >100K entities, use SQLite instead
   - Tags: `storage`, `tier_0`, `zero_dependency`

9. **`stores/sqlite_store.py` → `SqliteStore`**
   - File: `entityspine/src/entityspine/stores/sqlite/sqlite_store.py`
   - Priority: 9
   - Why: Tier 1 storage (embedded DB)
   - Architecture: Schema migration, indexes, FTS
   - Features: ACID, SQL queries, full-text search
   - Performance: Handles millions of entities
   - Tags: `storage`, `tier_1`, `sqlite`, `embedded`

10. **`loaders/sec_loader.py` → `SECCompanyLoader`**
    - File: `entityspine/src/entityspine/loaders/sec_loader.py`
    - Priority: 8
    - Why: Loads SEC company_tickers.json data
    - Architecture: HTTP fetch, validation, transform
    - Features: Auto-download, incremental updates
    - Tags: `data_loading`, `sec_edgar`, `ingestion`

---

### **Tier 2 (SHOULD Annotate - 15 classes)**

Important classes that support core functionality. Annotate with MOST sections (can skip Context/ADR if not applicable).

#### Domain Models
11. `domain/execution_context.py` → `ExecutionContext`
12. `domain/week_ending.py` → `WeekEnding`
13. `domain/candidate.py` → `ResolutionCandidate`

#### API Layer
14. `api/routes.py` → `EntityAPI`
15. `api/dto.py` → `EntityDTO`

#### Integration
16. `integration/feedspine_adapter.py` → `FeedSpineAdapter`
17. `integration/polygon_adapter.py` → `PolygonAdapter`

#### Stores
18. `stores/duckdb_store.py` → `DuckDBStore` (Tier 2)
19. `stores/sqlmodel_store.py` → `SqlModelStore` (Tier 3)
20. `stores/protocol.py` → `EntityStoreProtocol`

#### Search
21. `search/fuzzy.py` → `FuzzyMatcher`
22. `search/indexer.py` → `SearchIndexer`

#### Parser
23. `parser/company_tickers.py` → `CompanyTickersParser`
24. `parser/xbrl.py` → `XBRLParser`
25. `parser/sec13f.py` → `SEC13FParser`

---

### **Tier 3 (NICE TO HAVE - remaining classes)**

Supporting utilities, helpers, data classes. Can have basic docstrings with just summary + 1-2 key sections.

26-50+: All remaining classes in `utils/`, `models/`, `core/`, etc.

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Result[T] Pattern - CRITICAL

The `Ok`/`Err` classes in `domain/workflow.py` are THE core primitives:

```python
# From domain/workflow.py
@dataclass(frozen=True)
class Ok[T]:
    """Success variant of Result[T] monad."""
    value: T

@dataclass(frozen=True) 
class Err:
    """Error variant of Result[T] monad."""
    error: str
    category: ErrorCategory = ErrorCategory.UNKNOWN

# Type alias
Result = Ok[T] | Err
```

**When annotating any class that returns Result[T]:**
- Explain why Result[T] is used instead of exceptions
- Show how to handle both Ok and Err cases
- Include error categories when relevant

### Manifesto Section - Emphasize These Principles

For EntitySpine classes, ALWAYS include these in Manifesto:

```python
Manifesto:
    Entity ≠ Security ≠ Listing is the foundational principle.
    
    [Explain how THIS class implements this separation]
    
    We use CIK as stable identifier because:
    - Tickers change (FB → META)
    - Companies reorganize (mergers, spinoffs)
    - CIK is assigned once by SEC, never changes
    
    [If applicable: Claims-based identity]
    Identifiers are CLAIMS about entities, not immutable facts.
    The same ticker "AAPL" in 1980 is a different entity than "AAPL" in 2020.
    
    [If applicable: Zero-dependency principle]
    This class has ZERO dependencies (stdlib only) to ensure
    portability and avoid version conflicts.
```

### Architecture Section - Storage Tier

For store classes, include tier information:

```python
Architecture:
    ```
    [ASCII diagram showing data flow]
    ```
    
    Storage Tier: [Tier 0/1/2/3]
    - Tier 0: JSON (zero dependencies)
    - Tier 1: SQLite (embedded)
    - Tier 2: DuckDB (analytics)
    - Tier 3: PostgreSQL (enterprise)
    
    Dependencies: [List dependencies or "None (stdlib only)"]
    Concurrency: [Thread-safe? Async?]
    Persistence: [File, DB, memory]
```

### Features Section - Resolution Capabilities

For resolver/search classes:

```python
Features:
    - Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
    - Fuzzy name matching (Levenshtein distance < 3)
    - Ticker disambiguation (handles ticker reuse)
    - Historical resolution (as_of parameter for time-travel queries)
    - Bulk resolution (batch API for 1000+ identifiers)
    - Caching (LRU cache, configurable size)
```

### Guardrails Section - Common EntitySpine Mistakes

```python
Guardrails:
    - Do NOT use ticker as primary key (tickers change!)
      ✅ Instead: Use CIK as stable entity identifier
    
    - Do NOT assume ticker → entity is 1:1
      ✅ Instead: Use EntityResolver which handles disambiguation
    
    - Do NOT conflate Entity and Security
      ✅ Instead: Entity has multiple securities, query appropriately
    
    - Do NOT skip validation on identifier schemes
      ✅ Instead: Use IdentifierScheme enum for type safety
    
    - ALWAYS provide as_of date for backtesting queries
      (Prevents lookahead bias with restated data)
```

### Tags - Use These EntitySpine-Specific Tags

Required tags by domain:
- **Domain**: `core_concept`, `domain_model`, `immutable`, `frozen_dataclass`
- **Resolution**: `entity_resolution`, `identifier_claims`, `disambiguation`, `fuzzy_matching`
- **Storage**: `tier_0`, `tier_1`, `tier_2`, `tier_3`, `zero_dependency`, `sqlite`, `duckdb`
- **Graph**: `knowledge_graph`, `relationships`, `graph_queries`, `traversal`
- **Data**: `sec_edgar`, `sec_data`, `company_tickers`, `xbrl`, `form_13f`
- **Temporal**: `week_ending`, `time_semantics`, `historical_queries`

### Doc-Types - Where EntitySpine Classes Should Appear

Map classes to documentation:

```python
Doc-Types:
    - MANIFESTO (section: "Core Principles", priority: 10)
      # For classes that embody Entity ≠ Security ≠ Listing
    
    - FEATURES (section: "Resolution", priority: 9)
      # For resolver, search, matching capabilities
    
    - ARCHITECTURE (section: "Data Model", priority: 8)
      # For domain models, storage architecture
    
    - GUARDRAILS (section: "Identity Management", priority: 9)
      # For classes with common pitfalls
    
    - API_REFERENCE (section: "Core APIs", priority: 10)
      # For public API classes
```

### ADR References

Link to relevant ADRs:

```python
ADR:
    - 001-stdlib-only-domain.md: Why no dependencies in domain layer
    - 003-identifier-claims.md: Why we model identifiers as claims
    - 004-frozen-dataclasses.md: Why entities are immutable
    - 008-resolution-pipeline-and-claims.md: How resolution algorithm works
```

---

## 📚 REFERENCE DOCUMENTS

### Must Read Before Annotating

1. **EntitySpine README**: `entityspine/README.md`
   - Understand the "Why" and quick start

2. **ADRs** (if they exist): `entityspine/docs/adrs/`
   - 001-stdlib-only-domain.md
   - 003-identifier-claims.md
   - 008-resolution-pipeline-and-claims.md

3. **Existing Guides** (if available): `entityspine/docs/guides/`
   - CORE_CONCEPTS.md - Entity/Security/Listing separation
   - RESOLUTION_GUIDE.md - How resolution works

### Example Annotated Class (Full Template)

See [EXTENDED_ANNOTATION_PROMPT.md](../EXTENDED_ANNOTATION_PROMPT.md) for the complete extended format, then apply these EntitySpine-specific principles:

```python
from entityspine.domain.base import EntitySpineModel

class Entity(EntitySpineModel):
    """
    Canonical representation of a real-world entity (company, person, fund).
    
    Embodies the Entity ≠ Security ≠ Listing principle: one entity can issue
    multiple securities, each of which can have multiple listings.
    
    Manifesto:
        Entity ≠ Security ≠ Listing is the foundational principle of EntitySpine.
        
        This separation exists because:
        - One entity (Apple Inc.) can issue multiple securities (common stock, bonds, warrants)
        - One security (AAPL common) can trade on multiple exchanges (NASDAQ, BATS, IEX)
        - Conflating these levels leads to incorrect data joins and broken analytics
        
        We use CIK (Central Index Key) as the stable entity identifier because:
        - Tickers change (Facebook → Meta, Google → Alphabet)
        - Companies reorganize (mergers, spinoffs, bankruptcies)
        - CIK is assigned once by SEC and never changes
        - All SEC filers have a CIK
        
        This class is a frozen dataclass (immutable) to ensure entities
        can be safely cached and used as dictionary keys.
    
    Architecture:
        ```
        Entity (CIK-based identity)
            ↓
        IdentifierClaim[] (ticker, CUSIP, name claims)
            ↓
        Security[] (multiple securities per entity)
            ↓
        Listing[] (multiple listings per security)
        ```
        
        Storage: JSON (Tier 0), SQLite (Tier 1), DuckDB (Tier 2), PostgreSQL (Tier 3)
        Immutability: Frozen dataclass (ADR-004)
        Primary Key: ULID (time-sortable, ADR-002)
        Dependencies: None (stdlib only, ADR-001)
    
    Features:
        - Immutable entity representation
        - ULID primary key (time-sortable)
        - CIK as stable identifier
        - Entity type classification (issuer, person, fund, etc.)
        - Metadata storage (industry, SIC code, status)
        - Claims-based identifier resolution
        - Multiple identifier schemes (ticker, CUSIP, ISIN, name)
    
    Examples:
        >>> entity = Entity(
        ...     entity_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        ...     entity_type=EntityType.ISSUER,
        ...     cik="0000320193",
        ...     name="Apple Inc."
        ... )
        >>> entity.cik
        '0000320193'
        
        # Immutable (frozen)
        >>> entity.name = "Changed"
        Traceback (most recent call last):
        dataclasses.FrozenInstanceError: cannot assign to field 'name'
    
    Performance:
        - Construction: <1μs (simple dataclass)
        - Memory: ~200 bytes per entity
        - Hashable: O(1) dictionary lookups
        - Serialization: ~500 bytes JSON
    
    Guardrails:
        - Do NOT use ticker as primary identifier
          ✅ Instead: Use CIK (stored in cik field)
        
        - Do NOT mutate entity after creation
          ✅ Instead: Create new entity with updated fields
        
        - Do NOT assume entity_id is CIK
          ✅ Instead: Use entity.cik for CIK lookups
        
        - ALWAYS validate CIK format (10 digits, zero-padded)
    
    Context:
        Problem: Most financial systems treat ticker as primary key,
        breaking when tickers change or companies reorganize.
        
        Solution: Use CIK as stable identifier, model tickers as
        claims about entities (can change over time).
        
        Alternatives Considered:
        - LEI (Legal Entity Identifier): Not available for all US companies
        - CUSIP: Security-level, not entity-level
        - Ticker: Too unstable (changes frequently)
        
        Why CIK: Assigned once by SEC, never changes, covers all filers,
        publicly available, required for EDGAR submissions.
    
    ADR:
        - 001-stdlib-only-domain.md: Why no dependencies
        - 002-ulid-primary-keys.md: Why ULID for IDs
        - 003-identifier-claims.md: Claims-based identity
        - 004-frozen-dataclasses.md: Immutability rationale
    
    Changelog:
        - v0.3.0: Added entity_type enum
        - v0.4.0: Implemented frozen dataclass (BREAKING)
        - v0.5.0: Added ULID primary keys
    
    Unified-Data-Model:
        Target: architecture/UNIFIED_DATA_MODEL.md
        Section: "Core Domain Models"
        Diagram: entity-security-listing-hierarchy
        Schema-DDL: True
    
    Tags:
        - core_concept
        - domain_model
        - entity_resolution
        - immutable
        - frozen_dataclass
        - sec_data
    
    Doc-Types:
        - MANIFESTO (section: "Core Principles", priority: 10)
        - FEATURES (section: "Domain Models", priority: 9)
        - ARCHITECTURE (section: "Data Model", priority: 10)
        - GUARDRAILS (section: "Entity Management", priority: 9)
        - API_REFERENCE (section: "Core APIs", priority: 10)
    """
    ...
```

---

## ✅ VALIDATION CHECKLIST

Before submitting annotated EntitySpine classes:

### Content Requirements
- [ ] Manifesto explains Entity ≠ Security ≠ Listing (if applicable)
- [ ] Manifesto mentions CIK as stable identifier (if applicable)
- [ ] Architecture includes storage tier information
- [ ] Architecture notes dependencies (or "stdlib only")
- [ ] Features list is complete and accurate
- [ ] Examples use doctest format (`>>>`)
- [ ] Guardrails warn about ticker-as-primary-key
- [ ] Tags include EntitySpine-specific tags
- [ ] ADR references included (if applicable)

### EntitySpine-Specific
- [ ] Uses correct terminology (Entity vs Security vs Listing)
- [ ] References relevant ADRs
- [ ] Includes tier information for storage classes
- [ ] Mentions claims-based identity for resolvers
- [ ] Performance metrics for core services

### Quality
- [ ] At least 3 tags
- [ ] At least 2 doc-types
- [ ] Examples are runnable
- [ ] No TODO or placeholder text

---

## 🚀 QUICK START

1. **Read this entire guide** (10 minutes)
2. **Read EXTENDED_ANNOTATION_PROMPT.md** (15 minutes)
3. **Pick ONE Tier 1 class** from the list above
4. **Read the existing code** and any related docs
5. **Annotate using full extended format**
6. **Validate**: `docbuilder validate <file>`
7. **Submit for review** before batch-annotating others

---

**Ready? Start with `Entity` class - it's the foundation of EntitySpine!**
