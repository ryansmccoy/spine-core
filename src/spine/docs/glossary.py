"""Spine Suite — Glossary of canonical terminology.

Documentation carrier module. Content is extracted by document-spine
and rendered into GLOSSARY.md.

Manifesto:
    ## A

    **Anomaly** — A non-fatal pipeline issue (quality warning, transient error, format anomaly) recorded in ``core_anomalies``. Has severity, category, and optional resolution. **Never deleted.** *See: spine-core/src/spine/core/anomalies.py*

    **Adapter** — A boundary component that converts between domain models and external representations (Pydantic schemas, ORM tables, API responses). Lives in ``adapters/`` packages. *See: P010 in PRINCIPLES.md*

    **Asset** — A tracked data artifact with hierarchical keys, materialization history, and freshness monitoring. Inspired by Dagster's asset model. *See: spine-core/src/spine/core/assets.py*

    ## B

    **Backfill** — A structured recovery plan for re-processing historical data. Triggered by gaps, corrections, quality failures, or schema changes. Supports checkpoint-based resume. *See: spine-core/src/spine/core/backfill.py*

    **Blueprint** — The data definition of a workflow — steps, policies, dependencies — without any execution logic. Executed by a Runner. *See: P012 in PRINCIPLES.md*

    **Bronze** (Medallion Layer) — Raw, immutable data snapshots with provenance metadata. No transformations applied. *See: P016 in PRINCIPLES.md*

    ## C

    **Claim** → See **IdentifierClaim**

    **Circuit Breaker** — A resilience pattern with three states (CLOSED → OPEN → HALF_OPEN) that prevents repeated calls to failing services. *See: spine-core/src/spine/execution/circuit_breaker.py*

    **Composition Operator** — A function that builds a workflow from smaller parts: ``chain()``, ``parallel()``, ``conditional()``, ``retry()``, ``merge_workflows()``. *See: P011 in PRINCIPLES.md*

    **Connection** — The protocol for database access. Provides ``execute()``, ``fetch_all()``, ``fetch_one()``, ``close()``. Satisfied by SQLite, PostgreSQL, DuckDB drivers. *See: spine-core/src/spine/core/protocols.py*

    ## D

    **Dead Letter Queue (DLQ)** — Storage for work items that failed all retry attempts. Supports inspection and manual re-processing. *See: spine-core/src/spine/execution/dlq.py*

    **Dialect** — An abstraction that translates portable SQL operations into database-specific syntax (e.g., ``INSERT OR IGNORE`` vs ``ON CONFLICT DO NOTHING``). *See: spine-core/src/spine/core/dialect.py*

    **Domain Model** — A frozen dataclass (stdlib only) representing a core business concept. Lives in ``domain/`` packages. No Pydantic, no ORM. *See: P010 in PRINCIPLES.md*

    ## E

    **Entity** — A legal or organizational unit (e.g., Apple Inc., U.S. Treasury). Has a unique ``entity_id``. Does NOT contain ticker or exchange information. *See: entityspine/src/entityspine/domain/entity.py*

    **EventBus** — An in-memory or persistent pub/sub system for spine-internal events. Supports wildcard subscriptions. *See: spine-core/src/spine/core/events/__init__.py*

    **Execution Context** — Immutable correlation envelope carrying ``execution_id``, ``parent_execution_id``, ``batch_id``, and custom metadata across a pipeline run. *See: spine-core/src/spine/core/execution.py*

    ## F

    **Feed Adapter** — A class implementing the ``FeedAdapter`` protocol that fetches data from an external source (RSS, REST API, file) and returns ``RecordCandidate`` objects. *See: feedspine/src/feedspine/adapter/base.py*

    **Finding** — The atomic unit of insight in spine-tools. Every auditor, scanner, and maintainer produces ``ToolFinding`` objects that can be aggregated, filtered, and rendered. *See: spine-tools/src/spine_tools/capabilities/base.py*

    ## G

    **Gold** (Medallion Layer) — Enriched, curated data ready for consumption. Entity-resolved, sentiment-scored, derived metrics applied. *See: P016 in PRINCIPLES.md*

    **Guardrails** — Enforced development standards documented in each repo's ``docs/GUARDRAILS.md``. Covers typing, testing, coverage, docstrings, and CI rules.

    ## I

    **Idempotency Level** — One of three explicit levels: **L1_APPEND** (always insert), **L2_INPUT** (hash-based dedup), **L3_STATE** (delete+replace). *See: spine-core/src/spine/core/idempotency.py*

    **IdentifierClaim** — An assertion that a particular identifier (CIK, LEI, CUSIP, FIGI, etc.) belongs to an entity, with ``confidence``, ``source``, and temporal validity. The foundation of cross-vendor resolution. *See: entityspine/src/entityspine/domain/claim.py*

    ## L

    **Listing** — An exchange-specific trading venue for a security. Contains ``ticker``, ``mic`` (Market Identifier Code), ``start_date``, ``end_date``. Ticker lives HERE, not on Entity. *See: entityspine/src/entityspine/domain/listing.py*

    ## M

    **Manifest** (Work Manifest) — A tracking record for a work item as it progresses through pipeline stages (PENDING → INGESTED → NORMALIZED → AGGREGATED → PUBLISHED). One row per stage per partition. *See: spine-core/src/spine/core/manifest.py*

    **Managed Workflow** — A fluent builder API for constructing workflows. The recommended primary entry point. *See: spine-core/src/spine/orchestration/managed_workflow.py*

    **Medallion Architecture** — The Bronze → Silver → Gold data quality layering model. *See: P016 in PRINCIPLES.md*

    ## N

    **Natural Key** — A deterministic identifier computed from ``hash(source, record_type, content_id)``. Used for deduplication. *See: P009 in PRINCIPLES.md*

    ## P

    **Partition Key** — A JSON string that logically groups work items within shared tables (e.g., ``{"domain": "feedspine", "week_ending": "2025-12-26"}``). Enables cross-domain queries on shared ``core_*`` tables. *See: P007 in PRINCIPLES.md*

    **Playground** — An interactive debugger for stepping through workflow execution one step at a time. Supports peek, rewind, and fork. *See: spine-core/src/spine/orchestration/playground.py*

    **Protocol** — A PEP 544 structural typing interface. The primary abstraction mechanism in the suite (not ABC). *See: P001 in PRINCIPLES.md*

    **Provenance** — Metadata tracking which source produced a piece of data, when, and with what confidence. Foundation of data trust. *See: entityspine/src/entityspine/domain/provenance.py*

    ## R

    **Reject** — A record that failed validation, captured with stage, reason code, raw data, and execution context. **Never deleted.** *See: spine-core/src/spine/core/rejects.py*

    **Repository** — A class encapsulating data access for a specific domain type. Pairs a ``Connection`` with a ``Dialect`` for portable SQL. *See: P017 in PRINCIPLES.md*

    **Resolution** — The process of identifying which entity a query (ticker, CIK, name) refers to. Returns ranked candidates with confidence scores, not a single match. *See: entityspine/src/entityspine/services/resolver.py*

    **Result[T]** — A discriminated union: ``Ok[T]`` (success) or ``Err[T]`` (failure). Forces explicit error handling. *See: spine-core/src/spine/core/result.py*

    **Runner** — A component that executes a workflow blueprint. Variants: ``WorkflowRunner`` (basic), ``TrackedWorkflowRunner`` (persistent), ``DryRunExecutor`` (preview). *See: P012 in PRINCIPLES.md*

    ## S

    **Security** — A financial instrument (common stock, preferred stock, bond, warrant) issued by an Entity. Has ``security_type`` and links to ``IdentifierClaim`` objects. *See: entityspine/src/entityspine/domain/security.py*

    **Sighting** — A record of when/where a piece of data was observed. Tracks ``first_sighted_at``, ``last_sighted_at``, ``sighting_count``, ``sighting_sources``. Key to dedup metrics. *See: feedspine/src/feedspine/models/sighting.py*

    **Silver** (Medallion Layer) — Cleaned, normalized, deduplicated data. Business rules applied. Traceable to Bronze source. *See: P016 in PRINCIPLES.md*

    **Step** — A unit of work within a workflow. Types: ``lambda_`` (function), ``pipeline`` (sub-pipeline), ``choice`` (conditional), ``wait`` (delay), ``map`` (parallel fan-out). *See: spine-core/src/spine/orchestration/step_types.py*

    **StepResult** — Envelope containing a step's output, status, error category, quality metrics, and duration. The standard return type from step handlers. *See: spine-core/src/spine/orchestration/step_result.py*

    ## T

    **Tier** — A deployment level determining which backends are available. Tier 0 (JSON/Memory) → Tier 1 (SQLite) → Tier 2 (DuckDB) → Tier 3 (PostgreSQL) → Tier 4+ (PostgreSQL + Elasticsearch + Neo4j). *See: P005 in PRINCIPLES.md*

    **Tier Capability Honesty** — The principle that when a requested feature exceeds the current tier, the system warns (not silently ignores). *See: P015 in PRINCIPLES.md*

    ## W

    **Watermark** — A cursor tracking how far a consumer has processed a data stream. Supports forward-only advancement and gap detection. *See: spine-core/src/spine/core/watermarks.py*

    **WeekEnding** — A value object wrapping a ``date`` that is validated to be a Friday at construction time. Prevents silent calendar bugs. *See: spine-core/src/spine/core/temporal.py*

    **Workflow** — A frozen dataclass defining a DAG of steps with execution policy, failure policy, and defaults. Contains no execution logic. *See: spine-core/src/spine/orchestration/workflow.py*

    **WorkSpec** — The canonical contract between submitter and executor. Makes spine-core runtime-agnostic. *See: spine-core/src/spine/execution/spec.py*

Tags: glossary, terminology, reference, canonical
Doc-Types: GLOSSARY
"""
