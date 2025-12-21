"""Spine Suite — Core Principles (P001–P020).

Documentation carrier module. Content is extracted by document-spine
and rendered into PRINCIPLES.md.

Every principle is grounded in docstrings, manifestos, or code comments
from the repositories. Citations link to the actual source file.

Manifesto:
    ## Core Principles (Suite-Wide)

    ### P001 — Protocol-First Design

    **Why:** Decouple contracts from implementations so backends, adapters, and runners can be swapped without touching domain logic.

    **How it shows up:** Every subsystem defines a ``Protocol`` (PEP 544 structural typing) before any concrete class. Storage, execution, enrichment, search, scheduling, and LLM all follow this rule.

    **Evidence:**
    - ``spine-core/src/spine/core/protocols.py`` — *"Protocols define contracts without inheritance."*
    - ``feedspine/docs/MANIFESTO.md`` — Principle #5: *"All components defined by protocols."*
    - ``entityspine/docs/MANIFESTO.md`` — Principle #4 (Tiered Storage) defines tier-based backends.

    ---

    ### P002 — Zero Required Dependencies

    **Why:** Minimal attack surface, fast startup, easy auditing, and installable in restricted environments (air-gapped financial systems).

    **How it shows up:** Core domain models use only ``dataclasses``, ``sqlite3``, ``typing``, and stdlib. Heavy drivers (PostgreSQL, DuckDB, Redis, Neo4j) are **optional extras** loaded via import guards.

    **Evidence:**
    - ``entityspine/docs/MANIFESTO.md`` — Principle #1: *"stdlib only."*
    - ``spine-core/src/spine/core/__init__.py`` — *"import-guarded extras (never crashes on import)"*
    - ``spine-core/src/spine/core/assets.py`` — *"stdlib-only: No external dependencies."*

    ---

    ### P003 — Explicit over Implicit

    **Why:** Financial data demands auditability. Silent failures, hidden state, and magic behaviour undermine trust.

    **How it shows up:** ``Result[T]`` monad forces callers to check success. Typed error hierarchy with ``ErrorCategory``. Idempotency level is declared, not guessed.

    **Evidence:**
    - ``spine-core/src/spine/core/result.py`` — *"Explicit over Implicit — Callers must check success before accessing the value."*
    - ``spine-core/src/spine/core/temporal.py`` — *"Making Fridays a type, not a convention."*
    - ``spine-core/src/spine/core/idempotency.py`` — *"Explicitly declaring level documents behavior."*

    ---

    ### P004 — Errors Never Pass Silently

    **Why:** Swallowed exceptions in data pipelines lead to corrupt data and broken audits. Every failure must be captured, classified, and traceable.

    **How it shows up:** Typed ``SpineError`` hierarchy with category, retryable flag, and chained cause. Reject records are **never deleted**. Anomaly records are **never deleted**.

    **Evidence:**
    - ``spine-core/src/spine/core/errors.py`` — *"Typed Error Hierarchy — Every error has a category."*
    - ``spine-core/src/spine/core/rejects.py`` — *"Rejects are NEVER deleted."*
    - ``spine-core/src/spine/core/anomalies.py`` — *"Anomalies are NEVER deleted."*

    ---

    ### P005 — Tiered Architecture (Start Simple, Scale When Needed)

    **Why:** Not every user needs PostgreSQL on day one. A researcher should be able to ``pip install`` and start working with SQLite; a team can graduate to PostgreSQL.

    **How it shows up:** Every repository defines explicit tiers. Storage, execution, search, and caching all have in-memory/SQLite implementations at Tier 0–1 and advanced backends at higher tiers. The **same API** works at every tier.

    **Evidence:**
    - ``entityspine/docs/MANIFESTO.md`` — Principle #4: *"Tier 0 JSON → Tier 1 SQLite → Tier 2 DuckDB → Tier 3 PostgreSQL. Same API, different scale."*
    - ``spine-core/src/spine/core/cache.py`` — *"Tier 1: InMemoryCache / Tier 2/3: RedisCache."*

    ---

    ### P006 — Immutable Audit Trail

    **Why:** Financial compliance requires knowing what happened, when, why, and who authorized it.

    **How it shows up:** Rejects, anomalies, execution events, sightings, merge events, and corrections are append-only. Merged entities become redirects (never deleted).

    **Evidence:**
    - ``spine-core/src/spine/core/rejects.py`` — *"A reject row is an immutable audit record."*
    - ``spine-core/src/spine/execution/events.py`` — *"Events are append-only; never update or delete."*
    - ``spine-core/src/spine/core/finance/corrections.py`` — *"Never silently overwrite."*

    ---

    ### P007 — Schema Ownership (Write Once, Partition by Domain)

    **Why:** Multiple spines share the same database. Shared tables with a ``domain_name`` partition column eliminate duplication while preserving isolation.

    **How it shows up:** 8 shared ``core_*`` tables defined once in spine-core, used by all consumers.

    **Evidence:**
    - ``spine-core/src/spine/core/schema.py`` — *"Shared infrastructure tables partitioned by domain."*
    - ``spine-core/src/spine/core/quality.py`` — writes to shared ``core_quality`` (partitioned by ``domain_name``).

    ---

    ### P008 — Sync-Only Domain Primitives

    **Why:** Domain logic should not deal with async complexity. The same ``execute()`` call works on SQLite (inherently sync) and PostgreSQL (optionally async).

    **How it shows up:** All ``Connection``, ``StorageBackend``, and ``Repository`` protocols are synchronous. Async PostgreSQL is wrapped in ``SAConnectionBridge``.

    **Evidence:**
    - ``spine-core/src/spine/core/__init__.py`` — *"Sync-only primitives."*
    - ``spine-core/src/spine/core/storage.py`` — *"SYNC-ONLY protocols."*

    ---

    ### P009 — Natural Key Deduplication

    **Why:** Financial feeds are noisy — the same filing appears in RSS, API, and bulk downloads. Processing it 100 times wastes compute.

    **How it shows up:** FeedSpine uses ``hash(source, record_type, content_id)`` for dedup. spine-core provides three idempotency levels.

    **Evidence:**
    - ``feedspine/docs/MANIFESTO.md`` — Principle #2: *"Natural Key Deduplication."*
    - ``spine-core/src/spine/core/idempotency.py`` — *"L2_INPUT — Hash-based dedup, skip if exists."*
    - ``spine-core/src/spine/core/hashing.py`` — *"Deterministic: Same inputs → same output."*

    ---

    ### P010 — Canonical Domain Models (Pydantic at the Edges)

    **Why:** Domain logic should be expressed in plain Python dataclasses that are fast, serializable, and free of framework coupling.

    **How it shows up:** ``Entity``, ``Security``, ``Listing``, ``Workflow``, ``Step``, ``StepResult`` are all frozen dataclasses. Pydantic schemas exist in ``adapters/pydantic/`` only.

    **Evidence:**
    - ``entityspine/docs/MANIFESTO.md`` — Principle #2: *"All business logic in entityspine.domain."*
    - ``spine-core/src/spine/core/models/__init__.py`` — *"All models use dataclasses.dataclass."*

    ---

    ### P011 — Composability (Small Units, Functional Operators)

    **Why:** Complex workflows should be built by combining simple, testable primitives — not by subclassing a god-class.

    **How it shows up:** spine-core provides ``chain()``, ``parallel()``, ``conditional()``, ``retry()``, ``merge_workflows()``.

    **Evidence:**
    - ``spine-core/src/spine/orchestration/composition.py`` — 5 operators
    - ``spine-core/src/spine/orchestration/templates.py`` — ``etl_pipeline``, ``fan_out_fan_in``

    ---

    ### P012 — Blueprint Declares What, Runner Decides How

    **Why:** Separating definition from execution enables dry runs, linting, visualization, recording, and replay.

    **How it shows up:** ``Workflow`` is a frozen dataclass. ``WorkflowRunner`` executes it. ``DryRunExecutor`` previews it. ``WorkflowLinter`` validates it. ``WorkflowVisualizer`` renders it.

    **Evidence:**
    - ``spine-core/src/spine/orchestration/workflow.py`` — *"Blueprint declares WHAT, not HOW."*
    - ``spine-core/src/spine/orchestration/dry_run.py`` — preview without side effects.

    ---

    ### P013 — Every Operation Gets an Identity

    **Why:** Correlation across distributed systems requires unique, sortable identifiers.

    **How it shows up:** ULIDs everywhere — ``execution_id``, ``run_id``, ``anomaly_id``, ``reject_id``. Parent-child linking for sub-executions.

    **Evidence:**
    - ``spine-core/src/spine/core/execution.py`` — *"Every execution gets an ID."*
    - ``spine-core/src/spine/core/timestamps.py`` — ``generate_ulid()`` for sortable unique IDs.

    ---

    ### P014 — Identifiers Are Claims, Not Facts

    **Why:** In financial data, the same entity may have different identifiers from different vendors.

    **How it shows up:** EntitySpine's ``IdentifierClaim`` attaches ``confidence``, ``source``, ``captured_at``, and ``valid_from/valid_to`` to every identifier assertion. Resolution produces ranked candidates, not a single answer.

    **Evidence:**
    - ``entityspine/src/entityspine/domain/claim.py`` — *"Identifiers are NOT facts."*
    - ``entityspine/docs/MANIFESTO.md`` — Principle #3: *"Every identifier is a claim with confidence."*

    ---

    ### P015 — Tier Capability Honesty

    **Why:** When a feature is unavailable at a given tier, the system must warn — not silently skip.

    **How it shows up:** ``ResolutionResult`` includes ``warnings[]`` when requested features exceed tier capabilities.

    **Evidence:**
    - ``entityspine/src/entityspine/domain/resolution.py`` — *"When unavailable, warnings are added (not silent failures)."*

    ---

    ### P016 — Medallion Architecture (Bronze → Silver → Gold)

    **Why:** Raw data is messy. Layered quality ensures downstream consumers trust what they read.

    **How it shows up:** FeedSpine's ``Layer`` enum (BRONZE/SILVER/GOLD). EntitySpine's Bronze/Silver/Gold source data architecture.

    **Evidence:**
    - ``feedspine/docs/MANIFESTO.md`` — Principle #4: *"Bronze (raw) → Silver (cleaned) → Gold (enriched)."*
    - ``feedspine/src/feedspine/models/base.py`` — ``Layer`` enum.

    ---

    ### P017 — Repository Pattern (Dialect-Aware SQL)

    **Why:** Domain logic should not contain raw SQL strings or database-specific syntax.

    **How it shows up:** ``BaseRepository`` pairs a ``Connection`` with a ``Dialect``. Factory helpers (``_xxx_repo(ctx)``) are the canonical instantiation pattern. 14 repository classes in spine-core.

    **Evidence:**
    - ``spine-core/src/spine/core/repository.py`` — ``BaseRepository`` with dialect-aware SQL.
    - ``spine-core/src/spine/core/repositories.py`` — 14 domain repositories.

    ---

    ### P018 — Testable Without Infrastructure

    **Why:** Tests that require PostgreSQL, Redis, or network access are slow and brittle.

    **How it shows up:** ``MemoryStorage``, ``StubExecutor``, ``MockLLMProvider``, ``InMemoryEventBus``. spine-core has 2,670+ tests, all runnable without Docker.

    **Evidence:**
    - ``spine-core/src/spine/orchestration/testing.py`` — ``StubRunnable``, ``ScriptedRunnable``
    - ``feedspine/src/feedspine/storage/memory.py`` — ``MemoryStorage``

    ---

    ### P019 — Entity ≠ Security ≠ Listing

    **Why:** Apple Inc. (entity) issues AAPL Common Stock (security) which trades with ticker AAPL on NASDAQ (listing). Conflating these causes data quality disasters.

    **How it shows up:** Three separate frozen dataclasses with independent lifecycles. Ticker lives on ``Listing`` with temporal validity.

    **Evidence:**
    - ``entityspine/src/entityspine/domain/entity.py`` — *"Entity ≠ Security ≠ Listing."*
    - ``entityspine/src/entityspine/domain/listing.py`` — *"Tickers are NOT entity identifiers."*

    ---

    ### P020 — Decorator Registration + Global Catalog

    **Why:** Adding a new tool/auditor/adapter should be a two-line change.

    **How it shows up:** ``@register_auditor``, ``@register_task``, ``@register_pipeline``. Global catalogs aggregate all registries. spine-tools manages 69+ tools.

    **Evidence:**
    - ``spine-tools/src/spine_tools/audits/registry.py`` — *"Two-line change: subclass + decorator."*
    - ``spine-core/src/spine/execution/registry.py`` — ``@register_task``, ``@register_pipeline``

    ---

    ## Summary Table

    | ID | Principle | Category | Primary Repo |
    |----|-----------|----------|-------------|
    | P001 | Protocol-First Design | Design | All |
    | P002 | Zero Required Dependencies | Design | All |
    | P003 | Explicit over Implicit | Philosophy | spine-core |
    | P004 | Errors Never Pass Silently | Philosophy | spine-core |
    | P005 | Tiered Architecture | Design | All |
    | P006 | Immutable Audit Trail | Constraint | spine-core, entityspine |
    | P007 | Schema Ownership | Design | spine-core |
    | P008 | Sync-Only Domain Primitives | Design | spine-core |
    | P009 | Natural Key Deduplication | Design | feedspine, spine-core |
    | P010 | Canonical Domain Models | Design | entityspine, spine-core |
    | P011 | Composability | Design | spine-core |
    | P012 | Blueprint Declares What | Design | spine-core |
    | P013 | Every Operation Gets an Identity | Constraint | spine-core |
    | P014 | Identifiers Are Claims | Philosophy | entityspine |
    | P015 | Tier Capability Honesty | Philosophy | entityspine |
    | P016 | Medallion Architecture | Design | feedspine, entityspine |
    | P017 | Repository Pattern | Best Practice | spine-core, feedspine |
    | P018 | Testable Without Infrastructure | Design | All |
    | P019 | Entity ≠ Security ≠ Listing | Philosophy | entityspine |
    | P020 | Decorator Registration | Best Practice | spine-tools, spine-core |

Tags: principles, design, philosophy, architecture, core
Doc-Types: PRINCIPLES
"""
