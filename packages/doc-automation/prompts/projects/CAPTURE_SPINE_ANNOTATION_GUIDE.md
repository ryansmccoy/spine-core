# 📡 Capture-Spine - Annotation Guide

**Project-Specific Guide for Annotating Capture-Spine Classes**

*For use with Documentation Automation Package - February 2026*

---

## 📋 PROJECT CONTEXT

### What is Capture-Spine?

**Capture-Spine** is a point-in-time content capture system with full lineage tracking:

> *"I need to capture content from RSS feeds, financial documents, research papers, and knowledge notes—and answer 'what was visible at 2:30pm yesterday?'"*

### Core Philosophy

**Principle #1: Point-in-Time Accuracy**

Every record has exact timestamp and full audit trail:
- **When**: Captured at 2024-01-30 14:30:00 EST
- **Where**: Source feed (SEC EDGAR RSS, HN, etc.)
- **What**: Exact content (deduplicated, immutable)
- **Changes**: Track all modifications with version history

Query historical state: "Show me what was in my feed at 2:30pm yesterday"

**Principle #2: Content Deduplication with Sighting Lineage**

Same content from multiple sources = 1 record with sighting history:
- Record: "Tesla Q4 Earnings Report"
- Sighting 1: 2024-01-30 09:15 (SEC RSS feed)
- Sighting 2: 2024-01-30 10:00 (Bloomberg RSS)
- Sighting 3: 2024-01-31 08:00 (Daily index)

**Principle #3: Multi-Backend Search**

Search flexibility with performance:
- **PostgreSQL** - Always-on, full-text search (tsvector + trigram)
- **Elasticsearch** - Optional, complex queries, faceting
- **Hybrid** - PostgreSQL for simple queries, Elasticsearch for advanced

**Principle #4: Feed → Item → Record → Sighting Data Model**

```
FEEDS → ITEMS → RECORDS → SIGHTINGS
  │        │        │          │
  │        │        │          └── Lineage (when/where first seen)
  │        │        └── Unique entities (deduplicated)
  │        └── Raw HTTP responses (bronze tier)
  └── Configured data sources (RSS, API, file)
```

- **Feed**: Data source configuration (URL, schedule, credentials)
- **Item**: Raw HTTP response (preserve provenance, immutable)
- **Record**: Deduplicated entity (unique by natural key)
- **Sighting**: Observation of record in feed at timestamp

**Principle #5: Execution Ledger for All Background Jobs**

Every background task tracked:
- Job ID, type, status, start/end time
- Worker that executed it
- Success/failure with error details
- Retry count, next retry time

Full audit trail for debugging and compliance.

### Key Concepts

1. **Feed** - Configured data source (RSS, document feed, custom)
2. **Item** - Raw capture (HTTP response, file content)
3. **Record** - Deduplicated entity (unique by content hash or natural key)
4. **Sighting** - Observation (when/where record was seen)
5. **Point-in-Time Query** - Query historical state ("what was visible at X time?")
6. **Sighting Lineage** - Full history of when/where record appeared
7. **Execution Ledger** - Audit trail of all background jobs
8. **Body Store** - Content-addressed storage (S3, filesystem)

### Architecture Patterns

1. **Repository Pattern** - Abstract data access (services use repositories)
2. **Service Layer** - Business logic separated from API/storage
3. **Content-Addressed Storage** - Deduplicate by content hash
4. **Medallion Architecture** - Bronze (raw) → Silver (clean) → Gold (curated)
5. **Observer Pattern** - Real-time notifications (alerts, webhooks)

---

## 🎯 CLASSES TO ANNOTATE

### **Tier 1 (MUST Annotate - 15 classes)**

Core domain models, services, and critical infrastructure.

#### 🔴 Dependency Injection (`app/container.py`) - **CRITICAL**

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Container` | `app/container.py` | **10** | DI container - wires all services together |

The Container class is THE central configuration point. All services are registered here:
```python
class Container:
    """
    Dependency injection container for Capture-Spine.
    
    Wires together services, repositories, and adapters.
    Replace for testing, swap implementations at runtime.
    """
```

#### Settings & Configuration

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Settings` | `app/settings.py` | **10** | Environment config with `DeploymentTier` |
| `DeploymentTier` | `app/settings.py` | 9 | Local/Dev/QA/Staging/Production tiers |

#### Domain Models (`app/models.py`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `FeedBase`/`FeedRead` | `app/models.py` | **10** | Core - what is a feed? |
| `ItemCreate`/`ItemRead` | `app/models.py` | **10** | Raw capture (bronze tier) |
| `RecordCreate`/`RecordRead` | `app/models.py` | **10** | Deduplicated entity |
| `SightingCreate`/`SightingRead` | `app/models.py` | **10** | Lineage tracking |
| `RunMetadata` | `app/models.py` | 9 | Feed run metadata |
| `CheckpointRead` | `app/models.py` | 8 | Processing checkpoints |
| `SystemStatus` | `app/models.py` | 8 | System health model |

#### Core Services (`app/domains/`, `app/features/`)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `SearchService` | (services) | **10** | Multi-backend search (PG + ES) |
| `PollerService` | (services) | 9 | Adaptive polling scheduler |
| `ParserService` | (services) | 9 | Extensible parser system |
| `WorkSessionService` | (services) | 9 | Refactored from god class |
| `ChatSessionService` | (services) | 9 | Refactored from god class |

---

### **Tier 2 (SHOULD Annotate - 30 classes)**

Important supporting classes. Annotate with MOST sections.

#### Domains Layer (`app/domains/`) - **MODULAR ARCHITECTURE**

The `domains/` directory organizes by business domain:
- `feeds/` - Feed management
- `records/` - Record handling
- `search/` - Search functionality
- `users/` - User management

#### Features Layer (`app/features/`)

Feature-specific modules:
- Feed discovery
- Alert rules
- Daily digest
- Recommendations

#### API Routes (`app/api/`)

The API has 15+ route modules:

| Module | Key Classes | Why |
|--------|-------------|-----|
| `archive.py` | `ArchiveListEntry`, `TriggerArchiveRequest` | Archive management |
| `auth.py` | `AuthModeResponse`, `MessageResponse` | Authentication |
| `blobs.py` | `BlobUploadResponse`, `BlobMetadata` | Blob storage |
| `documents.py` | `UploadResponse` | Document upload |
| `entityspine.py` | `TickerResponse`, `CikResponse`, `ResolveResponse` | Entity resolution |
| `feed_preview.py` | Feed preview models | Feed testing |
| `filters.py` | Filter models | Search filters |
| `groups.py` | Group models | Feed grouping |
| `health.py` | Health check models | System health |
| `infrastructure.py` | Infrastructure models | System config |
| `jobs.py` | Job models | Background jobs |
| `onboarding.py` | Onboarding models | User onboarding |
| `performance.py` | Performance models | Metrics |
| `query.py` | Query models | Search queries |
| `records.py` | Record API models | Record CRUD |
| `subscriptions.py` | Subscription models | Feed subscriptions |

#### Core Layer (`app/core/`)

- Database utilities
- Middleware
- Security helpers

#### Orchestration (`app/orchestration/`)

- Celery tasks
- Background job management

---

### **Tier 3 (NICE TO HAVE - 100+ classes)**

Supporting utilities, error classes, internal implementations.

- All remaining API request/response models
- Database utilities in `app/db/`
- LLM integration in `app/llm/`
- Pipeline classes in `app/pipelines/`
- Runtime utilities in `app/runtime/`
- Task definitions in `app/tasks/`

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Container Pattern - Dependency Injection

The `Container` class in `app/container.py` is central:

```python
class Container:
    """
    Dependency injection container for Capture-Spine.
    
    Manifesto:
        Dependency injection enables:
        - Testability: Swap services with mocks
        - Flexibility: Swap implementations at runtime
        - Maintainability: Clear dependencies, no hidden coupling
        
        All services are registered here. When you need a service,
        inject Container and access via container.service_name.
    
    Architecture:
        ```
        Container
          ├── Settings (configuration)
          ├── Database (session factory)
          ├── Services
          │     ├── SearchService
          │     ├── PollerService
          │     ├── ParserService
          │     ├── WorkSessionService
          │     └── ChatSessionService
          └── Adapters
                ├── EntitySpineAdapter
                └── BlobStorage
        ```
    """
```

### Manifesto Section - Emphasize These Principles

For Capture-Spine classes:

```python
Manifesto:
    Point-in-time accuracy enables time travel:
    "What was in my feed at 2:30pm yesterday?"
    
    [For domain models]
    The Feed → Item → Record → Sighting data model ensures:
    - Feeds: Where content comes from
    - Items: Raw capture (bronze, immutable)
    - Records: Deduplicated entities (unique by natural key)
    - Sightings: Lineage (when/where record was seen)
    
    [For search]
    Multi-backend search provides flexibility:
    - PostgreSQL: Always-on, full-text (tsvector + trigram)
    - Elasticsearch: Optional, complex queries, faceting
    - Hybrid: Best of both worlds
    
    [For deduplication]
    Content-addressed hashing prevents duplicate storage.
    Same content from 3 feeds = 1 record with 3 sightings.
    
    [For execution ledger]
    Every background job is tracked for full audit trail:
    - Job ID, type, status
    - Start/end time, duration
    - Worker, retry count
    - Success/failure with error details
    
    [For services - after god class refactoring]
    Single responsibility: WorkSessionService manages ONLY work
    sessions, ChatSessionService manages ONLY chat sessions.
    Refactored from monolithic god class for maintainability.
```

### Architecture Section - Data Flow

```python
Architecture:
    ```
    External Feed (RSS, API, File)
          ↓
    Poller (Celery task, adaptive schedule)
          ↓
    ┌─────────────────────────┐
    │  Capture:               │
    │  1. Fetch HTTP response │
    │  2. Store as Item       │
    │     (bronze tier)       │
    └───────────┬─────────────┘
                ↓
    Parser (extract metadata, entities)
          ↓
    ┌─────────────────────────┐
    │  Deduplication:         │
    │  1. Compute content hash│
    │  2. Lookup Record       │
    │  3. Create if new       │
    │  4. Add Sighting        │
    └───────────┬─────────────┘
                ↓
    ┌─────────────────────────┐
    │  Storage:               │
    │  PostgreSQL: Metadata   │
    │  S3/Filesystem: Bodies  │
    │  Elasticsearch: Search  │
    └───────────┬─────────────┘
                ↓
    ┌─────────────────────────┐
    │  Search Index:          │
    │  Update tsvector        │
    │  Sync Elasticsearch     │
    └─────────────────────────┘
    ```
    
    Deduplication: Content-addressed hashing (SHA-256)
    Storage: Metadata (PG) + Bodies (S3) separation
    Search: Hybrid (PostgreSQL + Elasticsearch)
    Background: Celery workers with execution ledger
```

### Features Section - Capture Capabilities

```python
Features:
    - Universal content capture (RSS, documents, knowledge notes)
    - Point-in-time queries ("what was visible at 2:30pm?")
    - Content deduplication (same content = 1 record, N sightings)
    - Multi-backend search (PostgreSQL + Elasticsearch)
    - Personalized recommendations ("For You" feed)
    - Knowledge management (notes, prompts, collections)
    - Feed discovery (curated catalog, categories)
    - Adaptive polling (smart schedules)
    - Time travel & replay (historical state queries)
    - LLM integration (categorization, topic clustering)
    - Execution ledger (full audit trail)
    - Extensible parsers (SEC filings, HN, custom)
```

### Guardrails Section - Common Capture Mistakes

```python
Guardrails:
    - Do NOT mutate Items (they're immutable, bronze tier)
      ✅ Instead: Create new Record if content changed
    
    - Do NOT skip deduplication
      ✅ Instead: Always check existing Records by content hash
    
    - Do NOT assume feeds are reliable
      ✅ Instead: Handle timeouts, errors, rate limits gracefully
    
    - Do NOT store bodies in PostgreSQL
      ✅ Instead: Use content-addressed storage (S3/filesystem)
    
    - Do NOT hardcode search backend
      ✅ Instead: Support PostgreSQL, Elasticsearch, hybrid
    
    - Do NOT skip sighting creation
      ✅ Instead: ALWAYS create sighting for lineage tracking
    
    - ALWAYS log background jobs in execution ledger
      (Critical for debugging and audit trail)
```

### Tags - Use These Capture-Specific Tags

Required tags by domain:
- **Core**: `core_concept`, `domain_model`, `data_model`
- **Domain**: `feed`, `item`, `record`, `sighting`
- **Tiers**: `bronze_tier`, `silver_tier`, `gold_tier`
- **Features**: `search`, `discovery`, `recommendations`, `knowledge_management`
- **Search**: `postgresql`, `elasticsearch`, `hybrid_search`, `full_text`
- **Background**: `background_job`, `polling`, `parsing`, `scheduler`
- **Lineage**: `lineage`, `point_in_time`, `deduplication`, `sighting_history`
- **Services**: `service`, `refactored`, `god_class_fix`
- **Monitoring**: `alerting`, `monitoring`, `execution_ledger`, `audit_trail`

### Doc-Types - Where Capture Classes Should Appear

```python
Doc-Types:
    - MANIFESTO (section: "Point-in-Time Accuracy", priority: 10)
      # For classes about sightings, lineage, time travel
    
    - FEATURES (section: "Content Capture", priority: 10)
      # For feed, item, record, sighting models
    
    - FEATURES (section: "Search & Discovery", priority: 9)
      # For search, recommendations, feed discovery
    
    - ARCHITECTURE (section: "Data Model", priority: 10)
      # For Feed → Item → Record → Sighting flow
    
    - ARCHITECTURE (section: "Background Jobs", priority: 9)
      # For polling, parsing, execution ledger
    
    - GUARDRAILS (section: "Data Integrity", priority: 9)
      # For immutability, deduplication, audit trail
    
    - API_REFERENCE (section: "Core APIs", priority: 8)
      # For API route classes
```

### Refactoring Context (God Class Fixes)

If a class was recently refactored from a god class:

```python
Refactoring-Context:
    Original: Monolithic service handling work sessions, chat
    sessions, alert rules, search, recommendations (1500+ lines)
    
    Problem: Single Responsibility Principle violation, hard to
    test, changes affect multiple features.
    
    Solution: Split into focused services:
    - WorkSessionService: ONLY work session management
    - ChatSessionService: ONLY chat session management
    - AlertRulesService: ONLY alert rules
    - SearchService: ONLY search
    - RecommendationService: ONLY recommendations
    
    Benefits:
    - Easier to test (mock fewer dependencies)
    - Easier to reason about (single responsibility)
    - Easier to change (isolated impact)
    - Better type safety (fewer Optional fields)
    
    See: RESTRUCTURE_PLAN.md, RESTRUCTURE_COMPLETE.md
```

---

## 📚 REFERENCE DOCUMENTS

### Must Read Before Annotating

1. **Capture-Spine README**: `capture-spine/README.md`
   - Overview, architecture, data flow

2. **Features Overview**: `capture-spine/docs/features/FEATURES_OVERVIEW.md`
   - All 12+ core capabilities

3. **Architecture Docs**: `capture-spine/docs/architecture/01_system_overview.md`
   - System architecture, data model, background jobs

4. **Restructuring Docs**: `capture-spine/RESTRUCTURE_PLAN.md` + `RESTRUCTURE_COMPLETE.md`
   - God class refactoring context

### Example Annotated Class (Full Template)

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class SightingCreate(BaseModel):
    """
    Record a sighting - when/where a record was observed.
    
    Sightings enable point-in-time queries and full lineage tracking.
    Critical for answering "what was visible at 2:30pm yesterday?"
    
    Manifesto:
        Sightings are the foundation of point-in-time accuracy.
        
        Every time content appears in a feed, we create a sighting:
        - Record ID (what was seen)
        - Feed ID (where it was seen)
        - Timestamp (when it was seen)
        
        Multiple sightings for same record = lineage:
        Example: "Tesla Q4 Earnings" appears in 3 feeds:
        - Sighting 1: 2024-01-30 09:15 (SEC RSS)
        - Sighting 2: 2024-01-30 10:00 (Bloomberg)
        - Sighting 3: 2024-01-31 08:00 (Daily index)
        
        This enables:
        - Time travel: "Show me what was in my feed at 2:30pm"
        - Lineage: "Where did this record come from?"
        - Deduplication: "Have we seen this before?"
        - Freshness: "When was this last seen?"
        
        Without sightings, we lose provenance and temporal context.
    
    Architecture:
        ```
        Feed Poll
              ↓
        Fetch Items (HTTP responses)
              ↓
        Parse → Extract Records
              ↓
        ┌─────────────────────────┐
        │  For each Record:       │
        │  1. Check existing      │
        │  2. Create if new       │
        │  3. CREATE SIGHTING     │
        └───────────┬─────────────┘
                    ↓
        PostgreSQL Sightings Table:
        - record_id (FK)
        - feed_id (FK)
        - sighted_at (timestamp)
        - item_id (FK, optional)
              ↓
        Index: (sighted_at, feed_id) for temporal queries
        Index: (record_id) for lineage queries
        ```
        
        Storage: PostgreSQL (metadata only)
        Indexing: Composite indexes for time + feed queries
        Partitioning: By month (for large datasets)
        Retention: Configurable (default: 2 years)
    
    Features:
        - Automatic creation on record capture
        - Timestamp precision (microseconds)
        - Optional item reference (link to raw capture)
        - Feed lineage tracking
        - Point-in-time query support
        - Temporal range queries (between timestamps)
        - Deduplication check (has record been seen?)
    
    Examples:
        >>> from capture_spine import CaptureSpine
        >>> 
        >>> # Create sighting when record is captured
        >>> sighting = await spine.create_sighting(
        ...     record_id=123,
        ...     feed_id=456,
        ...     sighted_at=datetime.now(),
        ...     item_id=789  # Optional
        ... )
        
        # Query: "What records were visible at 2:30pm?"
        >>> records = await spine.query_records_at_time(
        ...     timestamp=datetime(2024, 1, 30, 14, 30),
        ...     feed_id=456
        ... )
        
        # Query: "Where did this record come from?"
        >>> sightings = await spine.get_sightings(record_id=123)
        >>> for s in sightings:
        ...     print(f"Seen at {s.sighted_at} in feed {s.feed_id}")
        Seen at 2024-01-30 09:15:00 in feed 456
        Seen at 2024-01-30 10:00:00 in feed 789
    
    Performance:
        - Insert: <5ms (indexed table)
        - Query by time: ~10ms (indexed sighted_at)
        - Query by record: ~5ms (indexed record_id)
        - Storage: ~50 bytes per sighting
        - Partitioning: By month (improves query speed)
    
    Guardrails:
        - Do NOT skip sighting creation
          ✅ Instead: ALWAYS create sighting when record captured
        
        - Do NOT mutate existing sightings
          ✅ Instead: Sightings are immutable (audit trail)
        
        - Do NOT query sightings without time bounds
          ✅ Instead: Always use time ranges (prevent full scan)
        
        - Do NOT store duplicate sightings
          ✅ Instead: Unique constraint on (record_id, feed_id, sighted_at)
        
        - ALWAYS index by sighted_at for temporal queries
          (Critical for point-in-time query performance)
    
    Context:
        Problem: Users need to know "what was in my feed yesterday?"
        and "where did this content come from?" Standard RSS readers
        don't track this - they only show current state.
        
        Solution: Create sighting for every observation. Track when/
        where each record appeared, enabling time travel queries and
        full lineage.
        
        Alternatives Considered:
        - Version records: Too complex, storage overhead
        - Event sourcing: Over-engineered for this use case
        - No tracking: Lose temporal context and provenance
        
        Why Sightings:
        - Simple model (3 fields: record, feed, time)
        - Fast queries (indexed by time)
        - Full lineage (all observations tracked)
        - Low storage (50 bytes per sighting)
    
    Changelog:
        - v0.1.0: Initial sighting model
        - v0.2.0: Added item_id reference
        - v0.3.0: Partitioning by month
        - v0.4.0: Unique constraint on (record, feed, time)
    
    Feature-Guide:
        Target: guides/POINT_IN_TIME_QUERIES.md
        Section: "Sighting Model"
        Include-Example: True
        Priority: 10
    
    Architecture-Doc:
        Target: architecture/DATA_MODEL.md
        Section: "Sightings"
        Diagram-Type: erd
    
    Tags:
        - core_concept
        - domain_model
        - sighting
        - lineage
        - point_in_time
        - audit_trail
        - temporal_query
    
    Doc-Types:
        - MANIFESTO (section: "Point-in-Time Accuracy", priority: 10)
        - ARCHITECTURE (section: "Data Model", priority: 10)
        - FEATURES (section: "Time Travel", priority: 9)
        - API_REFERENCE (section: "Sightings API", priority: 8)
    """
    
    record_id: int = Field(..., description="Record that was seen")
    feed_id: int = Field(..., description="Feed where it was seen")
    sighted_at: datetime = Field(..., description="When it was seen")
    item_id: Optional[int] = Field(None, description="Raw item (optional)")
```

---

## ✅ VALIDATION CHECKLIST

Before submitting annotated Capture-Spine classes:

### Content Requirements
- [ ] Manifesto explains point-in-time accuracy (if applicable)
- [ ] Manifesto mentions Feed → Item → Record → Sighting model
- [ ] Architecture includes data flow diagram
- [ ] Architecture notes deduplication strategy
- [ ] Features list search backends (PostgreSQL, Elasticsearch)
- [ ] Examples use async/await
- [ ] Guardrails warn about immutability (items/sightings)
- [ ] Tags include Capture-specific tags
- [ ] Refactoring context noted (if god class fix)

### Capture-Specific
- [ ] Uses correct terminology (feed, item, record, sighting)
- [ ] Mentions lineage/provenance (if applicable)
- [ ] Notes execution ledger (if background job)
- [ ] References multi-backend search (if search-related)
- [ ] Includes point-in-time query example (if sighting/record)

### Quality
- [ ] At least 3 tags
- [ ] At least 2 doc-types
- [ ] Examples are runnable
- [ ] No TODO or placeholder text

---

## 🚀 QUICK START

1. **Read this entire guide** (10 minutes)
2. **Read FEATURES_OVERVIEW.md** (15 minutes)
3. **Read RESTRUCTURE_COMPLETE.md** (10 minutes) - understand god class fixes
4. **Read EXTENDED_ANNOTATION_PROMPT.md** (15 minutes)
5. **Pick ONE Tier 1 class** (SightingCreate or FeedBase)
6. **Read existing code** and related docs
7. **Annotate using full extended format**
8. **Validate**: `docbuilder validate <file>`
9. **Submit for review** before batch-annotating

---

**Ready? Start with `SightingCreate` - it's the foundation of point-in-time accuracy!**
