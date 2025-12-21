"""Spine Suite — Tenets (60-second manifesto).

Documentation carrier module. Content is extracted by document-spine
and rendered into TENETS.md.

Manifesto:
    **1. Protocols, not inheritance.**
    Define what a thing *does*, not what it *is*. Any object with the right methods belongs.

    **2. Zero deps by default.**
    stdlib gets you from zero to working. PostgreSQL, Redis, Neo4j — those are upgrades, not requirements.

    **3. Explicit over implicit.**
    If it can fail, return ``Result[T]``. If it has a level, declare it. If it's a Friday, make it a type.

    **4. Errors are data.**
    Classify them. Chain them. Route them. Never swallow them.

    **5. Audit everything.**
    Rejects, anomalies, corrections, merges, events — append-only, permanent, queryable.

    **6. Start simple, scale when you need to.**
    SQLite today, PostgreSQL tomorrow. Same code. Same tests.

    **7. Blueprints describe; runners execute.**
    A workflow is data. What you do with it — run, lint, visualize, dry-run, replay — is a separate concern.

    **8. Compose small things.**
    Steps into workflows. Workflows into pipelines. Pipelines into orchestrations. Never a god-class.

    **9. Identifiers are claims, not facts.**
    Confidence-scored, temporally bounded, traceable to source. The truth is always contested.

    **10. Test without infrastructure.**
    If your test needs Docker, it's an integration test. Unit tests run on ``MemoryStorage`` and ``StubExecutor``.

    ---

    *The full evidence and rationale behind each tenet is in SPINE_PRINCIPLES.md.*

Tags: tenets, manifesto, philosophy, principles
Doc-Types: TENETS
"""
