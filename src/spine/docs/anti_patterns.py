"""Spine Suite — Anti-Patterns and Non-Goals.

Documentation carrier module. Content is extracted by document-spine
and rendered into ANTI_PATTERNS.md.

Manifesto:
    ## Anti-Patterns

    ### AP001 — Bare ``Exception`` Handling

    **What:** Catching or raising generic ``Exception`` instead of typed ``SpineError`` subclasses.

    **Why it's bad:** Swallows context (category, retryable flag, cause chain). Prevents proper retry routing and audit logging.

    **Evidence:** ``spine-core/src/spine/core/errors.py`` — *"Use appropriate SpineError subclass."*

    ---

    ### AP002 — Implicit Idempotency

    **What:** Not declaring the idempotency level of a pipeline stage.

    **Why it's bad:** Financial pipelines **will** be restarted. Without a declared level, duplicate records corrupt downstream analytics.

    **Evidence:** ``spine-core/src/spine/core/idempotency.py`` — *"Explicitly declaring level documents behavior."*

    ---

    ### AP003 — Deleting Audit Records

    **What:** Issuing ``DELETE`` against ``core_rejects``, ``core_anomalies``, ``core_execution_events``, or merge events.

    **Why it's bad:** Destroys the compliance audit trail.

    **Evidence:**
    - ``spine-core/src/spine/core/rejects.py`` — *"Rejects are NEVER deleted."*
    - ``spine-core/src/spine/core/anomalies.py`` — *"Anomalies are NEVER deleted."*
    - ``spine-core/src/spine/execution/events.py`` — *"Events are append-only."*

    ---

    ### AP004 — Pydantic in the Domain Layer

    **What:** Using Pydantic ``BaseModel`` for core domain objects.

    **Why it's bad:** Creates a hard dependency. Violates zero-dependency principle. Slows down construction.

    **Evidence:** ``entityspine/src/entityspine/domain/entity.py`` — ``STDLIB ONLY - NO PYDANTIC.``

    ---

    ### AP005 — Raw SQL in Domain Logic

    **What:** Embedding database-specific SQL strings directly in business logic code.

    **Why it's bad:** Breaks portability across SQLite/PostgreSQL/DuckDB.

    **Evidence:** ``spine-core/src/spine/core/dialect.py`` — *"Domain repositories use Dialect methods."*

    ---

    ### AP006 — Silent Feature Degradation

    **What:** Silently ignoring a requested feature because the current storage tier doesn't support it.

    **Why it's bad:** Users think they got fuzzy matching when they got exact-match-only.

    **Evidence:** ``entityspine/src/entityspine/domain/resolution.py`` — *"When unavailable, warnings are added."*

    ---

    ### AP007 — Top-Level Import of Optional Dependencies

    **What:** Importing heavy or optional packages at module top level without guarding.

    **Why it's bad:** Causes ``ImportError`` for users without the extra. Breaks zero-dependency guarantee.

    **Evidence:** ``spine-core/src/spine/core/__init__.py`` — *"import-guarded extras."*

    ---

    ### AP008 — God-Class Workflow Definition

    **What:** Building a single massive workflow with 50+ steps and inline lambdas.

    **Why it's bad:** Untestable, unreadable, impossible to reuse sub-flows.

    **Evidence:** ``spine-core/src/spine/orchestration/composition.py`` — functional operators for decomposition.

    ---

    ### AP009 — ``unwrap()`` Without Checking ``is_ok()``

    **What:** Calling ``.unwrap()`` on a ``Result[T]`` without first checking success.

    **Why it's bad:** Raises ``UnwrapError`` at runtime. Defeats explicit error handling.

    **Evidence:** ``spine-core/src/spine/core/result.py`` — *"Use unwrap_or() or pattern matching."*

    ---

    ### AP010 — Ticker as Entity Identifier

    **What:** Using a stock ticker symbol as a unique identifier for a company/entity.

    **Why it's bad:** Tickers are temporal (FB → META), exchange-specific, reusable, and ambiguous.

    **Evidence:** ``entityspine/src/entityspine/domain/listing.py`` — *"Tickers are NOT entity identifiers."*

    ---

    ### AP011 — Auto-Merging Duplicate Entities

    **What:** Automatically merging entities flagged as duplicates without human review.

    **Why it's bad:** False positives destroy data.

    **Evidence:** ``entityspine/src/entityspine/services/clustering.py`` — *"Never auto-merge."*

    ---

    ### AP012 — Returning Rich Renderables from APIs

    **What:** Having SDK/API functions return ``rich.Table``, ``rich.Panel``, or other UI objects.

    **Why it's bad:** Can't be serialized for MCP tools, REST APIs, or CI pipelines.

    **Evidence:** ``spine-tools/src/spine_tools/api.py`` — *"All functions return dataclasses or typed dicts."*

    ---

    ### AP013 — Operations Without Timeouts

    **What:** Making external calls without a deadline.

    **Why it's bad:** Resource exhaustion, cascading failures, poor user experience.

    **Evidence:** ``spine-core/src/spine/execution/timeout.py`` — *"Operations without timeouts are a reliability anti-pattern."*

    ---

    ### AP014 — Mutable Workflow Context

    **What:** Modifying ``WorkflowContext`` in-place during step execution.

    **Why it's bad:** Creates hidden coupling between steps. Breaks step isolation and replay.

    **Evidence:** ``spine-core/src/spine/orchestration/workflow_context.py`` — *"Steps return updates, runner creates new context."*

    ---

    ### AP015 — Insert-or-Ignore for Feed Dedup

    **What:** Using ``INSERT OR IGNORE`` for feed deduplication instead of three-way classification.

    **Why it's bad:** Can't distinguish true duplicates from updates. Loses sighting history.

    **Evidence:** ``feedspine/src/feedspine/pipeline/action.py`` — *"We distinguish true duplicates from updates."*

    ---

    ## Non-Goals

    | ID | Statement |
    |----|-----------|
    | NG001 | **Not a general-purpose ETL framework** — FeedSpine captures structured feeds. It is not Airflow, Dagster, or dbt. |
    | NG002 | **Not a task scheduler** — Use Celery, Airflow, or cron for scheduling. |
    | NG003 | **Not a data warehouse** — Spine captures and routes data. Analysis happens downstream. |
    | NG004 | **Not a web scraper** — FeedSpine consumes structured feeds, not HTML. |
    | NG005 | **Not a general graph database** — EntitySpine provides entity resolution with optional graph export. |
    | NG006 | **Not a trading system** — We resolve identities, not execute trades. |
    | NG007 | **Not a monolithic application** — Each project is independent with its own lifecycle. |

    ---

    ## Summary Table

    | ID | Category | Statement |
    |----|----------|-----------|
    | AP001 | Error Handling | Don't catch/raise bare ``Exception`` |
    | AP002 | Idempotency | Don't skip idempotency level declaration |
    | AP003 | Audit | Don't delete reject/anomaly/event records |
    | AP004 | Architecture | Don't use Pydantic in domain layer |
    | AP005 | Persistence | Don't embed raw SQL in domain logic |
    | AP006 | Transparency | Don't silently degrade features |
    | AP007 | Dependencies | Don't top-level import optional deps |
    | AP008 | Composability | Don't build monolithic workflows |
    | AP009 | Error Handling | Don't ``unwrap()`` without checking |
    | AP010 | Entity Model | Don't use ticker as entity identifier |
    | AP011 | Entity Model | Don't auto-merge without human review |
    | AP012 | API Design | Don't return Rich renderables from APIs |
    | AP013 | Reliability | Don't make calls without timeouts |
    | AP014 | Orchestration | Don't mutate workflow context in-place |
    | AP015 | Dedup | Don't use insert-or-ignore for feeds |

Tags: anti_patterns, non_goals, guardrails, philosophy
Doc-Types: ANTI_PATTERNS
"""
