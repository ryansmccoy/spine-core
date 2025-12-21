"""Optional SQLAlchemy 2.0 ORM layer for spine-core.

Manifesto:
    The raw ``Connection`` protocol is sufficient for simple queries, but
    complex joins, eager loading, and unit-of-work patterns benefit from
    a full ORM.  This package provides SQLAlchemy 2.0 declarative models
    that mirror every ``spine.core.schema/*.sql`` table.

    Strictly **optional** -- all core primitives continue to work with
    raw SQL.  Install with ``pip install spine-core[sqlalchemy]``.

Modules
-------
base        SpineBase (declarative base) + TimestampMixin
session     Engine factory, SpineSession, SAConnectionBridge
tables      All 30 mapped table classes (MigrationTable, ExecutionTable, ...)

Tags:
    spine-core, orm, sqlalchemy, optional, declarative, import-guarded

Doc-Types:
    package-overview, module-index
"""

from __future__ import annotations

try:
    from spine.core.orm.base import SpineBase, TimestampMixin
    from spine.core.orm.session import (
        SAConnectionBridge,
        SpineSession,
        create_spine_engine,
        spine_session_factory,
    )
    from spine.core.orm.tables import *  # noqa: F401,F403
except ImportError as exc:
    raise ImportError(
        "sqlalchemy is required for the ORM layer.  "
        "Install it with:  pip install spine-core[sqlalchemy]"
    ) from exc

__all__ = [
    "SpineBase",
    "TimestampMixin",
    "create_spine_engine",
    "SpineSession",
    "spine_session_factory",
    "SAConnectionBridge",
]
