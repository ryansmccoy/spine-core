"""Connection factory — create database connections from URL strings.

This is the **single entry point** for creating database connections
throughout spine-core.  Every module that needs a connection should use
``create_connection()`` rather than importing backend-specific classes
directly.

Supported URL schemes
---------------------
==================  ==========================================  ============
Scheme              Example                                     Backend
==================  ==========================================  ============
``memory``          ``memory`` or ``:memory:`` or ``None``       SQLite RAM
``sqlite``          ``sqlite:///path/to/file.db``                SQLite file
``(file path)``     ``./data/my.db`` or ``/tmp/spine.db``        SQLite file
``postgresql``      ``postgresql://user:pw@host:port/db``        PostgreSQL
``postgres``        ``postgres://user:pw@host:port/db``          PostgreSQL
==================  ==========================================  ============

Future backends (MySQL, MSSQL, DuckDB, etc.) can be added by
extending ``_BACKEND_REGISTRY``.

Usage
-----
::

    from spine.core.connection import create_connection

    # In-memory (ephemeral)
    conn, info = create_connection()

    # File-based SQLite
    conn, info = create_connection("sqlite:///runs.db")
    conn, info = create_connection("runs.db")

    # PostgreSQL
    conn, info = create_connection("postgresql://spine:spine@localhost:10432/spine")

    # With schema initialization
    conn, info = create_connection("runs.db", init_schema=True)

    print(info)
    # ConnectionInfo(backend='sqlite', persistent=True, url='runs.db')

Design
------
``create_connection()`` returns ``(conn, ConnectionInfo)`` where:

- ``conn`` satisfies the ``Connection`` protocol
  (``.execute()``, ``.fetchone()``, ``.commit()``, etc.)
- ``ConnectionInfo`` is a dataclass with backend metadata

This dual return lets callers make decisions based on what backend
they got (e.g. skip table_counts for PostgreSQL, show file path
for SQLite).

Tier: Basic (spine-core)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── ConnectionInfo ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConnectionInfo:
    """Metadata about a database connection."""

    backend: str
    """Backend identifier: ``"sqlite"``, ``"postgresql"``, etc."""

    persistent: bool
    """Whether data survives process exit."""

    url: str
    """The original URL or path used to create the connection."""

    resolved_path: str | None = None
    """For file-based SQLite, the resolved absolute path."""

    def __repr__(self) -> str:
        parts = [f"backend={self.backend!r}", f"persistent={self.persistent}"]
        if self.resolved_path:
            parts.append(f"path={self.resolved_path!r}")
        else:
            parts.append(f"url={self.url!r}")
        return f"ConnectionInfo({', '.join(parts)})"

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgres(self) -> bool:
        return self.backend == "postgresql"


# ── Backend registry ─────────────────────────────────────────────────────

# Each entry maps a URL prefix to a factory function.
# Factory signature: (url: str) -> tuple[Connection, ConnectionInfo]
#
# New backends are added by extending this dict.  The factory is called
# lazily so imports only happen when the backend is actually used.


def _create_sqlite_memory() -> tuple[Any, ConnectionInfo]:
    """Create an in-memory SQLite connection."""
    from spine.ops.sqlite_conn import SqliteConnection

    conn = SqliteConnection(":memory:")
    info = ConnectionInfo(
        backend="sqlite",
        persistent=False,
        url=":memory:",
    )
    return conn, info


def _create_sqlite_file(path_str: str) -> tuple[Any, ConnectionInfo]:
    """Create a file-based SQLite connection."""
    from spine.ops.sqlite_conn import SqliteConnection

    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = str(path.resolve())

    conn = SqliteConnection(resolved)
    info = ConnectionInfo(
        backend="sqlite",
        persistent=True,
        url=path_str,
        resolved_path=resolved,
    )
    return conn, info


def _create_postgresql(url: str) -> tuple[Any, ConnectionInfo]:
    """Create a PostgreSQL connection via SQLAlchemy bridge."""
    try:
        from spine.core.orm.session import (
            SAConnectionBridge,
            SpineSession,
            create_spine_engine,
        )

        engine = create_spine_engine(url)
        session = SpineSession(bind=engine)
        conn = SAConnectionBridge(session)
        info = ConnectionInfo(
            backend="postgresql",
            persistent=True,
            url=url,
        )
        return conn, info

    except ImportError:
        logger.warning(
            "SQLAlchemy not installed — falling back to in-memory SQLite. "
            "Install spine-core[postgres] for PostgreSQL support."
        )
        return _create_sqlite_memory()

    except Exception as e:
        logger.warning(
            "Cannot connect to PostgreSQL (%s) — "
            "falling back to in-memory SQLite. "
            "Start the database with: docker compose --profile standard up",
            e,
        )
        return _create_sqlite_memory()


# ── URL parsing ──────────────────────────────────────────────────────────


def _parse_url(db: str | None) -> tuple[str, str]:
    """Parse a database URL into (scheme, target).

    Returns
    -------
    tuple[str, str]
        (scheme, target) where scheme is one of:
        ``"memory"``, ``"sqlite"``, ``"postgresql"``, ``"file"``.
    """
    if db is None or db in ("", "memory", ":memory:"):
        return "memory", ":memory:"

    # Explicit URL schemes
    if db.startswith("sqlite:///"):
        path = db[len("sqlite:///"):]
        if not path or path == ":memory:":
            return "memory", ":memory:"
        return "sqlite", path

    if db.startswith("sqlite://"):
        # sqlite:// without triple slash
        path = db[len("sqlite://"):]
        if not path or path == ":memory:":
            return "memory", ":memory:"
        return "sqlite", path

    if db.startswith(("postgresql://", "postgres://")):
        return "postgresql", db

    if db.startswith(("postgresql+", "postgres+")):
        # Handle async drivers: postgresql+asyncpg://...
        # Strip the driver suffix for the sync bridge
        base = db.split("://", 1)
        scheme = base[0].split("+")[0]
        return "postgresql", f"{scheme}://{base[1]}" if len(base) > 1 else db

    # Bare file path — treat as SQLite file
    return "file", db


# ── Main factory ─────────────────────────────────────────────────────────


def create_connection(
    db: str | None = None,
    *,
    init_schema: bool = False,
    data_dir: str | None = None,
) -> tuple[Any, ConnectionInfo]:
    """Create a database connection from a URL, path, or keyword.

    This is the canonical way to get a database connection in spine-core.
    It routes to the appropriate backend based on the URL scheme and
    returns both the connection and metadata about it.

    Parameters
    ----------
    db:
        Database URL, file path, or keyword.  Options:

        - ``None`` or ``"memory"`` — in-memory SQLite (default)
        - ``"path/to/file.db"`` — file-based SQLite
        - ``"sqlite:///path/to/file.db"`` — explicit SQLite URL
        - ``"postgresql://user:pass@host:port/db"`` — PostgreSQL
        - ``"postgres://..."`` — PostgreSQL (alias)

    init_schema:
        If ``True``, apply all spine-core schemas (idempotent
        ``CREATE TABLE IF NOT EXISTS``).

    data_dir:
        For SQLite paths, resolve relative paths within this
        directory.  Defaults to the current directory.

    Returns
    -------
    tuple[Connection, ConnectionInfo]
        The connection object (satisfies ``Connection`` protocol)
        and metadata about the connection.

    Examples
    --------
    ::

        # Ephemeral
        conn, info = create_connection()

        # Persistent SQLite
        conn, info = create_connection("runs.db", init_schema=True)

        # PostgreSQL
        conn, info = create_connection(
            "postgresql://spine:spine@localhost:10432/spine",
            init_schema=True,
        )

        # Check what we got
        if info.is_sqlite:
            print(f"Using SQLite at {info.resolved_path}")
        elif info.is_postgres:
            print("Using PostgreSQL")
    """
    scheme, target = _parse_url(db)

    if scheme == "memory":
        conn, info = _create_sqlite_memory()

    elif scheme in ("sqlite", "file"):
        # Resolve relative paths against data_dir if provided
        if data_dir and not Path(target).is_absolute():
            target = str(Path(data_dir) / target)
        conn, info = _create_sqlite_file(target)

    elif scheme == "postgresql":
        conn, info = _create_postgresql(target)

    else:
        logger.warning(
            "Unknown database URL scheme %r — falling back to in-memory SQLite",
            scheme,
        )
        conn, info = _create_sqlite_memory()

    if init_schema:
        _init_schema(conn)

    return conn, info


def _init_schema(conn: Any) -> list[str]:
    """Apply all spine-core schemas to a connection (idempotent)."""
    from spine.core.schema_loader import apply_all_schemas

    return apply_all_schemas(conn)
