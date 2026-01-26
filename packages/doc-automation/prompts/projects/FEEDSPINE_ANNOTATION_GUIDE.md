# 📊 FeedSpine - Annotation Guide

**Project-Specific Guide for Annotating FeedSpine Classes**

*For use with Documentation Automation Package - February 2026*

---

## 📋 PROJECT CONTEXT

### What is FeedSpine?

**FeedSpine** is a storage-agnostic, executor-agnostic feed capture framework that handles:

> *"I need to collect data from 10 different feeds, deduplicate across them, track when we first saw each record, and organize into raw/clean/curated tiers"*

### Core Philosophy

**Principle #1: Medallion Architecture (Bronze → Silver → Gold)**

Data flows through quality tiers:
- **Bronze**: Raw data exactly as received (preserve provenance)
- **Silver**: Validated and normalized (clean, typed)
- **Gold**: Curated for analytics (denormalized, aggregated)

Each tier serves a purpose - don't skip bronze!

**Principle #2: Data Archetypes Matter**

Not all data is the same. FeedSpine recognizes **5 data archetypes**:
1. **Observations** - Measured facts over time (EPS, revenue, metrics)
2. **Events** - Things that happen (earnings calls, filings)
3. **Entities** - Master data (companies, people, securities)
4. **Documents** - Content blobs (PDFs, HTML, XBRL)
5. **Prices** - High-frequency time-series (tick data)

Each archetype needs different storage/indexing/querying.

**Principle #3: Deduplication by Natural Key**

Records are deduplicated by **natural key** (domain-specific identifier), not arbitrary IDs:
- Same SEC filing appears in RSS feed (5 min), daily index (next day), quarterly index (quarterly)
- FeedSpine stores it ONCE, tracks all sightings
- Natural key might be: `(accession_number)` or `(entity_id, period, metric)` or `(ticker, date, field)`

**Principle #4: Storage Agnostic**

Users choose their storage backend:
- **Memory** - Testing, ephemeral
- **SQLite** - Embedded, single-file
- **DuckDB** - Analytics-optimized
- **PostgreSQL** - Enterprise scale
- **Custom** - Implement `StorageProtocol`

Code doesn't change when you swap backends.

**Principle #5: Sighting History**

Track when/where each record was observed:
- First seen: 2024-01-30 09:15:00 (RSS feed)
- Also seen: 2024-01-31 08:00:00 (daily index)
- Also seen: 2024-04-01 (quarterly index)

Critical for data lineage and debugging.

### Key Concepts

1. **Feed Adapter** - Interface to external data source (SEC EDGAR, FactSet, Bloomberg, RSS)
2. **Natural Key** - Domain-specific unique identifier (not database PK)
3. **Sighting** - Observation of a record at a specific time from a specific source
4. **Medallion Tiers** - Bronze (raw) → Silver (clean) → Gold (curated)
5. **Data Archetypes** - Observations, Events, Entities, Documents, Prices
6. **Storage Backend** - Pluggable storage (Memory, SQLite, DuckDB, PostgreSQL)

### Architecture Patterns

1. **Adapter Pattern** - `FeedAdapter` abstraction for any data source
2. **Strategy Pattern** - Pluggable storage backends
3. **Template Method** - Base adapter with hooks for customization
4. **Observer Pattern** - Metrics and notifications on feed events

---

## 🎯 CLASSES TO ANNOTATE

### **Tier 1 (MUST Annotate - 15 classes)**

These classes embody core FeedSpine principles and should have FULL extended docstrings.

#### Core Pipeline (`pipeline.py`, `core/`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Pipeline` | `pipeline.py` | **10** | Orchestrates feed → storage flow |
| `ProcessResult` | `pipeline.py` | **10** | Pipeline execution result |
| `PipelineStats` | `pipeline.py` | 9 | Pipeline metrics |
| `FeedSpine` | `core/feedspine.py` | **10** | Main entry point |
| `CollectionResult` | `core/feedspine.py` | 9 | Collection results |

#### Adapter Layer (`adapter/`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `FeedAdapter` | `adapter/base.py` | **10** | Protocol - ALL adapters implement this |
| `BaseFeedAdapter` | `adapter/base.py` | **10** | Template method base class |
| `RSSFeedAdapter` | `adapter/rss.py` | 9 | Common feed type (SEC RSS, news) |
| `JSONFeedAdapter` | `adapter/json.py` | 9 | JSON API feeds |
| `FileFeedAdapter` | `adapter/file.py` | 8 | File-based feeds |

#### Storage Layer (`storage/`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `StorageBackend` | `protocols/storage.py` | **10** | Storage contract protocol |
| `MemoryStorage` | `storage/memory.py` | 9 | Testing, ephemeral |
| `SQLiteStorage` | `storage/sqlite.py` | 9 | Embedded database |
| `DuckDBStorage` | `storage/duckdb.py` | 8 | Analytics-optimized |
| `PostgresStorage` | `storage/postgres.py` | 8 | Enterprise scale |

---

### **Tier 2 (SHOULD Annotate - 25 classes)**

Important supporting classes. Annotate with MOST sections.

#### 🔴 Composition Operators (`composition/`) - **KEY ARCHITECTURE**

The composition layer enables fluent pipeline construction:

| Class | File | Why |
|-------|------|-----|
| `FeedConfig` | `composition/config.py` | Feed configuration |
| `Feed` | `composition/feed.py` | Composable feed wrapper |
| `PipelineOp` | `composition/ops.py` | Base pipeline operator |
| `FilterOp` | `composition/ops.py` | Filter records |
| `EnrichOp` | `composition/ops.py` | Add data to records |
| `TransformOp` | `composition/ops.py` | Transform records |
| `DedupeOp` | `composition/ops.py` | Deduplication operator |
| `NotifyOp` | `composition/ops.py` | Notification operator |
| `RateLimitOp` | `composition/ops.py` | Rate limiting |
| `CheckpointOp` | `composition/ops.py` | Checkpoint operator |
| `BatchOp` | `composition/ops.py` | Batch processing |
| `Preset`, `MinimalPreset` | `composition/preset.py` | Pipeline presets |

#### Protocols (`protocols/`)
- `Enricher` - Enrich records
- `BatchEnricher` - Batch enrichment
- `Executor` - Run pipelines
- `Scheduler` - Schedule runs
- `SearchBackend` - Search interface
- `MessageQueue` - Queue interface
- `ProgressReporter` - Progress tracking
- `Notifier` - Notification interface

#### 🔴 Earnings Service (`earnings/`, `analysis/`)

| Class | File | Why |
|-------|------|-----|
| `EarningsCalendarService` | `earnings/calendar.py` | Earnings calendar |
| `CalendarEvent`, `CalendarResult` | `earnings/calendar.py` | Event models |
| `EstimateSnapshot` | `earnings/estimates.py` | Point-in-time estimates |
| `EstimateRevision` | `earnings/estimates.py` | Revision tracking |
| `ActualReport` | `earnings/actuals.py` | Actual results |
| `EstimateActualComparison` | `analysis/comparison.py` | Surprise analysis |
| `ComparisonResult` | `analysis/comparison.py` | Comparison results |

#### Polygon Adapters (`adapter/`)
- `PolygonEarningsAdapter` - Polygon earnings feed
- `PolygonEstimateHistoryAdapter` - Estimate history feed
- `CopilotChatAdapter` - Chat integration

#### Models (`models/`)
- `Record`, `RecordCandidate` - Core record models
- `Sighting` - Sighting tracking
- `FeedRun` - Run metadata
- `Task`, `TaskResult` - Task models
- `Observation` - Observation model
- `Query`, `QuerySpec` - Query models

#### HTTP Client (`http/`)
- `HttpClient` - HTTP abstraction
- `RateLimiter`, `BurstRateLimiter` - Rate limiting
- `HostRateLimiter` - Per-host limiting

#### Utilities (`utils/`)
- `RetryConfig` - Retry configuration
- `VersionedRecord` - Version tracking
- `CompositeKeyBuilder` - Key building
- `UniqueConstraint` - Constraint definition

---

### **Tier 3 (NICE TO HAVE - 100+ classes)**

Supporting utilities, helpers, data classes.

- All remaining classes in `utils/`, `models/`, `protocols/`
- Internal implementation details
- Error classes and exceptions

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Composition Operators - Fluent Pipeline API

The `composition/` directory implements a fluent pipeline API:

```python
# Example: Build a pipeline with composition
from feedspine.composition import Feed, FilterOp, EnrichOp, DedupeOp

pipeline = (
    Feed("sec-filings", url="https://...")
    .filter(lambda r: r.form_type == "10-K")
    .enrich(entity_enricher)
    .dedupe(key=["accession_number"])
    .build()
)
```

**When annotating composition operators:**
- Explain how they chain together
- Show before/after record state
- Include fluent API examples

### Earnings Service - Key Business Logic

The `earnings/` and `analysis/` directories handle earnings data:

```python
# Earnings calendar and estimate tracking
class EarningsCalendarService:
    """
    Manages earnings calendar events and estimate snapshots.
    
    Manifesto:
        Observations (like earnings estimates) are versioned because
        analysts revise their estimates over time. We track:
        - Point-in-time snapshots (what was the estimate on this date?)
        - Revision history (how did estimates change?)
        - Actual vs estimate comparison (earnings surprise)
    """
```

### Manifesto Section - Emphasize These Principles

2. **`adapter/base.py` → `BaseFeedAdapter`** (ABC)
   - File: `feedspine/src/feedspine/adapter/base.py`
   - Priority: 10
   - Why: Base implementation with common functionality
   - Architecture: Template method pattern, hooks for customization
   - Features: Auto-retry, rate limiting, validation
   - Tags: `core_concept`, `template_method`, `base_class`

3. **`pipeline.py` → `Pipeline`**
   - File: `feedspine/src/feedspine/pipeline.py`
   - Priority: 10
   - Why: Orchestrates feed → storage flow
   - Manifesto: Medallion architecture (bronze → silver → gold)
   - Architecture: Data flow, transformation stages
   - Features: Deduplication, validation, metrics
   - Guardrails: Always preserve bronze (raw) layer
   - Tags: `core_concept`, `orchestration`, `data_pipeline`

4. **`storage/protocol.py` → `StorageProtocol`**
   - File: `feedspine/src/feedspine/storage/protocol.py`
   - Priority: 10
   - Why: Defines storage contract (swap backends)
   - Manifesto: Storage-agnostic design
   - Architecture: Protocol, method signatures
   - Tags: `core_concept`, `protocol`, `storage_abstraction`

#### Storage Implementations (`src/feedspine/storage/`)

5. **`storage/memory.py` → `MemoryStorage`**
   - File: `feedspine/src/feedspine/storage/memory.py`
   - Priority: 9
   - Why: In-memory storage for testing
   - Architecture: Dictionary-based, fast, ephemeral
   - Features: No I/O, instant dedup, testing
   - Guardrails: Do NOT use for production (data lost on exit)
   - Tags: `storage`, `in_memory`, `testing`, `ephemeral`

6. **`storage/sqlite.py` → `SQLiteStorage`**
   - File: `feedspine/src/feedspine/storage/sqlite.py`
   - Priority: 9
   - Why: Embedded database storage
   - Architecture: Single-file DB, ACID, indexes
   - Features: Persistent, SQL queries, FTS
   - Performance: Handles millions of records
   - Tags: `storage`, `sqlite`, `embedded`, `persistent`

7. **`storage/duckdb.py` → `DuckDBStorage`**
   - File: `feedspine/src/feedspine/storage/duckdb.py`
   - Priority: 8
   - Why: Analytics-optimized storage
   - Architecture: Columnar storage, vectorized queries
   - Features: OLAP queries, Parquet integration
   - Tags: `storage`, `duckdb`, `analytics`, `olap`

#### Feed Adapters (`src/feedspine/adapter/`)

8. **`adapter/rss.py` → `RSSFeedAdapter`**
   - File: `feedspine/src/feedspine/adapter/rss.py`
   - Priority: 9
   - Why: Common feed type (SEC RSS, news feeds)
   - Architecture: XML parsing, entry extraction
   - Features: Incremental updates, ETag support
   - Examples: SEC EDGAR RSS feed
   - Tags: `adapter`, `rss`, `xml`, `sec_edgar`

9. **`adapter/json.py` → `JSONFeedAdapter`**
   - File: `feedspine/src/feedspine/adapter/json.py`
   - Priority: 8
   - Why: JSON API feeds (FactSet, Polygon, etc.)
   - Architecture: HTTP client, JSON parsing, validation
   - Features: Pagination, rate limiting, retry
   - Tags: `adapter`, `json`, `api`, `http`

10. **`adapter/file.py` → `FileFeedAdapter`**
    - File: `feedspine/src/feedspine/adapter/file.py`
    - Priority: 8
    - Why: File-based feeds (CSV, Parquet, local files)
    - Architecture: File watching, change detection
    - Features: Snapshot comparison, diff generation
    - Tags: `adapter`, `file`, `csv`, `parquet`

#### Analysis & Enrichment

11. **`analysis/comparison.py` → `EstimateActualComparison`**
    - File: `feedspine/src/feedspine/analysis/comparison.py`
    - Priority: 9
    - Why: Compare estimates to actuals (earnings surprise)
    - Manifesto: Data quality gates, archetype-specific logic
    - Architecture: Observation archetype queries
    - Features: Surprise calculation, confidence scoring
    - Tags: `analysis`, `observations`, `earnings`, `comparison`

12. **`models/feeds.py` → `FeedConfig`**
    - File: `feedspine/src/feedspine/models/feeds.py`
    - Priority: 8
    - Why: Feed configuration and metadata
    - Architecture: Pydantic models, validation
    - Features: URL, schedule, credentials, natural key config
    - Tags: `configuration`, `metadata`, `validation`

---

### **Tier 2 (SHOULD Annotate - 15 classes)**

Important classes that support core functionality. Annotate with MOST sections.

#### Schedulers & Execution
13. `scheduler/cron.py` → `CronScheduler`
14. `executor/async.py` → `AsyncExecutor`
15. `executor/sync.py` → `SyncExecutor`

#### Enrichment
16. `enricher/base.py` → `Enricher`
17. `enricher/llm.py` → `LLMEnricher`

#### Metrics & Monitoring
18. `metrics/collector.py` → `MetricsCollector`
19. `metrics/reporter.py` → `MetricsReporter`

#### Queue Management
20. `queue/manager.py` → `QueueManager`
21. `queue/priority.py` → `PriorityQueue`

#### Blob Storage
22. `blob/s3.py` → `S3BlobStore`
23. `blob/local.py` → `LocalBlobStore`

#### Specific Adapters
24. `adapter/polygon_earnings.py` → `PolygonEarningsAdapter`
25. `earnings/calendar.py` → `EarningsCalendar`

#### Search & Discovery
26. `search/engine.py` → `SearchEngine`
27. `discovery.py` → `FeedDiscovery`

---

### **Tier 3 (NICE TO HAVE - remaining classes)**

Supporting utilities, helpers, data classes. Can have basic docstrings.

28-60+: All remaining classes in `utils/`, `models/`, `protocols/`, etc.

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Manifesto Section - Emphasize These Principles

For FeedSpine classes, ALWAYS include these in Manifesto:

```python
Manifesto:
    Data quality gates prevent garbage-in-garbage-out.
    
    [For storage classes]
    The medallion architecture (Bronze → Silver → Gold) ensures:
    - Bronze: Preserve raw data exactly as received (data lineage)
    - Silver: Apply validation and normalization (clean data)
    - Gold: Curate for analytics (denormalized, aggregated)
    
    [For adapter classes]
    Storage-agnostic design means you can swap backends without
    changing your feed logic. Code against StorageProtocol, not
    concrete implementations.
    
    [For dedup/sighting]
    Track ALL sightings, not just the first. A SEC filing appearing
    in RSS (5 min), daily index (next day), and quarterly index
    (quarterly) is ONE record with THREE sightings.
    
    [For data archetypes]
    Observations (metrics) need versioning because they get restated.
    Events (earnings calls) are point-in-time and immutable.
    Know your archetype, optimize accordingly.
```

### Architecture Section - Data Flow

For pipeline/adapter classes, include data flow:

```python
Architecture:
    ```
    External Feed (SEC EDGAR, FactSet, etc.)
          ↓
    FeedAdapter.fetch()
          ↓
    ┌─────────────────────────┐
    │  Transformation:        │
    │  1. Validate schema     │
    │  2. Extract natural key │
    │  3. Compute content hash│
    └───────────┬─────────────┘
                ↓
    Storage.store()
          ↓
    ┌─────────────────────────┐
    │  Medallion Tiers:       │
    │  Bronze: Raw (S3)       │
    │  Silver: Clean (DuckDB) │
    │  Gold: Curated (PG)     │
    └─────────────────────────┘
    ```
    
    Deduplication: Content-addressed hashing
    Validation: Pydantic schemas
    Concurrency: Async/await with semaphore
    Storage: Pluggable backend (StorageProtocol)
```

### Features Section - Feed Capabilities

For adapter classes:

```python
Features:
    - Automatic retry with exponential backoff
    - Rate limiting (configurable per-feed)
    - Incremental updates (fetch only new records)
    - ETag/If-Modified-Since support (HTTP optimization)
    - Deduplication by natural key
    - Sighting history tracking
    - Schema validation (Pydantic)
    - Metrics collection (fetch time, record count, errors)
    - Credential management (env vars, secrets)
```

### Guardrails Section - Common FeedSpine Mistakes

```python
Guardrails:
    - Do NOT skip bronze layer (always preserve raw data)
      ✅ Instead: Store raw in S3/blob, then transform
    
    - Do NOT mutate raw data
      ✅ Instead: Create new normalized version in silver tier
    
    - Do NOT assume deduplication by database ID
      ✅ Instead: Configure natural key for your domain
    
    - Do NOT treat all data the same
      ✅ Instead: Identify archetype (Observation/Event/Entity/etc.)
    
    - Do NOT hardcode storage backend
      ✅ Instead: Accept StorageProtocol, swap at runtime
    
    - ALWAYS track provenance (source, timestamp, version)
      (Critical for data lineage and debugging)
```

### Tags - Use These FeedSpine-Specific Tags

Required tags by domain:
- **Core**: `core_concept`, `adapter_pattern`, `protocol`, `storage_abstraction`
- **Storage**: `storage`, `sqlite`, `duckdb`, `postgresql`, `in_memory`, `s3`, `blob`
- **Medallion**: `bronze`, `silver`, `gold`, `raw_data`, `clean_data`, `curated`
- **Archetypes**: `observations`, `events`, `entities`, `documents`, `prices`
- **Feeds**: `adapter`, `rss`, `json`, `api`, `http`, `file`, `csv`
- **Data Sources**: `sec_edgar`, `factset`, `polygon`, `bloomberg`
- **Dedup**: `deduplication`, `natural_key`, `content_hash`, `sighting`
- **Quality**: `validation`, `pydantic`, `schema`, `data_quality`

### Doc-Types - Where FeedSpine Classes Should Appear

Map classes to documentation:

```python
Doc-Types:
    - MANIFESTO (section: "Data Quality", priority: 9)
      # For classes about medallion architecture, quality gates
    
    - FEATURES (section: "Adapters", priority: 10)
      # For feed adapter capabilities
    
    - FEATURES (section: "Storage Backends", priority: 9)
      # For storage implementations
    
    - ARCHITECTURE (section: "Feed System", priority: 10)
      # For pipeline, data flow, architecture
    
    - GUARDRAILS (section: "Data Management", priority: 9)
      # For classes with common pitfalls
    
    - API_REFERENCE (section: "Core APIs", priority: 8)
      # For public API classes
```

### Data Archetype Annotations

If a class handles specific data archetypes, note it:

```python
Data-Archetype:
    Type: Observation  # or Event, Entity, Document, Price
    
    Characteristics:
    - Versioning: Required (observations get restated)
    - Point-in-time queries: Required (backtesting)
    - Storage: TimescaleDB (time-series optimized)
    - Dedup: (entity_id, metric_key, period_key, as_of)
    
    See: guides/DATA_ARCHETYPES_GUIDE.md
```

---

## 📚 REFERENCE DOCUMENTS

### Must Read Before Annotating

1. **FeedSpine README**: `feedspine/README.md`
   - Understand the "Why" and quick start

2. **Data Archetypes Guide**: `feedspine/docs/archive/design/DATA_ARCHETYPES_GUIDE.md`
   - CRITICAL: Understand the 5 data archetypes
   - How each archetype needs different storage/indexing

3. **Medallion Architecture**: Search docs for bronze/silver/gold
   - Why we preserve raw data
   - Quality gates between tiers

### Example Annotated Class (Full Template)

```python
from feedspine.adapter.base import BaseFeedAdapter
from feedspine.models.feeds import FeedConfig

class RSSFeedAdapter(BaseFeedAdapter):
    """
    Feed adapter for RSS/Atom feeds (SEC EDGAR, news feeds, blogs).
    
    Fetches XML feeds, parses entries, extracts natural keys, and
    stores with automatic deduplication.
    
    Manifesto:
        Storage-agnostic design means you can swap backends without
        changing your feed logic.
        
        The RSS adapter handles the hard parts:
        - Incremental updates (only fetch new entries)
        - ETag/If-Modified-Since HTTP optimization
        - XML parsing (RSS 2.0, Atom 1.0)
        - Natural key extraction (often GUID or link)
        - Deduplication across multiple feeds
        
        Deduplication example: SEC filing appears in:
        - RSS feed (5 minutes after filing)
        - Daily index (next day)
        - Quarterly index (end of quarter)
        
        FeedSpine stores it ONCE, tracks THREE sightings.
        
        This prevents wasted storage and duplicate processing while
        preserving complete data lineage.
    
    Architecture:
        ```
        RSS Feed URL
              ↓
        HTTP GET (with ETag/If-Modified-Since)
              ↓
        Parse XML (RSS/Atom)
              ↓
        Extract Entries
              ↓
        ┌─────────────────────────┐
        │  Per Entry:             │
        │  1. Extract natural key │
        │  2. Validate schema     │
        │  3. Compute content hash│
        └───────────┬─────────────┘
                    ↓
        Storage.store()
              ↓
        Deduplicate by natural key
        ```
        
        HTTP Client: aiohttp (async) or requests (sync)
        XML Parser: xml.etree.ElementTree (stdlib)
        Validation: Pydantic schemas
        Concurrency: Semaphore (max 10 concurrent)
        Retry: Exponential backoff (3 attempts)
    
    Features:
        - RSS 2.0 and Atom 1.0 support
        - Incremental updates (ETag, If-Modified-Since, Last-Modified)
        - Automatic retry with exponential backoff
        - Rate limiting (configurable requests/second)
        - Deduplication by natural key (GUID, link, or custom)
        - Sighting history (track when/where seen)
        - Schema validation (Pydantic)
        - Metrics (fetch time, entry count, errors)
    
    Examples:
        >>> from feedspine import FeedSpine, MemoryStorage, RSSFeedAdapter
        >>> 
        >>> # SEC EDGAR RSS feed
        >>> adapter = RSSFeedAdapter(
        ...     name="sec-filings",
        ...     url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&CIK=&type=&company=&dateb=&owner=exclude&start=0&count=100&output=atom",
        ...     natural_key_field="id"  # Use GUID as natural key
        ... )
        >>> 
        >>> storage = MemoryStorage()
        >>> async with FeedSpine(storage=storage) as spine:
        ...     spine.register_feed(adapter)
        ...     result = await spine.collect()
        ...     print(f"New: {result.total_new}, Dupes: {result.total_duplicates}")
        New: 100, Dupes: 0
        
        # Hacker News RSS
        >>> hn_adapter = RSSFeedAdapter(
        ...     name="hacker-news",
        ...     url="https://news.ycombinator.com/rss",
        ...     natural_key_field="link"
        ... )
    
    Performance:
        - Fetch: ~200-500ms (network-bound)
        - Parse: ~10-50ms per 100 entries
        - Store: Depends on backend (memory: <1ms, SQLite: ~5ms, PostgreSQL: ~10ms)
        - Throughput: ~100 entries/second (I/O bound)
        - Memory: ~5MB for 10K entries
    
    Guardrails:
        - Do NOT skip natural key configuration
          ✅ Instead: Set natural_key_field or natural_key_extractor
        
        - Do NOT parse HTML as RSS
          ✅ Instead: Check Content-Type header, use correct adapter
        
        - Do NOT ignore HTTP cache headers
          ✅ Instead: Store ETag/Last-Modified, use on next fetch
        
        - Do NOT assume all entries are new
          ✅ Instead: Let FeedSpine deduplicate by natural key
        
        - ALWAYS handle network errors gracefully
          (Feeds go down, timeouts happen, plan for it)
    
    Context:
        Problem: RSS feeds often have overlapping content (same filing
        in multiple feeds), manual dedup is error-prone and wastes storage.
        
        Solution: Extract natural key (GUID, link), let storage backend
        handle deduplication, track all sightings for lineage.
        
        Alternatives Considered:
        - Parse HTML: Too brittle, feed URLs change
        - Scrape pages: Rate limits, TOS violations
        - Manual polling: Miss updates, waste bandwidth
        
        Why RSS: Standardized format, push-like (polling is efficient),
        supported by most data providers, includes metadata.
    
    Changelog:
        - v0.1.0: Initial RSS adapter
        - v0.2.0: Added Atom 1.0 support
        - v0.3.0: ETag/If-Modified-Since optimization
        - v0.4.0: Natural key extraction (configurable)
    
    Feature-Guide:
        Target: guides/FEED_ADAPTERS_GUIDE.md
        Section: "RSS Feeds"
        Include-Example: True
        Priority: 10
    
    Architecture-Doc:
        Target: architecture/FEED_ARCHITECTURE.md
        Section: "Adapter Implementations"
        Diagram-Type: ascii
    
    Tags:
        - adapter
        - rss
        - xml
        - http
        - sec_edgar
        - incremental_updates
        - deduplication
    
    Doc-Types:
        - MANIFESTO (section: "Storage Agnostic", priority: 8)
        - FEATURES (section: "Adapters", priority: 10)
        - ARCHITECTURE (section: "Feed System", priority: 9)
        - API_REFERENCE (section: "Adapters", priority: 9)
    """
    ...
```

---

## ✅ VALIDATION CHECKLIST

Before submitting annotated FeedSpine classes:

### Content Requirements
- [ ] Manifesto explains medallion architecture (if applicable)
- [ ] Manifesto mentions storage-agnostic design
- [ ] Architecture includes data flow diagram
- [ ] Architecture notes deduplication strategy
- [ ] Features list includes retry/rate limiting
- [ ] Examples use doctest format (`>>>`)
- [ ] Guardrails warn about skipping bronze layer
- [ ] Tags include FeedSpine-specific tags
- [ ] Data archetype noted (if applicable)

### FeedSpine-Specific
- [ ] Uses correct terminology (Bronze/Silver/Gold)
- [ ] Mentions natural key for dedup
- [ ] Includes sighting history concept
- [ ] References data archetypes if applicable
- [ ] Storage tier mentioned for storage classes

### Quality
- [ ] At least 3 tags
- [ ] At least 2 doc-types
- [ ] Examples are runnable
- [ ] No TODO or placeholder text

---

## 🚀 QUICK START

1. **Read this entire guide** (10 minutes)
2. **Read DATA_ARCHETYPES_GUIDE.md** (15 minutes) - CRITICAL
3. **Read EXTENDED_ANNOTATION_PROMPT.md** (15 minutes)
4. **Pick ONE Tier 1 class** from the list above
5. **Read the existing code** and any related docs
6. **Annotate using full extended format**
7. **Validate**: `docbuilder validate <file>`
8. **Submit for review** before batch-annotating others

---

**Ready? Start with `FeedAdapter` (protocol) or `Pipeline` class - they're the foundation of FeedSpine!**
