# 📋 COPY-PASTE PROMPT: Annotate EntitySpine Classes

**Copy everything below and send to an LLM with file editing access:**

---

## TASK: Add Extended Docstrings to EntitySpine Classes

You are a documentation automation agent. Add rich extended docstrings to Python classes in the EntitySpine project.

### Project Context

**EntitySpine** is a zero-dependency entity resolution system for SEC EDGAR data.

**The Project Origin (Why It Exists):**
The project started because SEC EDGAR uses **CIK numbers** to identify filers, but traders/analysts need **ticker symbols**. The fundamental problem: "Given a CIK, what's the ticker? Given a ticker, what's the CIK?" This seemingly simple question is surprisingly hard because:
- Companies change tickers (FB → META)
- Tickers are reused (TWC: Time Warner Cable 2009-2016, then Tahoe Resources)
- Multiple securities per company (GOOGL, GOOG are both Alphabet)
- Tickers are exchange-specific (same company, different symbols on different exchanges)

**Core Principles (use in Manifesto sections):**
1. **Entity ≠ Security ≠ Listing** - One entity issues securities, securities have listings
2. **Claims-based identity** - Identifiers are probabilistic claims with confidence scores  
3. **Result[T] pattern** - All operations return Ok(value) or Err(error), no exceptions
4. **Stdlib-only domain** - Zero external dependencies in domain/ layer
5. **Tiered storage** - T0 (JSON) → T1 (SQLite) → T2 (DuckDB) → T3 (PostgreSQL)

### Extended Docstring Format

```python
class ClassName:
    """
    One-line summary.
    
    Extended description (2-3 sentences).
    
    Manifesto:
        Why this class exists. Reference principles above.
        Explain design decisions.
    
    Architecture:
        ```
        ASCII diagram
        ```
        Dependencies: X, Y, Z (or "None - stdlib only")
        Storage Tier: T0/T1/T2/T3 (if applicable)
    
    Features:
        - Feature 1
        - Feature 2
    
    Examples:
        >>> instance = ClassName()
        >>> instance.method()
        'result'
    
    Performance:
        - Operation: O(n), ~Xms
    
    Guardrails:
        - Do NOT use ticker as primary key
          ✅ Instead: Use CIK
    
    Context:
        Problem: What problem this solves
        Solution: How it solves it
    
    Tags:
        - entity_resolution
        - domain_model
    
    Doc-Types:
        - MANIFESTO (section: "Core Principles", priority: 10)
        - FEATURES (section: "Domain Models", priority: 9)
    """
```

### Files to Annotate (Feature-Based + Chronological Order)

**Selection methodology**: Organized by feature importance, following the project's evolution. Start with the core problem (CIK→ticker resolution) and work outward.

---

## 🔴 PHASE 1: THE ORIGINAL PROBLEM - CIK ↔ Ticker Resolution (Do First)

*These files solve the original problem: "What ticker is CIK 0000320193?"*

| Order | File | Classes | Why First |
|-------|------|---------|-----------|
| 1 | `sources/sec.py` | SECTickerSnapshot, SECTickerSource | **THE DATA SOURCE** - fetches SEC company_tickers.json (CIK + ticker + name) |
| 2 | `services/lookup.py` | Lookup | **THE API** - `lu.ticker("0000320193")` → "AAPL" - this is what users actually call |
| 3 | `services/resolver.py` | EntityResolver, ResolverConfig | **THE ENGINE** - multi-tier resolution with confidence scoring |
| 4 | `stores/json_store.py` | JsonEntityStore | **TIER 0 STORAGE** - zero-dep JSON persistence (part of initial commit) |

---

## 🟠 PHASE 2: THE DATA MODEL - Entity ≠ Security ≠ Listing (Initial Commit Files)

*The core insight that makes EntitySpine different from simple CIK→ticker mappings*

| Order | File | Class | Why This Order |
|-------|------|-------|----------------|
| 5 | `domain/entity.py` | Entity | **THE ANCHOR** - "Apple Inc." - legal identity (NO identifiers!) |
| 6 | `domain/security.py` | Security | **THE INSTRUMENT** - "AAPL Common Stock" - what you trade |
| 7 | `domain/listing.py` | Listing | **WHERE TICKER LIVES** - "NASDAQ:AAPL" - ticker is here, not on Entity |
| 8 | `domain/claim.py` | IdentifierClaim | **THE CROSSWALK** - "SEC says CIK 320193 = Apple" with confidence |
| 9 | `domain/candidate.py` | ResolutionCandidate | Match candidates with scores |
| 10 | `domain/resolution.py` | ResolutionResult | Resolution outcomes |

---

## 🟡 PHASE 3: ENTITY RELATIONSHIPS - Companies & Subsidiaries

*Added later: relationships between entities (parent/subsidiary, mergers, ownership)*

| Order | File | Classes (count) | Feature |
|-------|------|-----------------|---------|
| 11 | `domain/graph.py` | EntityNetwork, EntityCluster, Relationship, etc (25) | **THE KNOWLEDGE GRAPH** - company relationships, insider transactions |
| 12 | `services/graph_service.py` | GraphService | Build and query relationship graphs |
| 13 | `parser/exhibit21.py` | Exhibit21Parser, SubsidiaryExtractor | Extract subsidiaries from SEC filings |
| 14 | `domain/clustering.py` | ClusterResult, SimilarityScore | Group related entities |
| 15 | `services/clustering.py` | ClusteringService | Clustering algorithms |

---

## 🟢 PHASE 4: MULTI-VENDOR SYMBOLOGY - FactSet, Bloomberg, Refinitiv

*The reason EntitySpine uses "claims": different vendors disagree*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 16 | `core/identifier.py` | IdentifierParser, ChecksumValidator | Parse/validate CUSIP, ISIN, SEDOL |
| 17 | `sources/gleif.py` | GLEIFSource, LEIRegistry (11) | LEI lookups (GLEIF API) |
| 18 | `loaders/factset.py` | FactSetLoader | FactSet security master |
| 19 | `loaders/bloomberg.py` | BloombergLoader | Bloomberg terminal data |
| 20 | `services/symbology_refresh.py` | SymbologyRefreshService | Keep identifiers current |

---

## 🔵 PHASE 5: STORAGE TIERS - T0 → T1 → T2 → T3

*Scaling from JSON files to PostgreSQL*

| Order | File | Classes | Storage Tier |
|-------|------|---------|--------------|
| 21 | `stores/sqlite_store.py` | SqliteStore | T1: SQLite (most common) |
| 22 | `stores/sqlite/storage.py` | SqliteStore (modular) | T1: Refactored SQLite |
| 23 | `stores/audit_stores.py` | ProvenanceStore, MergeEventStore (6) | Audit trail |
| 24 | `stores/mappers.py` | EntityMapper, SecurityMapper | ORM layer |
| 25 | `stores/elasticsearch_store.py` | ElasticsearchStore | T4: Full-text search |
| 26 | `stores/neo4j_store.py` | Neo4jStore | T5: Graph database |

---

## 🟣 PHASE 6: MARKET INFRASTRUCTURE - Exchanges, MICs, Reference Data

*Added later: ISO standards, exchange metadata*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 27 | `domain/markets.py` | Exchange, BrokerDealer, etc (11) | Market participants |
| 28 | `sources/iso10383.py` | MICSnapshot, MICRegistry | ISO MIC codes (exchanges) |
| 29 | `sources/iso3166.py` | CountryRegistry | Country codes |
| 30 | `sources/iso4217.py` | CurrencyRegistry | Currency codes |
| 31 | `domain/reference_data/venues.py` | TradingVenue, VenueRegistry | Trading venues |

---

## ⚪ PHASE 7: SUPPORTING INFRASTRUCTURE

*Quality, workflow, observations, errors*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 32 | `domain/workflow.py` | Ok, Err, ExecutionContext (14) | Result[T] pattern |
| 33 | `domain/errors.py` | ErrorCategory, ErrorRecord | Error handling |
| 34 | `domain/observation.py` | Observation, MetricSpec (8) | Time-series observations |
| 35 | `services/data_quality.py` | DataQualityScorer | Data validation |
| 36 | `services/audit.py` | AuditService | Audit logging |

---

### Workflow

**Work in PHASES, not random files:**
1. Complete Phase 1 entirely (4 files) - this is the core problem
2. Complete Phase 2 entirely (6 files) - the data model
3. Then proceed to Phase 3, 4, etc.

For each file:
1. Read the entire source file
2. Add extended docstrings to **all public classes**
3. Ensure Manifesto references the feature's purpose in EntitySpine's evolution

### Quality Checklist (per phase)
- [ ] All classes in the phase are annotated
- [ ] Manifesto explains why this feature was added
- [ ] Architecture diagrams show relationships to earlier phases
- [ ] Examples demonstrate the feature's use case

### Start Now

**Begin with Phase 1, File 1: `sources/sec.py`** - the SEC data source that started it all. This file fetches `company_tickers_exchange.json` and creates the CIK→ticker→name mappings.

---

**When done with each phase, report progress before continuing.**
