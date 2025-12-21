"""SQLAlchemy engine factory, scoped session, and Connection bridge.

Manifesto:
    ORM and raw-SQL code must share a single abstraction so ops modules
    work identically whether the caller uses a raw ``sqlite3.Connection``
    or a ``Session``.  ``SAConnectionBridge`` wraps a SA Session to
    satisfy the ``spine.core.protocols.Connection`` protocol.

This module provides:

* ``create_spine_engine``  -- Create a SA engine from a URL or config dict.
* ``SpineSession``         -- A pre-configured ``sessionmaker`` subclass.
* ``SAConnectionBridge``   -- Wraps a SA ``Session`` to satisfy the
  ``spine.core.protocols.Connection`` protocol, enabling ORM and raw-SQL
  code to share a single abstraction.

Tags:
    spine-core, orm, sqlalchemy, session, engine, bridge, connection

Doc-Types:
    api-reference
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_spine_engine(
    url: str = "sqlite:///spine.db",
    *,
    echo: bool = False,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: int | None = None,
    **kwargs: Any,
) -> Engine:
    """Create a SQLAlchemy engine with sane defaults.

    Parameters
    ----------
    url:
        Database URL (``sqlite:///…``, ``postgresql://…``, etc.)
    echo:
        If ``True``, log all SQL to stdout.
    pool_size, max_overflow, pool_timeout:
        Connection pool parameters (ignored for SQLite).
    **kwargs:
        Extra arguments forwarded to ``sqlalchemy.create_engine``.
    """

    # SQLite-specific tweaks
    if url.startswith("sqlite"):
        # Enable WAL mode for better concurrency
        kwargs.setdefault("connect_args", {"check_same_thread": False})
        # Foreign keys off by default in SQLite — enable via event listener
        from sqlalchemy import event

        engine = _sa_create_engine(url, echo=echo, **kwargs)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _rec: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    # Non-SQLite: apply pool settings
    pool_kwargs: dict[str, Any] = {}
    if pool_size is not None:
        pool_kwargs["pool_size"] = pool_size
    if max_overflow is not None:
        pool_kwargs["max_overflow"] = max_overflow
    if pool_timeout is not None:
        pool_kwargs["pool_timeout"] = pool_timeout

    return _sa_create_engine(url, echo=echo, **pool_kwargs, **kwargs)


class SpineSession(Session):
    """Pre-configured session with ``expire_on_commit=False``.

    Prevents lazy-load surprises after commit.  Can be used directly or
    via ``sessionmaker(class_=SpineSession)``.
    """

    def __init__(self, bind: Engine | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("expire_on_commit", False)
        super().__init__(bind=bind, **kwargs)


def spine_session_factory(engine: Engine) -> sessionmaker[SpineSession]:
    """Return a ``sessionmaker`` bound to *engine* that produces ``SpineSession`` instances."""
    return sessionmaker(bind=engine, class_=SpineSession)


class SAConnectionBridge:
    """Adapter that makes a SQLAlchemy ``Session`` look like ``spine.core.protocols.Connection``.

    This lets callers that depend on the ``Connection`` protocol re-use the
    same ORM session when mixing raw-SQL writes with ORM operations.

    Implements: ``execute``, ``executemany``, ``fetchone``, ``fetchall``,
    ``commit``, ``rollback``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._last_result: Any = None

    # --- execute / executemany ---

    def execute(self, sql: str, parameters: Sequence[Any] | None = None) -> SAConnectionBridge:  # type: ignore[override]
        stmt = text(sql)
        if parameters:
            # Convert positional (?, ?) → (:p0, :p1) for SA text()
            mapping = {f"p{i}": v for i, v in enumerate(parameters)}
            stmt = text(sql.replace("?", "").replace("?", ""))  # noop — see below
            # Actually, SA text() needs named params.  We rewrite ? placeholders.
            rewritten, idx = [], 0
            for ch in sql:
                if ch == "?":
                    rewritten.append(f":p{idx}")
                    idx += 1
                else:
                    rewritten.append(ch)
            stmt = text("".join(rewritten))
            self._last_result = self._session.execute(stmt, mapping)
        else:
            self._last_result = self._session.execute(stmt)
        return self

    def executemany(self, sql: str, seq_of_parameters: Sequence[Sequence[Any]]) -> None:  # type: ignore[override]
        for params in seq_of_parameters:
            self.execute(sql, params)

    # --- fetch ---

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._last_result is None:
            return None
        row = self._last_result.fetchone()
        return tuple(row) if row is not None else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self._last_result is None:
            return []
        return [tuple(r) for r in self._last_result.fetchall()]

    # --- transaction ---

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    # --- properties ---

    @property
    def description(self) -> list[tuple[str, ...]] | None:
        """DB-API 2.0 compatible description from the last result.

        Returns a list of (column_name, ...) tuples that
        :class:`~spine.core.repository.BaseRepository` uses to build dicts.
        """
        if self._last_result is None:
            return None
        keys = list(self._last_result.keys())
        # DB-API 2.0 description is list of 7-tuples; only name is used
        return [(k, None, None, None, None, None, None) for k in keys]

    @property
    def session(self) -> Session:
        """Access the underlying SA session (e.g., for ORM queries)."""
        return self._session
