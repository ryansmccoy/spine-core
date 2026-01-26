# Code Annotation Prompt: Migrate Existing Code to Self-Documenting Format

**For:** Migrating existing Python classes to use structured docstrings for auto-documentation generation

**Context:** Part of the Documentation Automation system in Spine Core

---

## Objective

Systematically annotate existing Python code across the Spine ecosystem with structured docstrings that can be parsed to auto-generate MANIFESTO.md, FEATURES.md, and API documentation.

---

## Docstring Format Standard

### Structured Sections

```python
class YourClass:
    """
    [Brief one-line description]
    
    [Optional: Longer description paragraph]
    
    Manifesto:
        [Core principles this class embodies]
        [Why this approach matters]
        [What problem it solves]
    
    Architecture:
        [ASCII diagram or structural description]
        [Key relationships with other components]
        [Data flow]
    
    Features:
        - [Feature 1: description]
        - [Feature 2: description]
        - [Feature 3: description]
    
    Examples:
        >>> [Executable code example]
        >>> [Show common use cases]
    
    Storage:
        [If applicable: Storage tier, schema, persistence details]
    
    Performance:
        [If applicable: Time/space complexity, benchmarks, scaling]
    
    Guardrails:
        [If applicable: What NOT to do, constraints, limitations]
    """
```

### Method Docstrings

```python
def your_method(self, param: Type) -> ReturnType:
    """
    [Brief description]
    
    [Optional: Detailed explanation]
    
    Args:
        param: Description of parameter
    
    Returns:
        Description of return value
    
    Raises:
        ExceptionType: When this exception occurs
    
    Examples:
        >>> obj.your_method("value")
        ExpectedOutput(...)
    
    Performance:
        O(n) time, O(1) space
    
    Notes:
        - Important consideration 1
        - Important consideration 2
    """
```

---

## Mapping: Code → Documentation

| Docstring Section | Generates Into | Purpose |
|------------------|----------------|---------|
| **Manifesto:** | MANIFESTO.md | Core principles, philosophy, design rationale |
| **Architecture:** | MANIFESTO.md (Architecture section) | System design, relationships, data flow |
| **Features:** | FEATURES.md | Capabilities, what the component can do |
| **Examples:** | Both FEATURES.md and API docs | Usage examples, common patterns |
| **Storage:** | FEATURES.md (Storage section) | Persistence details, data model |
| **Performance:** | FEATURES.md (Performance section) | Benchmarks, complexity, scaling |
| **Guardrails:** | GUARDRAILS.md | Constraints, anti-patterns, what NOT to do |

---

## Migration Strategy

### Step 1: Identify Core Classes (Week 1)

For each project, identify the 5-10 most important classes that embody the project's core principles:

**EntitySpine:**
- `EntityResolver` - Core resolution logic
- `EntityStore` - Storage abstraction
- `EntityGraph` - Knowledge graph
- `CIKRegistry` - CIK lookups
- `TickerResolver` - Ticker resolution

**FeedSpine:**
- `FeedAdapter` - Base adapter interface
- `SECFeedAdapter` - SEC EDGAR feed
- `FeedOrchestrator` - Feed management
- `FeedStore` - Feed persistence
- `FeedScheduler` - Scheduling logic

**GenAI-Spine:**
- `LLMClient` - LLM interface
- `PromptManager` - Prompt templates
- `ResponseParser` - Response processing
- `EmbeddingService` - Vector embeddings
- `RAGEngine` - Retrieval-augmented generation

### Step 2: Annotate Core Classes (Weeks 2-4)

For each core class:

1. **Read existing code and any related documentation**
2. **Extract manifesto principles** - Why was this designed this way?
3. **Document architecture** - How does it fit into the system?
4. **List features** - What can it do?
5. **Add examples** - Show common usage
6. **Note guardrails** - What are the constraints?

### Step 3: Validate Extraction (Week 5)

Run the parser (when built) to verify:

```bash
docbuilder extract src/core_class.py --format json
# Should output structured sections
```

Manually verify output matches intent.

### Step 4: Expand to All Classes (Weeks 6-8)

- Annotate remaining classes (less detail than core classes)
- Focus on:
  - Brief description
  - Key features
  - Common examples

### Step 5: Generate & Review (Week 9)

```bash
docbuilder build
# Generates MANIFESTO.md, FEATURES.md, GUARDRAILS.md
```

**Review checklist:**
- [ ] MANIFESTO.md clearly explains project philosophy
- [ ] FEATURES.md comprehensively lists capabilities
- [ ] GUARDRAILS.md warns about anti-patterns
- [ ] No duplicate content across docs
- [ ] All major classes represented

---

## Annotation Examples

### Example 1: EntityResolver (Core Class)

```python
class EntityResolver:
    """
    Resolve any identifier (CIK, ticker, name, CUSIP, ISIN) to a canonical entity.
    
    This is the central component of EntitySpine, embodying the core principle:
    Entity ≠ Security ≠ Listing
    
    Manifesto:
        The Entity → Security → Listing hierarchy is fundamental to financial data.
        
        Why this matters:
        - One entity (Apple Inc.) can issue multiple securities (common stock, bonds, warrants)
        - One security (AAPL common stock) can have multiple listings (NASDAQ, BATS, IEX)
        - Conflating these leads to incorrect data joins and broken analytics
        
        EntitySpine maintains strict separation to ensure data integrity.
        
        Historical context: Most financial data systems treat "ticker" as primary key,
        causing breakage when companies change tickers, securities relist, or entities
        reorganize. We use CIK (Central Index Key) as the stable entity identifier.
    
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
        │  5. ISIN → CIK          │
        └───────────┬─────────────┘
                    ↓
              Canonical Entity
              (with CIK, name, metadata)
        ```
        
        Storage: CIK → Entity map in SQLite (Tier 1) or DuckDB (Tier 2)
        Caching: In-memory LRU cache (10K entities)
        Fallback: SEC EDGAR API for missing entities
    
    Features:
        - Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
        - Fuzzy name matching (Levenshtein distance < 3)
        - Ticker disambiguation (multiple companies with same ticker)
        - Historical ticker resolution (AAPL in 1990 ≠ AAPL in 2020)
        - Bulk resolution (batch API for 1000+ identifiers)
        - Entity metadata (industry, SIC code, filing status)
    
    Examples:
        >>> resolver = EntityResolver()
        
        # Resolve by ticker
        >>> entity = resolver.resolve("AAPL")
        >>> entity.cik
        '0000320193'
        >>> entity.name
        'Apple Inc.'
        
        # Resolve by CIK
        >>> entity = resolver.resolve("0000320193")
        >>> entity.name
        'Apple Inc.'
        
        # Resolve by name (fuzzy)
        >>> entity = resolver.resolve("apple incorporated")
        >>> entity.cik
        '0000320193'
        
        # Bulk resolution
        >>> entities = resolver.resolve_many(["AAPL", "MSFT", "GOOG"])
        >>> len(entities)
        3
    
    Performance:
        - Single lookup: <1ms (cached), <10ms (uncached)
        - Bulk resolution: ~50 identifiers/second
        - Memory: ~50MB for 10K cached entities
        - Storage: ~500MB for full SEC entity universe
    
    Guardrails:
        - Do NOT use ticker as a primary key (tickers change!)
        - Do NOT assume one-to-one ticker → entity (disambiguation needed)
        - Do NOT skip validation (always check resolve() returns non-None)
        - Do NOT mix entity and security identifiers (use separate resolvers)
    
    Storage:
        Tier 1 (SQLite):
            entities table: (cik PRIMARY KEY, name, sic_code, ...)
            ticker_map table: (ticker, cik, start_date, end_date)
            cusip_map table: (cusip, cik)
        
        Tier 2 (DuckDB):
            Same schema + analytics views (entity_counts, ticker_changes)
    """
    
    def resolve(self, identifier: str, as_of: date | None = None) -> Entity | None:
        """
        Resolve identifier to canonical entity.
        
        Args:
            identifier: CIK (with or without leading zeros), ticker, CUSIP, ISIN, or company name
            as_of: Optional date for historical ticker resolution (default: today)
        
        Returns:
            Entity object if found, None otherwise
        
        Raises:
            ValueError: If identifier format is invalid
            AmbiguousIdentifierError: If multiple entities match (caller must disambiguate)
        
        Examples:
            >>> resolver.resolve("AAPL")
            Entity(cik='0000320193', name='Apple Inc.')
            
            >>> resolver.resolve("apple inc")
            Entity(cik='0000320193', name='Apple Inc.')
            
            >>> resolver.resolve("missing-ticker")
            None
        
        Performance:
            O(1) for CIK direct lookup
            O(log n) for ticker/CUSIP lookup (indexed)
            O(n) for name fuzzy matching (can be slow for large datasets)
        
        Notes:
            - CIK is always returned with leading zeros removed (internal format)
            - Historical ticker resolution requires as_of date
            - Fuzzy name matching uses Levenshtein distance threshold of 3
        """
        ...
```

### Example 2: FeedAdapter (Interface/ABC)

```python
class FeedAdapter(ABC):
    """
    Base interface for all feed adapters in FeedSpine.
    
    Defines the contract that all feed implementations must follow, enabling
    polymorphic feed orchestration and consistent error handling.
    
    Manifesto:
        Feed adapters should be dumb pipes, not smart processors.
        
        Philosophy:
        - Adapter fetches raw data (HTTP, S3, filesystem)
        - Adapter validates structure (schema, format)
        - Adapter does NOT transform or enrich data
        - Transformation happens in downstream processing
        
        Why: Separation of concerns allows feed logic to evolve independently
        from business logic. An adapter should be replaceable without changing
        downstream code.
    
    Architecture:
        ```
        FeedAdapter (ABC)
              ↓
        ┌─────────────────────────┐
        │  fetch() → raw data     │
        │  validate() → check     │
        │  parse() → structured   │
        └────────┬────────────────┘
                 ↓
           [Concrete implementations]
           - SECFeedAdapter
           - USGPOFeedAdapter  
           - FRSFeedAdapter
        ```
    
    Features:
        - Polymorphic feed interface (swap implementations)
        - Built-in retry logic (exponential backoff)
        - Rate limiting (configurable per-feed)
        - Error categorization (transient vs permanent)
        - Progress tracking (for large feeds)
    
    Examples:
        >>> # Implement custom feed
        >>> class CustomFeedAdapter(FeedAdapter):
        ...     def fetch(self) -> bytes:
        ...         return requests.get(self.url).content
        ...     
        ...     def parse(self, raw: bytes) -> list[dict]:
        ...         return json.loads(raw)
        
        >>> adapter = CustomFeedAdapter(url="https://example.com/feed")
        >>> items = adapter.fetch_and_parse()
    
    Guardrails:
        - Do NOT add business logic to adapters (keep them dumb)
        - Do NOT cache in adapters (caching is orchestrator's job)
        - Do NOT handle credentials in adapter (use credential provider)
        - Do implement retry logic (network is unreliable)
    """
    
    @abstractmethod
    def fetch(self) -> bytes:
        """
        Fetch raw feed data.
        
        Returns:
            Raw bytes (could be XML, JSON, CSV, etc.)
        
        Raises:
            FeedUnavailableError: If feed is temporarily down (retry)
            FeedNotFoundError: If feed URL is invalid (permanent)
            RateLimitExceededError: If rate limit hit (backoff)
        
        Notes:
            - Implementations should include retry logic
            - Should respect rate limits
            - Should timeout after reasonable duration (default: 30s)
        """
        ...
```

### Example 3: Utility Class (Minimal Annotation)

```python
class DateUtils:
    """
    Date parsing and formatting utilities.
    
    Features:
        - Parse SEC date formats (YYYYMMDD, YYYY-MM-DD)
        - Convert to/from various formats
        - Fiscal year calculations
        - Business day arithmetic
    
    Examples:
        >>> DateUtils.parse_sec_date("20240101")
        date(2024, 1, 1)
        
        >>> DateUtils.fiscal_year_end(date(2024, 6, 30), fiscal_year_end=12)
        date(2024, 12, 31)
    """
    
    @staticmethod
    def parse_sec_date(date_str: str) -> date:
        """
        Parse SEC date format (YYYYMMDD or YYYY-MM-DD).
        
        Args:
            date_str: Date string in SEC format
        
        Returns:
            Python date object
        
        Raises:
            ValueError: If date_str is invalid format
        
        Examples:
            >>> DateUtils.parse_sec_date("20240101")
            date(2024, 1, 1)
        """
        ...
```

---

## Project-Specific Annotation Guides

### EntitySpine Classes to Prioritize

1. **EntityResolver** - Core resolution logic → MANIFESTO (Entity ≠ Security ≠ Listing)
2. **EntityStore** - Storage abstraction → MANIFESTO (Progressive storage tiers)
3. **EntityGraph** - Knowledge graph → FEATURES (Graph queries)
4. **CIKRegistry** - CIK lookups → FEATURES (Identifier resolution)
5. **SQLiteStore** - Tier 1 storage → FEATURES (Storage tiers)

### FeedSpine Classes to Prioritize

1. **FeedAdapter** - Base adapter → MANIFESTO (Dumb pipes philosophy)
2. **SECFeedAdapter** - SEC feed → FEATURES (SEC integration)
3. **FeedOrchestrator** - Orchestration → ARCHITECTURE (Feed scheduling)
4. **FeedStore** - Persistence → FEATURES (Storage)
5. **FeedScheduler** - Scheduling → FEATURES (Automation)

### GenAI-Spine Classes to Prioritize

1. **LLMClient** - LLM interface → MANIFESTO (LLM as tool, not oracle)
2. **PromptManager** - Prompt templates → FEATURES (Prompt engineering)
3. **RAGEngine** - RAG → FEATURES (Knowledge retrieval)
4. **EmbeddingService** - Embeddings → FEATURES (Vector search)
5. **ResponseParser** - Parsing → GUARDRAILS (LLM output validation)

---

## Validation Checklist

After annotating a class, verify:

- [ ] **Manifesto section**: Does this explain *why* the design choice matters?
- [ ] **Architecture section**: Can a new developer understand how this fits in?
- [ ] **Features section**: Are all major capabilities listed?
- [ ] **Examples section**: Can someone copy-paste and run these?
- [ ] **Guardrails section**: Are anti-patterns and constraints clear?
- [ ] **Brief description**: Is the one-liner accurate and concise?
- [ ] **Method docstrings**: Do all public methods have examples?

---

## Next Steps

1. **Choose a pilot project** (entityspine or feedspine)
2. **Identify 5 core classes**
3. **Annotate them using this format**
4. **Run parser (when available) to extract**
5. **Review generated documentation**
6. **Iterate on format if needed**
7. **Expand to remaining classes**
8. **Repeat for other projects**

---

## Related Documentation

- [../design/SELF_DOCUMENTING_CODE.md](../design/SELF_DOCUMENTING_CODE.md) - Feature overview
- [../README.md](../README.md) - Package overview
- [LLM_DECISION_PROMPT.md](LLM_DECISION_PROMPT.md) - Implementation approach decision

---

*Good documentation starts with good code. Self-documenting code starts with structured annotations.*
