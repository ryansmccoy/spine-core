"""Execution repository — core_executions + core_execution_events.

Tags:
    spine-core, repository, execution

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.repository import BaseRepository
from ._helpers import _build_where


class ExecutionRepository(BaseRepository):
    """CRUD for the ``core_executions`` and ``core_execution_events`` tables.

    Replaces inline raw SQL in :mod:`spine.ops.runs`.
    """

    TABLE = "core_executions"
    EVENTS_TABLE = "core_execution_events"

    # -- reads -----------------------------------------------------------------

    def get_by_id(self, execution_id: str) -> dict[str, Any] | None:
        """Fetch a single execution row by primary key."""
        return self.query_one(
            f"SELECT * FROM {self.TABLE} WHERE id = {self.ph(1)}",
            (execution_id,),
        )

    def list_executions(
        self,
        *,
        workflow: str | None = None,
        status: str | None = None,
        lane: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List executions with optional filters.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"workflow": workflow, "status": status, "lane": lane},
            self.ph,
        )
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.TABLE} WHERE {where} "
            f"ORDER BY started_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    # -- writes ----------------------------------------------------------------

    def create_execution(self, data: dict[str, Any]) -> None:
        """Insert a new execution row."""
        self.insert(self.TABLE, data)

    def update_status(self, execution_id: str, status: str) -> None:
        """Update execution status (e.g. cancel, complete, fail)."""
        self.execute(
            f"UPDATE {self.TABLE} SET status = {self.ph(1)} WHERE id = {self.ph(1)}",
            (status, execution_id),
        )

    # -- events ----------------------------------------------------------------

    def add_event(self, data: dict[str, Any]) -> None:
        """Insert an execution event row."""
        self.insert(self.EVENTS_TABLE, data)

    def list_events(
        self,
        execution_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List events for an execution.  Returns ``(rows, total)``."""
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.EVENTS_TABLE} "
            f"WHERE execution_id = {self.ph(1)}",
            (execution_id,),
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.EVENTS_TABLE} "
            f"WHERE execution_id = {self.ph(1)} "
            f"ORDER BY timestamp ASC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (execution_id, limit, offset),
        )
        return rows, total
