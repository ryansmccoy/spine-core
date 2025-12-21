"""Source & connection table definitions — sources, fetches, cache, DB connections.

Tags:
    spine-core, orm, sqlalchemy, tables, sources

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spine.core.orm.base import SpineBase

_NOW = text("(datetime('now'))")


class SourceTable(SpineBase):
    __tablename__ = "core_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    fetches: Mapped[list[SourceFetchTable]] = relationship(
        "SourceFetchTable", backref="source"
    )
    cache_entries: Mapped[list[SourceCacheTable]] = relationship(
        "SourceCacheTable", backref="source"
    )


class SourceFetchTable(SpineBase):
    __tablename__ = "core_source_fetches"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_sources.id")
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int | None] = mapped_column(Integer)
    byte_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id")
    )
    capture_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class SourceCacheTable(SpineBase):
    __tablename__ = "core_source_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_sources.id")
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_path: Mapped[str | None] = mapped_column(Text)
    # content_blob omitted -- binary handled at DB layer
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    last_accessed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)


class DatabaseConnectionTable(SpineBase):
    __tablename__ = "core_database_connections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    dialect: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str | None] = mapped_column(Text)
    port: Mapped[int | None] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    password_ref: Mapped[str | None] = mapped_column(Text)
    pool_size: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_overflow: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    pool_timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    last_connected_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)
