"""SQL migration runner.

Reads ``.sql`` files from the schema directory, tracks applied migrations
in the ``_migrations`` table, and applies pending ones in filename order.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Default schema directory - adjacent to this module's parent
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


@dataclass
class MigrationRecord:
    """Record of a single applied migration."""

    id: int
    filename: str
    applied_at: str


@dataclass
class MigrationResult:
    """Result of a migration run."""

    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class MigrationRunner:
    """Applies SQL migrations from a schema directory.

    Parameters
    ----------
    conn
        A ``sqlite3.Connection`` (or compatible DB-API2 connection).
    schema_dir
        Directory containing numbered ``.sql`` files.
        Defaults to ``spine/core/schema/``.

    Example::

        import sqlite3
        from spine.core.migrations import MigrationRunner

        conn = sqlite3.connect("spine.db")
        runner = MigrationRunner(conn)
        result = runner.apply_pending()
        print(f"Applied {len(result.applied)} migrations")
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        schema_dir: Path | str | None = None,
    ) -> None:
        self._conn = conn
        self._schema_dir = Path(schema_dir) if schema_dir else _SCHEMA_DIR
        self._ensure_migrations_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_pending(self) -> MigrationResult:
        """Apply all pending migrations in filename order.

        Returns ``MigrationResult`` with lists of applied, skipped, and
        errored migrations.
        """
        result = MigrationResult()
        applied = {r.filename for r in self.get_applied()}

        for sql_file in self._discover_migrations():
            name = sql_file.name
            if name in applied:
                result.skipped.append(name)
                continue

            try:
                sql = sql_file.read_text(encoding="utf-8")
                self._conn.executescript(sql)
                self._record_migration(name)
                result.applied.append(name)
                logger.info("migration.applied", extra={"migration": name})
            except Exception as exc:
                result.errors[name] = str(exc)
                logger.error(
                    "migration.failed",
                    extra={"migration": name, "error": str(exc)},
                )
                break  # Stop on first error

        return result

    def get_applied(self) -> list[MigrationRecord]:
        """Return list of already-applied migrations."""
        cursor = self._conn.execute(
            "SELECT id, filename, applied_at FROM _migrations ORDER BY id"
        )
        return [
            MigrationRecord(id=row[0], filename=row[1], applied_at=row[2])
            for row in cursor.fetchall()
        ]

    def get_pending(self) -> list[str]:
        """Return filenames of migrations not yet applied."""
        applied = {r.filename for r in self.get_applied()}
        return [
            f.name
            for f in self._discover_migrations()
            if f.name not in applied
        ]

    def rollback_last(self) -> str | None:
        """Remove the last migration record (does NOT reverse SQL).

        Returns the filename of the removed record, or ``None`` if no
        migrations exist.

        .. warning::
            This only removes the tracking record. It does **not** execute
            any ``DROP`` or ``ALTER`` statements. Use with caution.
        """
        records = self.get_applied()
        if not records:
            return None
        last = records[-1]
        self._conn.execute("DELETE FROM _migrations WHERE id = ?", (last.id,))
        self._conn.commit()
        logger.info("migration.rolled_back", extra={"migration": last.filename})
        return last.filename

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_migrations_table(self) -> None:
        """Create the ``_migrations`` table if it doesn't exist."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.commit()

    def _discover_migrations(self) -> list[Path]:
        """Return sorted list of ``.sql`` files in the schema directory."""
        if not self._schema_dir.exists():
            return []
        return sorted(self._schema_dir.glob("*.sql"))

    def _record_migration(self, filename: str) -> None:
        """Insert a record into ``_migrations``."""
        self._conn.execute(
            "INSERT INTO _migrations (filename) VALUES (?)",
            (filename,),
        )
        self._conn.commit()
