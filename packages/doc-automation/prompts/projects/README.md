# 📚 Project-Specific Annotation Guides

**Turnkey guides for annotating code classes in each Spine ecosystem project**

---

## 🎯 Purpose

This directory contains **project-specific annotation guides** that provide:

1. **Project Context** - Philosophy, principles, key concepts
2. **Classes to Annotate** - Prioritized lists (Tier 1/2/3)
3. **Project-Specific Guidelines** - What to emphasize in each section
4. **Reference Documents** - Must-read docs before annotating
5. **Example Annotated Classes** - Full templates with project context
6. **Validation Checklists** - Quality gates before submission

Each guide is **turnkey** - you can send it to an LLM with source files and it will annotate autonomously.

---

## 📋 Available Guides

### **1. EntitySpine** - Master Data & Entity Resolution
[ENTITYSPINE_ANNOTATION_GUIDE.md](ENTITYSPINE_ANNOTATION_GUIDE.md)

**Key Concepts:**
- Entity ≠ Security ≠ Listing (separation of concerns)
- Claims-based identity (competing identifiers)
- Tiered storage (T0: JSON → T3: PostgreSQL)
- Stdlib-only domain models
- Result[T] pattern (Ok/Err) for error handling

**Priority Classes (Tier 1 - 15 classes):**
- **Core Primitives:** `Ok`, `Err`, `ExecutionContext` (Result[T] monad)
- **Domain Models:** `Entity`, `Security`, `Listing`, `IdentifierClaim`, `Relationship`, `Observation`
- **Services:** `EntityResolver`, `GraphService`, `FuzzyMatcher`
- **Stores:** `JsonEntityStore`, `SqliteStore`

**Tier 2 Highlights:** Graph models (`NodeKind`, `PersonRole`), Loaders (`SecDataLoader`), Sources (`LEISnapshot`)

**Tags:** `entity_resolution`, `master_data`, `knowledge_graph`, `claims_based_identity`, `result_type`

---

### **2. FeedSpine** - Feed Capture & Data Pipelines
[FEEDSPINE_ANNOTATION_GUIDE.md](FEEDSPINE_ANNOTATION_GUIDE.md)

**Key Concepts:**
- Medallion architecture (Bronze → Silver → Gold)
- Data archetypes (Observations, Events, Entities, Documents, Prices)
- Storage-agnostic design
- Deduplication by natural key
- Sighting history
- Composition operators (fluent pipeline API)

**Priority Classes (Tier 1 - 15 classes):**
- **Core:** `Pipeline`, `ProcessResult`, `FeedSpine`, `CollectionResult`
- **Adapters:** `FeedAdapter`, `BaseFeedAdapter`, `RSSFeedAdapter`, `JSONFeedAdapter`, `FileFeedAdapter`
- **Storage:** `StorageBackend`, `MemoryStorage`, `SQLiteStorage`, `DuckDBStorage`, `PostgresStorage`

**Tier 2 Highlights:** Composition operators (`FilterOp`, `EnrichOp`, `TransformOp`), Earnings service (`EarningsCalendarService`)

**Tags:** `adapter_pattern`, `medallion`, `deduplication`, `observations`, `composition_operators`

**Must Read:** `DATA_ARCHETYPES_GUIDE.md`

---

### **3. GenAI-Spine** - LLM Service & Prompt Management
[GENAI_SPINE_ANNOTATION_GUIDE.md](GENAI_SPINE_ANNOTATION_GUIDE.md)

**Key Concepts:**
- Provider-agnostic (Ollama, OpenAI, Anthropic)
- OpenAI-compatible API
- Cost tracking built-in
- Prompt management (CRUD, versioning, templates)
- Ecosystem integration (Result[T], ExecutionContext)

**Priority Classes (Tier 1 - 15 classes):**
- **🔴 Providers (CRITICAL):** `LLMProvider` (ABC), `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `ProviderRegistry`
- **Settings:** `Settings`
- **API Models:** `ChatCompletionRequest/Response`, `SummarizeRequest/Response`, `ExtractRequest/Response`, `ClassifyRequest/Response`
- **Prompts:** `PromptCreateRequest/Response`
- **Usage:** `UsageResponse`

**Tier 2 Highlights:** Storage layer (`Prompt`, `PromptVersion`, `Execution`), Repository protocols

**Tags:** `provider_agnostic`, `openai_compatible`, `capability`, `prompt_management`, `cost_tracking`

**Must Read:** `ECOSYSTEM_INTEGRATION.md`

---

### **4. Capture-Spine** - Point-in-Time Content Capture
[CAPTURE_SPINE_ANNOTATION_GUIDE.md](CAPTURE_SPINE_ANNOTATION_GUIDE.md)

**Key Concepts:**
- Point-in-time accuracy ("what was visible at 2:30pm?")
- Feed → Item → Record → Sighting data model
- Content deduplication with sighting lineage
- Multi-backend search (PostgreSQL + Elasticsearch)
- Execution ledger for background jobs
- Container-based dependency injection
- Modular domains/features architecture

**Priority Classes (Tier 1 - 15 classes):**
- **🔴 Container:** `Container` (DI - wires all services)
- **Settings:** `Settings`, `DeploymentTier`
- **Domain Models:** `FeedBase/Read`, `ItemCreate/Read`, `RecordCreate/Read`, `SightingCreate/Read`, `RunMetadata`, `SystemStatus`
- **Services:** `SearchService`, `PollerService`, `ParserService`, `WorkSessionService`, `ChatSessionService`

**Tier 2 Highlights:** Domains layer, Features layer, 15+ API route modules

**Tags:** `point_in_time`, `lineage`, `sighting_history`, `container_di`, `domains_architecture`

**Must Read:** `RESTRUCTURE_COMPLETE.md` (god class refactoring context)

---

### **5. Market-Spine** - Market Data & Trading Analytics
[MARKET_SPINE_ANNOTATION_GUIDE.md](MARKET_SPINE_ANNOTATION_GUIDE.md)

**Status:** ⚠️ Early Development

**Key Concepts:**
- Market data as data archetype (high-frequency, time-series)
- Separation of market data vs trading logic
- Integration with EntitySpine (symbol resolution)
- Time-series storage (TimescaleDB)
- Reuse patterns from sibling projects

**Priority Classes** (when created):
- Price, Quote, Trade, Bar (OHLCV)
- MarketDataService, SymbolResolutionService
- PortfolioService, AnalyticsService

**Recommended:** Reuse `Result[T]` from EntitySpine, storage protocols from FeedSpine, `Container` pattern from Capture-Spine

**Tags:** `market_data`, `time_series`, `symbol_resolution`, `timescaledb`

**Must Read:** FeedSpine `DATA_ARCHETYPES_GUIDE.md` (Prices archetype)

---

### **6. Spine-Core** - Framework Primitives
[SPINE_CORE_ANNOTATION_GUIDE.md](SPINE_CORE_ANNOTATION_GUIDE.md)

**Key Concepts:**
- Registry-driven architecture (discover components at runtime)
- Capture semantics (append-only, audit trail)
- Quality gates (validation, anomaly detection)
- Domain isolation (shared primitives, independent packages)

**⚠️ Note:** Core primitives (`Result[T]`, `Ok`, `Err`, `ExecutionContext`) are **currently defined in EntitySpine** (`domain/workflow.py`). They will be factored out to spine-core as the canonical source.

**Priority Classes:**
- Core Primitives: `Ok[T]`, `Err`, `ExecutionContext`, `ErrorCategory` (currently in EntitySpine)
- Framework: `Registry`, `Dispatcher` (to be created)
- Base Classes: `BaseAdapter`, `BaseProcessor`, `BaseStore` (to be created)
- Quality: `Validator`, `AnomalyDetector`, `QualityScorer` (to be created)

**Tags:** `core_primitive`, `registry`, `dispatcher`, `framework`, `domain_isolation`

**Note:** Foundation for ALL domain packages - get these right!

---

## 🔧 How to Use These Guides

### Step 1: Choose a Project

Pick a guide based on which project you're annotating:
- Annotating EntitySpine? → [ENTITYSPINE_ANNOTATION_GUIDE.md](ENTITYSPINE_ANNOTATION_GUIDE.md)
- Annotating FeedSpine? → [FEEDSPINE_ANNOTATION_GUIDE.md](FEEDSPINE_ANNOTATION_GUIDE.md)
- etc.

### Step 2: Read the Guide

Spend 10-15 minutes reading:
- **Project Context** (understand philosophy)
- **Classes to Annotate** (see Tier 1 priorities)
- **Project-Specific Guidelines** (know what to emphasize)
- **Example Annotated Class** (see full template)

### Step 3: Read Reference Docs

Each guide lists "Must Read" documents:
- Project README
- Architecture docs
- Design docs (ADRs, data models)

### Step 4: Pick a Tier 1 Class

Start with ONE Tier 1 class from the guide:
- EntitySpine: Start with `Entity` or `EntityResolver`
- FeedSpine: Start with `FeedAdapter` or `Pipeline`
- GenAI-Spine: Start with `SummarizeRequest`
- Capture-Spine: Start with `SightingCreate` or `FeedBase`

### Step 5: Annotate

Use the full extended docstring format from [../EXTENDED_ANNOTATION_PROMPT.md](../EXTENDED_ANNOTATION_PROMPT.md):
- Copy the template
- Fill in project-specific details
- Use the guide's examples as reference
- Follow the project-specific guidelines

### Step 6: Validate

Run validation checks:
```bash
docbuilder validate <file>
```

Check against the guide's validation checklist.

### Step 7: Review & Iterate

Submit for review before batch-annotating other classes.

---

## 📊 Annotation Progress Tracking

| Project | Tier 1 Classes | Tier 2 Classes | Tier 3 Classes | Status |
|---------|----------------|----------------|----------------|--------|
| EntitySpine | 10 | 15 | 30+ | 🔴 Not Started |
| FeedSpine | 12 | 15 | 30+ | 🔴 Not Started |
| GenAI-Spine | 10 | 15 | 30+ | 🔴 Not Started |
| Capture-Spine | 12 | 15 | 50+ | 🔴 Not Started |
| Market-Spine | 8 | 10 | 20+ | 🔴 Not Started |
| Spine-Core | 10 | 10 | 20+ | 🔴 Not Started |

**Legend:**
- 🔴 Not Started
- 🟡 In Progress (Tier 1)
- 🟢 Tier 1 Complete
- ✅ All Tiers Complete

---

## 🎓 Learning Path

If you're new to the Spine ecosystem, follow this order:

1. **Start with Spine-Core** - Understand shared primitives (Result[T], ExecutionContext)
2. **Then EntitySpine** - Master data layer, entity resolution
3. **Then FeedSpine** - Feed capture, medallion architecture, data archetypes
4. **Then GenAI-Spine** - LLM capabilities, provider abstraction
5. **Then Capture-Spine** - Point-in-time capture, lineage tracking
6. **Finally Market-Spine** - Time-series data, trading analytics

---

## 📝 Quick Reference

### Common Tags Across Projects

**Architectural:**
- `core_concept`, `core_primitive`, `base_class`, `protocol`, `abstraction`
- `adapter_pattern`, `template_method`, `registry`, `dispatcher`

**Data Management:**
- `deduplication`, `lineage`, `sighting_history`, `point_in_time`, `audit_trail`
- `bronze_tier`, `silver_tier`, `gold_tier`, `medallion`

**Storage:**
- `storage`, `sqlite`, `duckdb`, `postgresql`, `timescaledb`, `elasticsearch`
- `in_memory`, `persistent`, `content_addressed`

**Integration:**
- `entity_resolution`, `master_data`, `knowledge_graph`
- `ecosystem_integration`, `result_type`, `execution_context`

### Common Doc-Types

- **MANIFESTO** - Core principles, philosophy
- **FEATURES** - Capabilities, what it does
- **ARCHITECTURE** - System design, data flow
- **CORE_PRIMITIVES** - Fundamental building blocks
- **UNIFIED_DATA_MODEL** - Cross-project data model
- **GUARDRAILS** - Common mistakes, best practices
- **API_REFERENCE** - Public API documentation

---

## 🚀 Getting Started

**Never annotated before?** Start here:

1. Read [../EXTENDED_ANNOTATION_PROMPT.md](../EXTENDED_ANNOTATION_PROMPT.md) (25 KB, comprehensive format)
2. Read [SPINE_CORE_ANNOTATION_GUIDE.md](SPINE_CORE_ANNOTATION_GUIDE.md) (foundation)
3. Pick ONE class from Tier 1 (Result[T] is a good start)
4. Annotate using the template
5. Validate and review
6. Move to next project

**Already familiar with annotation format?** Jump straight to project guides!

---

## 💡 Tips for Success

### Do's ✅
- **DO** read the entire guide before starting
- **DO** read the "Must Read" reference docs
- **DO** start with ONE Tier 1 class
- **DO** use the example as a template
- **DO** validate before batch-annotating
- **DO** ask for review early

### Don'ts ❌
- **DON'T** skip the project context section
- **DON'T** batch-annotate without validating one first
- **DON'T** ignore the project-specific guidelines
- **DON'T** copy-paste examples without adapting
- **DON'T** skip reference docs (especially for unfamiliar projects)

---

## 📖 Additional Resources

### General Annotation
- [../EXTENDED_ANNOTATION_PROMPT.md](../EXTENDED_ANNOTATION_PROMPT.md) - Complete annotation format
- [../IMPLEMENTATION_PROMPT.md](../IMPLEMENTATION_PROMPT.md) - System implementation guide
- [../VALIDATION_PROMPT.md](../VALIDATION_PROMPT.md) - Validation strategy

### Architecture & Design
- [../../design/KNOWLEDGE_GRAPH_DOCUMENTATION.md](../../design/KNOWLEDGE_GRAPH_DOCUMENTATION.md) - EntitySpine-based knowledge graph

### Reference
- [../../README.md](../../README.md) - Doc-automation package overview
- [../../TRACKER.md](../../TRACKER.md) - 12-month implementation roadmap

---

**Ready to start annotating? Pick a guide and dive in!** 🎯
