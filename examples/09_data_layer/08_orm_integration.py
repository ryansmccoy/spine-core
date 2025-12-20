#!/usr/bin/env python3
"""ORM Integration — SQLAlchemy ORM alongside the Dialect layer.

WHY BOTH ORM AND DIALECT?
─────────────────────────
The Dialect layer is lightweight and zero-dependency — perfect for
CLI tools and small scripts.  The ORM layer adds SQLAlchemy 2.0 for
relationship navigation, lazy loading, and session-scoped transactions
— ideal for web APIs and complex domain logic.  Both coexist via
SAConnectionBridge, which wraps an ORM session as a Connection.

ARCHITECTURE
────────────
    ┌────────────────────────────────────┐
    │ create_spine_engine(url)            │
    │   → SA Engine with SpineBase models │
    └────────────────┬───────────────────┘
                     │
              SpineSession(engine)
                     │
          ┌─────────┼───────────┐
          ▼                    ▼
    ORM operations      SAConnectionBridge
    session.add()       → Connection protocol
    session.query()     → raw SQL via execute()

    Mix ORM writes with raw-SQL reads in one transaction.

KEY COMPONENTS
──────────────
    Component              Purpose
    ────────────────────── ────────────────────────────
    create_spine_engine    Engine factory for spine models
    SpineSession           Session with auto-table creation
    SpineBase              Declarative base for all models
    SAConnectionBridge     Adapts Session → Connection
    spine_session_factory  Scoped session factory

Requires: pip install sqlalchemy (or: pip install spine-core[sqlalchemy])

Run: python examples/09_data_layer/08_orm_integration.py

See Also:
    07_database_portability — Dialect-only approach (no ORM)
    09_orm_relationships — navigating model relationships
    11_orm_vs_dialect — side-by-side comparison
"""

from __future__ import annotations

from spine.core.orm import (
    SAConnectionBridge,
    SpineBase,
    SpineSession,
    create_spine_engine,
    spine_session_factory,
)
from spine.core.orm.tables import ExecutionTable, SourceTable


def main() -> None:
    # ── 1. Engine ────────────────────────────────────────────────────
    # create_spine_engine sets up SQLite WAL mode + foreign-key pragmas
    # automatically.  For PostgreSQL, pass "postgresql://user:pw@host/db".
    engine = create_spine_engine("sqlite:///:memory:", echo=False)
    SpineBase.metadata.create_all(engine)
    print(f"Created {len(SpineBase.metadata.tables)} tables in :memory: SQLite\n")

    # ── 2. ORM writes via SpineSession ───────────────────────────────
    Session = spine_session_factory(engine)

    with Session() as session:
        # Insert two sources via ORM models
        src1 = SourceTable(
            id="src-alpha",
            name="Alpha Feed",
            source_type="api",
            config_json={"url": "https://api.example.com/alpha"},
            enabled=True,
        )
        src2 = SourceTable(
            id="src-beta",
            name="Beta Feed",
            source_type="file",
            config_json={"path": "/data/beta.csv"},
            enabled=False,
        )
        session.add_all([src1, src2])
        session.commit()

        # Query back — expire_on_commit=False so attributes are still loaded
        print(f"src1.name = {src1.name!r}  (no lazy-load needed)")
        print(f"src2.enabled = {src2.enabled!r}")

        # ORM query
        sources = session.query(SourceTable).order_by(SourceTable.name).all()
        print(f"\nAll sources ({len(sources)}):")
        for s in sources:
            print(f"  {s.id}: {s.name} ({s.source_type}) enabled={s.enabled}")

    # ── 3. Bridge: ORM session → Connection protocol ─────────────────
    # Useful when you want to call helpers that accept ``Connection``
    # (BaseRepository, Dialect helpers) but stay inside an ORM session.
    with Session() as session:
        bridge = SAConnectionBridge(session)

        # Raw SQL insert via the bridge (uses positional ? placeholders)
        bridge.execute(
            "INSERT INTO core_executions "
            "(id, workflow, lane, trigger_source, status, retry_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            ["exec-001", "ingest", "default", "manual", "running", 0],
        )
        bridge.commit()

        # Raw SQL select via the bridge
        bridge.execute(
            "SELECT id, workflow, status FROM core_executions WHERE id = ?",
            ["exec-001"],
        )
        row = bridge.fetchone()
        assert row is not None
        print(f"\nExecution via bridge: id={row[0]}, workflow={row[1]}, status={row[2]}")

        # Mix: ORM read of the same row
        exec_row = session.get(ExecutionTable, "exec-001")
        assert exec_row is not None
        print(f"Same row via ORM:    id={exec_row.id}, workflow={exec_row.workflow}")

    # ── 4. Factory shortcut ──────────────────────────────────────────
    # spine_session_factory returns a standard sessionmaker[SpineSession]
    # that you can use exactly like any SA sessionmaker.
    with Session.begin() as session:
        count = session.query(SourceTable).count()
        print(f"\nTotal sources after all transactions: {count}")

    print("\nDone — ORM + Dialect layers coexist cleanly.")


if __name__ == "__main__":
    main()
