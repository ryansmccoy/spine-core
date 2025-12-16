"""Declarative base, mixins and type-map for all spine-core ORM models.

Uses SQLAlchemy 2.0 ``DeclarativeBase`` with a ``type_annotation_map``
that maps Python built-in types to portable SA column types.

Mixins
------
* **TimestampMixin** — ``created_at`` / ``updated_at`` with server defaults.
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, Integer, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SpineBase(DeclarativeBase):
    """Shared declarative base for every spine-core table.

    ``type_annotation_map`` lets Mapped columns use plain Python types and
    automatically resolve to the right SA column type:

    * ``str``   → ``Text``
    * ``int``   → ``Integer``
    * ``bool``  → ``Integer``  (SQLite has no native BOOLEAN)
    * ``datetime.datetime`` → ``DateTime``
    * ``dict``  → ``JSON``    (stored as TEXT in SQLite, native JSON elsewhere)
    * ``list``  → ``JSON``
    """

    type_annotation_map = {
        str: Text,
        int: Integer,
        bool: Integer,  # SQLite compat: 0/1
        datetime.datetime: DateTime,
        dict: JSON,
        list: JSON,
    }


class TimestampMixin:
    """Mixin that adds ``created_at`` and ``updated_at`` with server defaults.

    Uses ``datetime('now')`` for SQLite compatibility.  Production DDL for
    PostgreSQL / MySQL / Oracle uses dialect-appropriate ``NOW()`` via the
    per-dialect schema files in ``spine.core.schema/<dialect>/``.
    """

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("(datetime('now'))"),
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        server_default=text("(datetime('now'))"),
        onupdate=text("(datetime('now'))"),
    )
