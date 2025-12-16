"""Tests for SQL schema loading utilities."""

from __future__ import annotations

import sqlite3
from pathlib import Path
import textwrap

import pytest

from spine.core.schema_loader import (
    SCHEMA_DIR,
    apply_all_schemas,
    create_test_db,
    get_schema_files,
    get_table_list,
    get_table_schema,
    read_schema_sql,
)


# ── get_schema_files tests ────────────────────────────────────────────


class TestGetSchemaFiles:
    def test_returns_real_schema_files(self):
        files = get_schema_files()
        assert len(files) >= 5  # At least 00, 02-05 (01_orchestration removed)
        assert all(f.suffix == ".sql" for f in files)
        assert files[0].name.startswith("00_")

    def test_files_are_sorted(self):
        files = get_schema_files()
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_custom_schema_dir(self, tmp_path: Path):
        (tmp_path / "01_test.sql").write_text("CREATE TABLE t1 (id INTEGER);")
        (tmp_path / "00_init.sql").write_text("CREATE TABLE t0 (id INTEGER);")
        files = get_schema_files(tmp_path)
        assert [f.name for f in files] == ["00_init.sql", "01_test.sql"]

    def test_empty_dir(self, tmp_path: Path):
        assert get_schema_files(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path: Path):
        assert get_schema_files(tmp_path / "nope") == []


# ── read_schema_sql tests ─────────────────────────────────────────────


class TestReadSchemaSql:
    def test_reads_all_files(self, tmp_path: Path):
        (tmp_path / "00_a.sql").write_text("CREATE TABLE a (id INTEGER);")
        (tmp_path / "01_b.sql").write_text("CREATE TABLE b (id INTEGER);")

        sql = read_schema_sql(tmp_path)
        assert "-- Source: 00_a.sql" in sql
        assert "CREATE TABLE a" in sql
        assert "-- Source: 01_b.sql" in sql
        assert "CREATE TABLE b" in sql

    def test_empty_dir_returns_empty_string(self, tmp_path: Path):
        assert read_schema_sql(tmp_path) == ""


# ── apply_all_schemas tests ───────────────────────────────────────────


class TestApplyAllSchemas:
    @pytest.fixture
    def conn(self):
        c = sqlite3.connect(":memory:")
        yield c
        c.close()

    @pytest.fixture
    def schema_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "schema"
        d.mkdir()
        (d / "00_init.sql").write_text(
            textwrap.dedent("""\
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT
                );
            """)
        )
        (d / "01_orders.sql").write_text(
            textwrap.dedent("""\
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id)
                );
            """)
        )
        return d

    def test_applies_all_files(self, conn, schema_dir):
        applied = apply_all_schemas(conn, schema_dir)
        assert applied == ["00_init.sql", "01_orders.sql"]

        tables = get_table_list(conn)
        assert "users" in tables
        assert "orders" in tables

    def test_skip_files(self, conn, schema_dir):
        applied = apply_all_schemas(conn, schema_dir, skip_files=["00_init.sql"])
        assert applied == ["01_orders.sql"]

        tables = get_table_list(conn)
        assert "users" not in tables

    def test_empty_schema_dir(self, conn, tmp_path):
        applied = apply_all_schemas(conn, tmp_path)
        assert applied == []

    def test_real_schemas(self, conn):
        """Test that real spine-core schemas apply correctly."""
        applied = apply_all_schemas(conn)
        assert len(applied) >= 5  # 00, 02-05 (01_orchestration removed)

        tables = get_table_list(conn)
        # Check some expected tables from 00_core.sql
        assert "core_executions" in tables
        assert "core_rejects" in tables
        assert "core_anomalies" in tables


# ── create_test_db tests ──────────────────────────────────────────────


class TestCreateTestDb:
    def test_creates_in_memory_db(self):
        conn = create_test_db()
        try:
            tables = get_table_list(conn)
            assert len(tables) > 0
            assert "core_executions" in tables
        finally:
            conn.close()

    def test_custom_schema_dir(self, tmp_path: Path):
        (tmp_path / "00_test.sql").write_text("CREATE TABLE test_table (id INTEGER);")
        conn = create_test_db(tmp_path)
        try:
            tables = get_table_list(conn)
            assert "test_table" in tables
        finally:
            conn.close()


# ── get_table_list tests ──────────────────────────────────────────────


class TestGetTableList:
    def test_empty_db(self):
        conn = sqlite3.connect(":memory:")
        assert get_table_list(conn) == []
        conn.close()

    def test_with_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE z_table (id INTEGER)")
        conn.execute("CREATE TABLE a_table (id INTEGER)")
        tables = get_table_list(conn)
        # Should be sorted
        assert tables == ["a_table", "z_table"]
        conn.close()


# ── get_table_schema tests ────────────────────────────────────────────


class TestGetTableSchema:
    def test_returns_create_statement(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        schema = get_table_schema(conn, "users")
        assert "CREATE TABLE users" in schema
        assert "id INTEGER PRIMARY KEY" in schema
        conn.close()

    def test_nonexistent_table(self):
        conn = sqlite3.connect(":memory:")
        with pytest.raises(ValueError, match="Table not found"):
            get_table_schema(conn, "nonexistent")
        conn.close()


# ── SCHEMA_DIR constant tests ─────────────────────────────────────────


class TestSchemaDir:
    def test_schema_dir_exists(self):
        assert SCHEMA_DIR.exists()
        assert SCHEMA_DIR.is_dir()

    def test_has_sql_files(self):
        files = list(SCHEMA_DIR.glob("*.sql"))
        assert len(files) >= 5  # 00, 02-05 (01_orchestration removed)
