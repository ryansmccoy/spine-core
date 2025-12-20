"""Data layer — Adapters, protocols, DB portability, ORM, migrations.

The data layer provides portable database access through adapters,
protocols, and provider injection.  It supports both raw SQL via
the Dialect layer and SQLAlchemy ORM, with migration tracking and
retention policies.

Examples are grouped into four logical sections.

ADAPTERS & PROTOCOLS — portable data access
────────────────────────────────────────────
    01 — Database adapters (SQLiteAdapter, portable queries)
    02 — Protocols and storage (type contracts, cross-dialect SQL)
    03 — Database provider (tier-agnostic connection injection)

SCHEMA & LIFECYCLE — managing database state
─────────────────────────────────────────────
    04 — Migration runner (versioned schema upgrades)
    05 — Data retention (purge policies for old records)
    06 — Schema loader (bulk schema loading and introspection)
    07 — Database portability (SQL that runs on any backend)

ORM — SQLAlchemy integration
─────────────────────────────
    08 — ORM integration (SQLAlchemy ORM alongside Dialect)
    09 — ORM relationships (parent/child navigation)
    10 — Repository bridge (BaseRepository over ORM Session)
    11 — ORM vs Dialect (side-by-side comparison)
"""
