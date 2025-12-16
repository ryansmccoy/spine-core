"""Tests for the SQL migration runner."""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from spine.core.migrations.runner import MigrationRecord, MigrationResult, MigrationRunner


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite connection."""
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


@pytest.fixture()
def schema_dir(tmp_path: Path) -> Path:
    """Create a temp schema directory with numbered SQL files."""
    d = tmp_path / "schema"
    d.mkdir()

    (d / "00_core.sql").write_text(
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS core_executions (
                id INTEGER PRIMARY KEY,
                name TEXT
            );
        """),
        encoding="utf-8",
    )
    (d / "01_orchestration.sql").write_text(
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS orchestration_groups (
                id INTEGER PRIMARY KEY,
                group_name TEXT
            );
        """),
        encoding="utf-8",
    )
    (d / "02_workflow.sql").write_text(
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS workflow_history (
                id INTEGER PRIMARY KEY,
                status TEXT
            );
        """),
        encoding="utf-8",
    )
    return d


@pytest.fixture()
def runner(conn: sqlite3.Connection, schema_dir: Path) -> MigrationRunner:
    """MigrationRunner wired to temp schema dir."""
    return MigrationRunner(conn, schema_dir=schema_dir)


# ── MigrationResult dataclass tests ──────────────────────────────────


class TestMigrationResult:
    def test_empty_result_is_success(self):
        r = MigrationResult()
        assert r.success is True
        assert r.applied == []
        assert r.skipped == []
        assert r.errors == {}

    def test_result_with_errors_is_not_success(self):
        r = MigrationResult(errors={"bad.sql": "syntax error"})
        assert r.success is False


# ── MigrationRecord dataclass tests ──────────────────────────────────


class TestMigrationRecord:
    def test_fields(self):
        rec = MigrationRecord(id=1, filename="00_core.sql", applied_at="2025-01-01")
        assert rec.id == 1
        assert rec.filename == "00_core.sql"
        assert rec.applied_at == "2025-01-01"


# ── Core runner tests ────────────────────────────────────────────────


class TestMigrationRunner:
    def test_creates_migrations_table(self, conn, schema_dir):
        """Runner should create _migrations table on init."""
        MigrationRunner(conn, schema_dir=schema_dir)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
        )
        assert cursor.fetchone() is not None

    def test_apply_pending_all(self, runner: MigrationRunner):
        """First run should apply all 3 migrations."""
        result = runner.apply_pending()
        assert result.success is True
        assert len(result.applied) == 3
        assert result.skipped == []
        assert "00_core.sql" in result.applied
        assert "01_orchestration.sql" in result.applied
        assert "02_workflow.sql" in result.applied

    def test_apply_idempotent(self, runner: MigrationRunner):
        """Running twice should skip all on second run."""
        first = runner.apply_pending()
        assert len(first.applied) == 3

        second = runner.apply_pending()
        assert second.applied == []
        assert len(second.skipped) == 3

    def test_get_applied(self, runner: MigrationRunner):
        """After applying, get_applied returns records."""
        runner.apply_pending()
        records = runner.get_applied()
        assert len(records) == 3
        assert all(isinstance(r, MigrationRecord) for r in records)
        assert records[0].filename == "00_core.sql"
        assert records[1].filename == "01_orchestration.sql"
        assert records[2].filename == "02_workflow.sql"
        # Each record should have a non-empty applied_at
        assert all(r.applied_at for r in records)

    def test_get_pending_all(self, runner: MigrationRunner):
        """Before applying, all migrations are pending."""
        pending = runner.get_pending()
        assert len(pending) == 3

    def test_get_pending_after_partial(
        self, conn: sqlite3.Connection, schema_dir: Path
    ):
        """After applying, pending returns only unapplied."""
        runner = MigrationRunner(conn, schema_dir=schema_dir)
        # Manually mark one as applied
        conn.execute("INSERT INTO _migrations (filename) VALUES (?)", ("00_core.sql",))
        conn.commit()

        pending = runner.get_pending()
        assert "00_core.sql" not in pending
        assert len(pending) == 2

    def test_get_pending_empty_after_full_apply(self, runner: MigrationRunner):
        runner.apply_pending()
        assert runner.get_pending() == []

    def test_rollback_last(self, runner: MigrationRunner):
        runner.apply_pending()
        assert len(runner.get_applied()) == 3

        removed = runner.rollback_last()
        assert removed == "02_workflow.sql"
        assert len(runner.get_applied()) == 2

    def test_rollback_last_returns_none_when_empty(self, runner: MigrationRunner):
        assert runner.rollback_last() is None

    def test_rollback_then_reapply(self, runner: MigrationRunner):
        """After rollback, re-applying should pick up the removed migration."""
        runner.apply_pending()
        runner.rollback_last()  # remove 02_workflow.sql

        result = runner.apply_pending()
        assert result.applied == ["02_workflow.sql"]
        assert len(result.skipped) == 2

    def test_tables_created_by_migrations(
        self, runner: MigrationRunner, conn: sqlite3.Connection
    ):
        """Verify the SQL actually created the expected tables."""
        runner.apply_pending()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "core_executions" in tables
        assert "orchestration_groups" in tables
        assert "workflow_history" in tables

    def test_error_stops_processing(self, conn: sqlite3.Connection, tmp_path: Path):
        """If a migration has bad SQL, processing stops."""
        d = tmp_path / "bad_schema"
        d.mkdir()
        (d / "00_good.sql").write_text("CREATE TABLE good (id INTEGER);")
        (d / "01_bad.sql").write_text("THIS IS NOT SQL;")
        (d / "02_never.sql").write_text("CREATE TABLE never (id INTEGER);")

        runner = MigrationRunner(conn, schema_dir=d)
        result = runner.apply_pending()

        assert result.success is False
        assert "00_good.sql" in result.applied
        assert "01_bad.sql" in result.errors
        assert "02_never.sql" not in result.applied
        assert "02_never.sql" not in result.skipped

    def test_empty_schema_dir(self, conn: sqlite3.Connection, tmp_path: Path):
        """Empty schema dir should result in no-op."""
        d = tmp_path / "empty"
        d.mkdir()
        runner = MigrationRunner(conn, schema_dir=d)
        result = runner.apply_pending()
        assert result.success is True
        assert result.applied == []

    def test_missing_schema_dir(self, conn: sqlite3.Connection, tmp_path: Path):
        """Non-existent schema dir should result in no-op."""
        runner = MigrationRunner(conn, schema_dir=tmp_path / "nope")
        result = runner.apply_pending()
        assert result.success is True
        assert result.applied == []

    def test_default_schema_dir(self, conn: sqlite3.Connection):
        """When no schema_dir given, defaults to core/schema/."""
        runner = MigrationRunner(conn)
        # Should not raise - just discovers whatever is in the real schema dir
        pending = runner.get_pending()
        assert isinstance(pending, list)

    def test_incremental_migration(
        self, conn: sqlite3.Connection, schema_dir: Path
    ):
        """Add a new migration file after initial apply."""
        runner = MigrationRunner(conn, schema_dir=schema_dir)
        runner.apply_pending()
        assert len(runner.get_applied()) == 3

        # Add a 4th migration
        (schema_dir / "03_alerting.sql").write_text(
            "CREATE TABLE alerts (id INTEGER PRIMARY KEY, msg TEXT);"
        )

        result = runner.apply_pending()
        assert result.applied == ["03_alerting.sql"]
        assert len(result.skipped) == 3
        assert len(runner.get_applied()) == 4
