"""Source repository — sources, fetches, cache, database connections.

Tags:
    spine-core, repository, sources

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.repository import BaseRepository
from ._helpers import _build_where


class SourceRepository(BaseRepository):
    """CRUD for source-related tables.

    Replaces inline raw SQL in :mod:`spine.ops.sources`.
    """

    SOURCES_TABLE = "core_sources"
    FETCHES_TABLE = "core_source_fetches"
    CACHE_TABLE = "core_source_cache"
    DB_CONN_TABLE = "core_database_connections"

    # -- sources ---------------------------------------------------------------

    def list_sources(
        self,
        *,
        source_type: str | None = None,
        domain: str | None = None,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List sources.  Returns ``(rows, total)``."""
        conds: dict[str, Any] = {"source_type": source_type, "domain": domain}
        if enabled is not None:
            conds["enabled"] = 1 if enabled else 0
        where, params = _build_where(conds, self.ph)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.SOURCES_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.SOURCES_TABLE} WHERE {where} "
            f"ORDER BY created_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        """Get source by ID."""
        return self.query_one(
            f"SELECT * FROM {self.SOURCES_TABLE} WHERE id = {self.ph(1)}",
            (source_id,),
        )

    def create_source(self, data: dict[str, Any]) -> None:
        """Register a new source."""
        self.insert(self.SOURCES_TABLE, data)

    def delete_source(self, source_id: str) -> None:
        """Delete a source."""
        self.execute(
            f"DELETE FROM {self.SOURCES_TABLE} WHERE id = {self.ph(1)}",
            (source_id,),
        )

    def set_enabled(self, source_id: str, enabled: bool, now: str) -> None:
        """Enable or disable a source."""
        self.execute(
            f"UPDATE {self.SOURCES_TABLE} SET enabled = {self.ph(1)}, "
            f"updated_at = {self.ph(1)} WHERE id = {self.ph(1)}",
            (1 if enabled else 0, now, source_id),
        )

    # -- fetches ---------------------------------------------------------------

    def list_fetches(
        self,
        *,
        source_id: str | None = None,
        source_name: str | None = None,
        status: str | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List source fetches.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"source_id": source_id, "source_name": source_name, "status": status},
            self.ph,
        )
        if since:
            clause = f"started_at >= {self.ph(1)}"
            where = f"{where} AND {clause}" if where != "1=1" else clause
            params = (*params, since)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.FETCHES_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.FETCHES_TABLE} WHERE {where} "
            f"ORDER BY started_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    # -- cache -----------------------------------------------------------------

    def list_cache(
        self,
        *,
        source_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List source cache entries.  Returns ``(rows, total)``."""
        where, params = _build_where({"source_id": source_id}, self.ph)
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.CACHE_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.CACHE_TABLE} WHERE {where} "
            f"ORDER BY fetched_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def invalidate_cache(self, source_id: str) -> int:
        """Delete all cache entries for a source. Returns count deleted."""
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.CACHE_TABLE} "
            f"WHERE source_id = {self.ph(1)}",
            (source_id,),
        )
        total = (count_row or {}).get("cnt", 0)
        if total:
            self.execute(
                f"DELETE FROM {self.CACHE_TABLE} "
                f"WHERE source_id = {self.ph(1)}",
                (source_id,),
            )
        return total

    # -- database connections --------------------------------------------------

    def list_db_connections(
        self,
        *,
        dialect: str | None = None,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List database connections.  Returns ``(rows, total)``."""
        conds: dict[str, Any] = {"dialect": dialect}
        if enabled is not None:
            conds["enabled"] = 1 if enabled else 0
        where, params = _build_where(conds, self.ph)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.DB_CONN_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.DB_CONN_TABLE} WHERE {where} "
            f"ORDER BY created_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def create_db_connection(self, data: dict[str, Any]) -> None:
        """Register a new database connection."""
        self.insert(self.DB_CONN_TABLE, data)

    def delete_db_connection(self, connection_id: str) -> None:
        """Delete a database connection."""
        self.execute(
            f"DELETE FROM {self.DB_CONN_TABLE} WHERE id = {self.ph(1)}",
            (connection_id,),
        )

    def get_db_connection(self, connection_id: str) -> dict[str, Any] | None:
        """Get a database connection by ID."""
        return self.query_one(
            f"SELECT * FROM {self.DB_CONN_TABLE} WHERE id = {self.ph(1)}",
            (connection_id,),
        )
