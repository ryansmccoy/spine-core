#!/usr/bin/env python3
"""ORM vs Dialect — Side-by-side comparison of both data access paths.

spine-core supports **two coexisting** data access paths.  This example
performs the **same four operations** using both approaches so you can
compare the ergonomics and choose the right tool for each job:

  ┌──────────────────┬──────────────────────────────────────────────┐
  │ **Dialect path**  │ BaseRepository + raw SQL + Connection        │
  │ **ORM path**      │ SpineSession + SA model classes              │
  └──────────────────┴──────────────────────────────────────────────┘

Operations compared:
  1. CREATE (insert a row)
  2. READ   (fetch one row by PK)
  3. UPDATE (modify a field)
  4. LIST   (filtered multi-row query)

Decision guide at the end.

Run: python examples/09_data_layer/11_orm_vs_dialect.py

Requires: pip install sqlalchemy  (or: pip install spine-core[sqlalchemy])
"""

from __future__ import annotations

import datetime

from sqlalchemy import select

from spine.core.orm import SpineBase, SpineSession, create_spine_engine
from spine.core.orm.tables import SourceFetchTable, SourceTable
from spine.core.repository import BaseRepository


def main() -> None:
    engine = create_spine_engine("sqlite:///:memory:", echo=False)
    SpineBase.metadata.create_all(engine)

    print("=" * 60)
    print("ORM vs Dialect — Same Operations, Two Paths")
    print("=" * 60)

    # ================================================================
    # DIALECT PATH — BaseRepository + raw SQL
    # ================================================================
    print("\n┌──────────────────────────────────────────┐")
    print("│  DIALECT PATH  (BaseRepository + raw SQL) │")
    print("└──────────────────────────────────────────┘")

    with SpineSession(bind=engine) as session:
        repo = BaseRepository.from_session(session)

        # 1. CREATE
        print("\n  1. CREATE — repo.insert(table, dict)")
        repo.insert("core_sources", {
            "id": "src-d1",
            "name": "Dialect Source",
            "source_type": "api",
            "config_json": '{"dialect": true}',
            "enabled": 1,
        })
        repo.commit()
        print("     → Inserted 'Dialect Source'")

        # 2. READ
        print("\n  2. READ — repo.query_one(sql, params)")
        row = repo.query_one(
            f"SELECT id, name, source_type FROM core_sources "
            f"WHERE id = {repo.ph(1)}",
            ("src-d1",),
        )
        print(f"     → {row}")

        # 3. UPDATE
        print("\n  3. UPDATE — repo.execute(sql, params)")
        repo.execute(
            "UPDATE core_sources SET name = ? "
            "WHERE id = ?",
            ("Dialect Source (updated)", "src-d1"),
        )
        repo.commit()
        updated = repo.query_one(
            f"SELECT name FROM core_sources WHERE id = {repo.ph(1)}",
            ("src-d1",),
        )
        print(f"     → name is now: {updated['name']}")

        # Add a couple more for the LIST demo
        repo.insert_many("core_sources", [
            {"id": "src-d2", "name": "Feed A", "source_type": "file",
             "config_json": "{}", "enabled": 1},
            {"id": "src-d3", "name": "Feed B", "source_type": "file",
             "config_json": "{}", "enabled": 0},
        ])
        repo.commit()

        # 4. LIST with filter
        print("\n  4. LIST — repo.query(sql, params)  [filter: source_type='file']")
        rows = repo.query(
            f"SELECT id, name, enabled FROM core_sources "
            f"WHERE source_type = {repo.ph(1)} ORDER BY id",
            ("file",),
        )
        print(f"     → {len(rows)} rows:")
        for r in rows:
            print(f"       {r['id']}: {r['name']} (enabled={r['enabled']})")

    # ================================================================
    # ORM PATH — SpineSession + SA models
    # ================================================================
    print("\n┌──────────────────────────────────────────┐")
    print("│  ORM PATH  (SpineSession + SA models)     │")
    print("└──────────────────────────────────────────┘")

    with SpineSession(bind=engine) as session:

        # 1. CREATE
        print("\n  1. CREATE — session.add(ModelInstance)")
        src = SourceTable(
            id="src-o1",
            name="ORM Source",
            source_type="api",
            config_json={"orm": True},
            enabled=True,
        )
        session.add(src)
        session.commit()
        print(f"     → Inserted '{src.name}'")

        # 2. READ
        print("\n  2. READ — session.get(Model, pk)")
        loaded = session.get(SourceTable, "src-o1")
        print(f"     → id={loaded.id}, name={loaded.name}, "
              f"type={loaded.source_type}")

        # 3. UPDATE
        print("\n  3. UPDATE — mutate attribute + commit")
        loaded.name = "ORM Source (updated)"
        session.commit()
        refreshed = session.get(SourceTable, "src-o1")
        print(f"     → name is now: {refreshed.name}")

        # 4. LIST with filter (SA 2.0 select() style)
        print("\n  4. LIST — select().where()  [filter: source_type='file']")
        stmt = (
            select(SourceTable)
            .where(SourceTable.source_type == "file")
            .order_by(SourceTable.id)
        )
        results = session.execute(stmt).scalars().all()
        print(f"     → {len(results)} rows:")
        for s in results:
            print(f"       {s.id}: {s.name} (enabled={s.enabled})")

    # ================================================================
    # ORM BONUS: Relationship navigation (not possible with dialect)
    # ================================================================
    print("\n┌──────────────────────────────────────────┐")
    print("│  ORM BONUS  — Relationship navigation     │")
    print("└──────────────────────────────────────────┘")

    with SpineSession(bind=engine) as session:
        # Add a fetch linked to a source
        session.add(SourceFetchTable(
            id="sf-001", source_id="src-o1",
            source_name="ORM Source", source_type="api",
            source_locator="https://example.com/feed",
            status="ok", record_count=42,
            started_at=datetime.datetime.now(),
        ))
        session.commit()

        # Navigate: source → fetches (no extra query needed)
        src = session.get(SourceTable, "src-o1")
        print(f"\n  Source '{src.name}' has {len(src.fetches)} fetch(es):")
        for f in src.fetches:
            print(f"    {f.id}: {f.record_count} records, status={f.status}")

    # ================================================================
    # DECISION GUIDE
    # ================================================================
    print("\n" + "=" * 60)
    print("When to use which path?")
    print("=" * 60)
    print("""
  DIALECT PATH (BaseRepository + raw SQL)
    ✓ Zero dependencies beyond stdlib (sqlite3)
    ✓ Full control over SQL — custom JOINs, CTEs, aggregates
    ✓ Portable across 5 backends via Dialect abstraction
    ✓ Lightweight — no model class overhead
    ✗ No relationship navigation
    ✗ Manual dict ↔ row mapping

  ORM PATH (SpineSession + SA models)
    ✓ Type-safe model attributes
    ✓ Relationship navigation (parent→child, back_populates)
    ✓ Identity map — same PK = same Python object
    ✓ Cascade deletes, eager/lazy loading
    ✗ Requires sqlalchemy dependency
    ✗ More memory for large result sets

  BRIDGE (BaseRepository.from_session)
    ✓ Best of both — ORM session + repo convenience
    ✓ Useful in web frameworks where you already have a Session
    ✓ Mix ORM writes with raw-SQL reads in one transaction
""")
    print("Done — both paths demonstrated side by side.")
    print("=" * 60)


if __name__ == "__main__":
    main()
