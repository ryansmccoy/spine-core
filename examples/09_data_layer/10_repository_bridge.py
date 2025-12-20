#!/usr/bin/env python3
"""Repository Bridge — Use BaseRepository over an ORM Session.

Demonstrates ``BaseRepository.from_session()``, which wraps a SQLAlchemy
ORM ``Session`` in ``SAConnectionBridge`` so that all BaseRepository
convenience methods work transparently:

1. Creating a repository from an ORM session
2. ``insert()`` + ``commit()`` — single-row dict insertion
3. ``query()`` — returns ``list[dict]`` with column names
4. ``query_one()`` — single-row convenience
5. ``insert_many()`` — batch insertion
6. ``execute()`` — raw DDL / DML
7. Mixing ORM and repository in one transaction

This is useful when you already have an SA session (e.g. from a web
framework) but want to use BaseRepository's convenience helpers.

Run: python examples/09_data_layer/10_repository_bridge.py

Requires: pip install sqlalchemy  (or: pip install spine-core[sqlalchemy])
"""

from __future__ import annotations

from spine.core.orm import SpineBase, SpineSession, create_spine_engine
from spine.core.orm.tables import SourceTable
from spine.core.repository import BaseRepository


def main() -> None:
    engine = create_spine_engine("sqlite:///:memory:", echo=False)
    SpineBase.metadata.create_all(engine)
    print("=" * 60)
    print("BaseRepository.from_session() — Repository ↔ ORM Bridge")
    print("=" * 60)

    # ── 1. Create a repository from an ORM session ──────────────
    print("\n--- 1. Create repository from ORM session ---")

    with SpineSession(bind=engine) as session:
        repo = BaseRepository.from_session(session)
        print(f"  repo type:      {type(repo).__name__}")
        print(f"  repo.conn type: {type(repo.conn).__name__}")
        print(f"  repo.dialect:   {repo.dialect.name}")

        # ── 2. insert() — single dict insert ────────────────────
        print("\n--- 2. insert() — single-row dict insertion ---")

        repo.insert("core_sources", {
            "id": "src-alpha",
            "name": "Alpha Feed",
            "source_type": "api",
            "config_json": '{"url": "https://api.example.com/alpha"}',
            "enabled": 1,
        })
        repo.commit()
        print("  Inserted src-alpha via repo.insert()")

        # ── 3. query() — returns list[dict] ─────────────────────
        print("\n--- 3. query() — SELECT → list[dict] ---")

        rows = repo.query(
            "SELECT id, name, source_type FROM core_sources"
        )
        print(f"  query() returned {len(rows)} row(s):")
        for row in rows:
            print(f"    {row}")
        # Note: rows are dicts with column names as keys
        assert rows[0]["name"] == "Alpha Feed"

        # ── 4. query_one() — single-row convenience ─────────────
        print("\n--- 4. query_one() — single row or None ---")

        row = repo.query_one(
            f"SELECT name, source_type FROM core_sources WHERE id = {repo.ph(1)}",
            ("src-alpha",),
        )
        print(f"  query_one() → {row}")
        assert row is not None
        assert row["source_type"] == "api"

        # Missing row returns None
        missing = repo.query_one(
            f"SELECT name FROM core_sources WHERE id = {repo.ph(1)}",
            ("does-not-exist",),
        )
        print(f"  Missing row  → {missing}")
        assert missing is None

        # ── 5. insert_many() — batch insert ──────────────────────
        print("\n--- 5. insert_many() — batch insertion ---")

        count = repo.insert_many("core_sources", [
            {
                "id": "src-beta",
                "name": "Beta Feed",
                "source_type": "file",
                "config_json": '{"path": "/data/beta.csv"}',
                "enabled": 0,
            },
            {
                "id": "src-gamma",
                "name": "Gamma Stream",
                "source_type": "websocket",
                "config_json": '{"url": "wss://stream.example.com"}',
                "enabled": 1,
            },
        ])
        repo.commit()
        print(f"  insert_many() affected {count} rows")

        all_rows = repo.query("SELECT id, name FROM core_sources ORDER BY id")
        print(f"  Total sources now: {len(all_rows)}")
        for r in all_rows:
            print(f"    {r['id']}: {r['name']}")

        # ── 6. execute() — raw DDL / DML ─────────────────────────
        print("\n--- 6. execute() — raw SQL ---")

        repo.execute(
            f"UPDATE core_sources SET enabled = 1 WHERE id = {repo.ph(1)}",
            ("src-beta",),
        )
        repo.commit()

        updated = repo.query_one(
            f"SELECT id, enabled FROM core_sources WHERE id = {repo.ph(1)}",
            ("src-beta",),
        )
        print(f"  Updated src-beta enabled: {updated['enabled']}")

        # ── 7. Mix ORM + repository in one transaction ───────────
        print("\n--- 7. Mixing ORM and repository in one transaction ---")

        # ORM write: add a new source via the session
        session.add(SourceTable(
            id="src-delta",
            name="Delta Feed",
            source_type="api",
            config_json={"url": "https://delta.example.com"},
            enabled=True,
        ))
        session.flush()  # flush so the row is visible to raw SQL

        # Repository read: query it back via raw SQL
        delta = repo.query_one(
            f"SELECT name, source_type FROM core_sources WHERE id = {repo.ph(1)}",
            ("src-delta",),
        )
        print(f"  ORM insert + repo read: {delta}")

        # Repository write + ORM read
        repo.insert("core_sources", {
            "id": "src-epsilon",
            "name": "Epsilon Feed",
            "source_type": "file",
            "config_json": '{}',
            "enabled": 1,
        })
        session.flush()

        orm_row = session.get(SourceTable, "src-epsilon")
        print(f"  Repo insert + ORM read: name={orm_row.name}")

        session.commit()

        total = repo.query("SELECT COUNT(*) as cnt FROM core_sources")
        print(f"\n  Final source count: {total[0]['cnt']}")

    print("\n" + "=" * 60)
    print("Done — BaseRepository works seamlessly over ORM sessions.")
    print("=" * 60)


if __name__ == "__main__":
    main()
