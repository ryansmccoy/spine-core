# 📋 COPY-PASTE PROMPT: Annotate Capture-Spine Classes

**Copy everything below and send to an LLM with file editing access:**

---

## TASK: Add Extended Docstrings to Capture-Spine Classes

You are a documentation automation agent. Add rich extended docstrings to Python classes in the Capture-Spine project.

### Project Context

**Capture-Spine** is a point-in-time content capture system with full lineage tracking.

**The Project Origin (Why It Exists):**
The project started because financial analysis requires knowing **what information was available at a specific moment**. When analyzing a trade decision, you need to know "What did the RSS feed show at 2:30pm yesterday?" - not what it shows now. Capture-Spine preserves point-in-time snapshots with full lineage: the same content from 3 feeds = 1 record with 3 sightings, each with a timestamp. This evolved from a simple feed aggregator (Dec 2025) into a full-featured knowledge management system with search, LLM integration, and multi-user RBAC.

**Core Principles (use in Manifesto sections):**
1. **Point-in-time accuracy** - "What was visible at 2:30pm yesterday?"
2. **Feed → Item → Record → Sighting** - Hierarchical data model
3. **Content deduplication** - Same content = one record with multiple sightings
4. **Container DI** - Dependency injection for testability and flexibility
5. **Modular architecture** - Domains layer + Features layer

### Extended Docstring Format

```python
class ClassName:
    """
    One-line summary.
    
    Extended description (2-3 sentences).
    
    Manifesto:
        Why this class exists. Reference point-in-time accuracy.
        Explain sighting lineage if applicable.
    
    Architecture:
        ```
        Feed → Item (bronze) → Record (deduped) → Sighting (lineage)
        ```
        Dependency Injection: Via Container
        Database: PostgreSQL with full-text search
    
    Features:
        - Feature 1
        - Feature 2
    
    Examples:
        >>> from app.container import Container
        >>> container = Container()
        >>> service = container.service_name
    
    Guardrails:
        - Do NOT mutate Items (bronze tier is immutable)
          ✅ Instead: Create new Record versions
    
    Tags:
        - point_in_time
        - sighting_history
    
    Doc-Types:
        - MANIFESTO (section: "Point-in-Time", priority: 10)
        - ARCHITECTURE (section: "Data Model", priority: 9)
    """
```

### Files to Annotate (Feature-Based + Chronological Order)

**Selection methodology**: Organized by feature importance, following the project's evolution from simple feed capture (Dec 2025) through multi-user RBAC (Jan 2026).

---

## 🔴 PHASE 1: CORE DATA MODEL - Feed → Item → Record → Sighting (Do First)

*The fundamental data hierarchy that enables point-in-time accuracy*

| Order | File | Classes | Why First |
|-------|------|---------|-----------|
| 1 | `app/models.py` | FeedBase, FeedRead, ItemCreate, ItemRead, RecordCreate, RecordRead, SightingCreate, SightingRead (15 classes) | **THE DATA MODEL** - the core hierarchy |
| 2 | `app/container.py` | Container | **THE DI CONTAINER** - wires all services together |
| 3 | `app/settings.py` | Settings, DeploymentTier | Global configuration |

---

## 🟠 PHASE 2: CORE INFRASTRUCTURE - Database & Config (Initial Dec 2025)

*The foundational infrastructure from the initial commit*

| Order | File | Classes | Why This Order |
|-------|------|---------|----------------|
| 4 | `app/db/session.py` | get_db, SessionManager | Database session management |
| 5 | `app/db/models.py` | Feed, Item, Record, Sighting (SQLAlchemy) | ORM models |
| 6 | `app/core/identity.py` | IdentityService, ContentHasher | **DEDUPLICATION** - same content = one record |
| 7 | `app/core/exceptions.py` | AppException, NotFoundError | Exception hierarchy |

---

## 🟡 PHASE 3: FEATURES LAYER - The Big Functionality Blocks

*Capture-Spine's features layer - each is a self-contained module*

| Order | File | Classes (count) | Feature Added |
|-------|------|-----------------|---------------|
| 8 | `app/features/search/models.py` | SearchQuery, SearchResult, etc (28) | **SEARCH** - Elasticsearch full-text (Jan 11) |
| 9 | `app/features/search/service.py` | SearchService | Search service |
| 10 | `app/features/intelligence/models.py` | IntelligenceReport, etc (24) | **INTELLIGENCE** - AI-powered analysis |
| 11 | `app/features/batch_ingestion/models.py` | BatchJob, BatchStatus, etc (27) | **BATCH** - bulk content ingestion |
| 12 | `app/features/work_sessions/models.py` | WorkSession, etc (32) | **WORK SESSIONS** - activity tracking (Jan 31) |
| 13 | `app/features/chat_session/models.py` | ChatSession, etc (14) | **CHAT** - Copilot session ingestion (Jan 31) |
| 14 | `app/features/document_ingestion/models.py` | Document, etc (12) | **DOCUMENTS** - local file ingestion (Jan 11) |
| 15 | `app/features/security/models.py` | User, Role, Permission (19) | **SECURITY** - multi-user RBAC (Jan 12) |

---

## 🟢 PHASE 4: API ROUTERS - FastAPI Endpoints

*REST API that exposes all functionality*

| Order | File | Classes | Endpoint |
|-------|------|---------|----------|
| 16 | `app/api/routers/ingest/models.py` | IngestRequest, IngestResponse (20) | `/api/v1/ingest` - content ingestion |
| 17 | `app/api/routers/content/models.py` | ContentQuery, ContentResponse (20) | `/api/v1/content` - content retrieval |
| 18 | `app/api/routers/knowledge/models.py` | KnowledgeItem, etc (20) | `/api/v1/knowledge` - knowledge layer |
| 19 | `app/api/routers/llm/models.py` | LLMRequest, LLMResponse (23) | `/api/v1/llm` - GenAI-Spine integration |
| 20 | `app/api/routers/ops/models.py` | OpsStatus, etc (21) | `/api/v1/ops` - operational status |
| 21 | `app/api/routers/archive.py` | ArchiveJob, etc (13) | `/api/v1/archive` - archival operations |

---

## 🔵 PHASE 5: LLM INTEGRATION - AI Capabilities

*GenAI-Spine integration for LLM-powered features*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 22 | `app/llm/types.py` | LLMMessage, LLMResponse (15) | LLM type definitions |
| 23 | `app/features/llm_transform/models.py` | TransformRequest, etc (20) | LLM-based content transformation |
| 24 | `app/features/recommendations/models.py` | Recommendation, etc (15) | "For You" recommendations (Jan 16) |

---

## 🟣 PHASE 6: SUPPORTING INFRASTRUCTURE

*Alerting, monitoring, runtime config*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 25 | `app/features/alerts/rules_models.py` | AlertRule, AlertTrigger (13) | Alert rules engine |
| 26 | `app/features/dev_feature/models.py` | FeatureFlag, etc (17) | Feature flags (Jan 11) |
| 27 | `app/features/organization/models.py` | Organization, Team (17) | Multi-tenant organization |
| 28 | `app/runtime/feature_flags.py` | FeatureManager | Runtime feature management |
| 29 | `app/observability/metrics.py` | MetricsCollector | Prometheus metrics |

---

### Workflow

**Work in PHASES, not random files:**
1. Complete Phase 1 entirely (3 files) - the core data model
2. Complete Phase 2 entirely (4 files) - database infrastructure
3. Then proceed to Phase 3, 4, etc.

For each file:
1. Read the entire source file
2. Add extended docstrings to **all public classes**
3. Ensure Manifesto references point-in-time accuracy and sighting lineage

### Quality Checklist (per phase)
- [ ] All classes in the phase are annotated
- [ ] Manifesto explains Feed → Item → Record → Sighting hierarchy
- [ ] Architecture shows data flow and DI container usage
- [ ] Examples show Container-based dependency injection

### Start Now

**Begin with Phase 1, File 1: `app/models.py`** - the Pydantic models that define Feed, Item, Record, and Sighting. This is THE data model that enables point-in-time queries.

---

**When done with each phase, report progress before continuing.**
