# 📋 COPY-PASTE PROMPT: Annotate FeedSpine Classes

**Copy everything below and send to an LLM with file editing access:**

---

## TASK: Add Extended Docstrings to FeedSpine Classes

You are a documentation automation agent. Add rich extended docstrings to Python classes in the FeedSpine project.

### Project Context

**FeedSpine** is a storage-agnostic, executor-agnostic feed capture framework.

**The Project Origin (Why It Exists):**
The project started because every data pipeline needs to solve the same problems: fetching data from external sources (RSS, APIs, files), deduplicating it, tracking when you saw it, and storing it reliably. FeedSpine abstracts these problems into a composable pipeline so you never have to write this boilerplate again. The key insight: **the same content seen from 3 different feeds should be 1 record with 3 sightings** - not 3 duplicates.

**Core Principles (use in Manifesto sections):**
1. **Medallion Architecture** - Bronze (raw) → Silver (clean) → Gold (curated)
2. **Data Archetypes** - Observations, Events, Entities, Documents, Prices (each needs different handling)
3. **Storage-agnostic** - Swap Memory/SQLite/DuckDB/PostgreSQL without code changes
4. **Natural key deduplication** - Same content from 3 feeds = 1 record with 3 sightings
5. **Composition operators** - Fluent pipeline API (filter, enrich, transform, dedupe)

### Extended Docstring Format

```python
class ClassName:
    """
    One-line summary.
    
    Extended description (2-3 sentences).
    
    Manifesto:
        Why this class exists. Reference medallion architecture.
        Explain storage-agnostic design if applicable.
    
    Architecture:
        ```
        External Feed → FeedAdapter → Pipeline → Storage
        ```
        Data Tier: Bronze/Silver/Gold
        Deduplication: By natural key
    
    Features:
        - Feature 1
        - Feature 2
    
    Examples:
        >>> adapter = ClassName(url="...")
        >>> records = await adapter.fetch()
    
    Performance:
        - Fetch: ~Xms (network-bound)
        - Parse: ~Xms per 100 records
    
    Guardrails:
        - Do NOT skip bronze layer
          ✅ Instead: Always preserve raw data first
    
    Tags:
        - adapter_pattern
        - medallion
    
    Doc-Types:
        - MANIFESTO (section: "Data Quality", priority: 9)
        - FEATURES (section: "Adapters", priority: 10)
    """
```

### Files to Annotate (Feature-Based + Chronological Order)

**Selection methodology**: Organized by feature importance, following the project's evolution from initial commit through later additions.

---

## 🔴 PHASE 1: THE PIPELINE - The Core Abstraction (Initial Commit - Do First)

*The pipeline is FeedSpine's fundamental insight: External Feed → Adapter → Pipeline → Storage*

| Order | File | Classes | Why First |
|-------|------|---------|-----------|
| 1 | `pipeline.py` | Pipeline, ProcessResult, PipelineStats | **THE CORE** - composable feed processing (filter → enrich → transform → store) |
| 2 | `core/feedspine.py` | FeedSpine | **THE ORCHESTRATOR** - coordinates adapters, pipelines, storage |
| 3 | `core/config.py` | FeedSpineConfig | Global configuration |
| 4 | `core/checkpoint.py` | Checkpoint, CheckpointManager | Resume interrupted feeds |

---

## 🟠 PHASE 2: ADAPTERS - Data Ingestion (Initial Commit Files)

*Adapters fetch data from external sources - the "bronze layer" entry point*

| Order | File | Classes | Why This Order |
|-------|------|---------|----------------|
| 5 | `adapter/base.py` | FeedAdapter, BaseFeedAdapter | **THE PROTOCOL** - all adapters implement this |
| 6 | `adapter/rss.py` | RSSFeedAdapter | Most common use case - RSS/Atom feeds |
| 7 | `adapter/json.py` | JSONFeedAdapter | JSON API endpoints |
| 8 | `adapter/file.py` | FileFeedAdapter | Local file ingestion |
| 9 | `adapter/polygon_earnings.py` | PolygonEarningsAdapter | **REAL-WORLD** - Polygon.io earnings API |
| 10 | `adapter/copilot_chat.py` | CopilotChatAdapter | **INTEGRATION** - Copilot chat session ingestion |

---

## 🟡 PHASE 3: PROTOCOLS - The Contracts (Initial Commit)

*Protocols define what each component must do - enables swappability*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 11 | `protocols/storage.py` | StorageBackend | **STORAGE CONTRACT** - what all storage backends implement |
| 12 | `protocols/feed.py` | Feed | Feed protocol |
| 13 | `protocols/enricher.py` | Enricher | Enricher protocol |
| 14 | `protocols/executor.py` | Executor | Execution strategy protocol |
| 15 | `protocols/cache.py` | Cache | Caching protocol |
| 16 | `protocols/queue.py` | Queue | Queue protocol |

---

## 🟢 PHASE 4: STORAGE BACKENDS - Where Data Lives

*Storage-agnostic design: same code, swap storage with config*

| Order | File | Classes | Storage Tier |
|-------|------|---------|--------------|
| 17 | `storage/memory.py` | MemoryStorage | **TESTING** - in-memory, no persistence |
| 18 | `storage/sqlite.py` | SQLiteStorage | **DEV/SMALL** - single-file database |
| 19 | `storage/duckdb.py` | DuckDBStorage | **ANALYTICS** - columnar, fast aggregations |
| 20 | `storage/postgres.py` | PostgresStorage | **PRODUCTION** - full-featured RDBMS |
| 21 | `storage/backends/sqlite.py` | SqliteBackend (modular) | Refactored SQLite |
| 22 | `storage/backends/postgres.py` | PostgresBackend (modular) | Refactored Postgres |

---

## 🔵 PHASE 5: DATA MODELS - Records, Sightings, Content

*The data structures that flow through pipelines*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 23 | `models/record.py` | FeedRecord | **THE RECORD** - deduplicated content unit |
| 24 | `models/sighting.py` | Sighting | **THE LINEAGE** - when/where content was seen |
| 25 | `models/content.py` | Content, ContentType | Content with type detection |
| 26 | `models/observation.py` | Observation | Time-series observations |
| 27 | `models/query.py` | Query, QueryResult | Query interface |
| 28 | `models/feed_run.py` | FeedRun, RunStatus | Feed execution tracking |

---

## 🟣 PHASE 6: COMPOSITION - Fluent Pipeline API

*The operator pattern that makes pipelines composable*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 29 | `composition/feed.py` | ComposableFeed | Fluent feed builder |
| 30 | `composition/ops.py` | FilterOp, MapOp, EnrichOp | Pipeline operators |
| 31 | `composition/config.py` | CompositionConfig | Configuration for composition |
| 32 | `composition/preset.py` | Preset, PresetRegistry | Reusable pipeline templates |

---

## ⚪ PHASE 7: SUPPORTING INFRASTRUCTURE

*HTTP clients, caching, enrichers, metrics*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 33 | `http/client.py` | HttpClient | HTTP fetching with retries |
| 34 | `http/rate_limiter.py` | RateLimiter | Rate limiting |
| 35 | `cache/memory.py` | MemoryCache | In-memory caching |
| 36 | `enricher/metadata.py` | MetadataEnricher | Add metadata to records |
| 37 | `enricher/entity_enricher.py` | EntityEnricher | **INTEGRATION** - EntitySpine entity resolution |
| 38 | `metrics/collector.py` | MetricsCollector | Pipeline metrics |
| 39 | `discovery.py` | FeedDiscovery | Auto-discover feeds |

---

### Workflow

**Work in PHASES, not random files:**
1. Complete Phase 1 entirely (4 files) - this is the core pipeline
2. Complete Phase 2 entirely (6 files) - data ingestion adapters
3. Then proceed to Phase 3, 4, etc.

For each file:
1. Read the entire source file
2. Add extended docstrings to **all public classes**
3. Ensure Manifesto references the feature's purpose in FeedSpine's evolution

### Quality Checklist (per phase)
- [ ] All classes in the phase are annotated
- [ ] Manifesto explains medallion architecture relevance
- [ ] Architecture shows data flow (External → Adapter → Pipeline → Storage)
- [ ] Examples demonstrate the feature's use case

### Start Now

**Begin with Phase 1, File 1: `pipeline.py`** - the composable pipeline that started it all. This file defines how feeds are processed: fetch → filter → enrich → transform → store.

---

**When done with each phase, report progress before continuing.**
