"""Processing repositories — manifest, rejects, work items.

Tags:
    spine-core, repository, processing, manifest, rejects, work-items

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.repository import BaseRepository
from ._helpers import _build_where


class ManifestRepository(BaseRepository):
    """CRUD for the ``core_manifest`` table.

    Replaces inline raw SQL in :mod:`spine.ops.processing`.
    """

    TABLE = "core_manifest"

    COLUMNS = (
        "domain, partition_key, stage, stage_rank, row_count, "
        "metrics_json, execution_id, batch_id, updated_at"
    )

    def get_entry(
        self,
        domain: str,
        partition_key: str,
        stage: str,
    ) -> dict[str, Any] | None:
        """Get a single manifest entry by composite key."""
        return self.query_one(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} "
            f"WHERE domain = {self.ph(1)} "
            f"AND partition_key = {self.ph(1)} "
            f"AND stage = {self.ph(1)}",
            (domain, partition_key, stage),
        )

    def list_entries(
        self,
        *,
        domain: str | None = None,
        partition_key: str | None = None,
        stage: str | None = None,
        execution_id: str | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List manifest entries with filters.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {
                "domain": domain,
                "partition_key": partition_key,
                "stage": stage,
                "execution_id": execution_id,
            },
            self.ph,
        )
        if since:
            clause = f"updated_at >= {self.ph(1)}"
            where = f"{where} AND {clause}" if where != "1=1" else clause
            params = (*params, since)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE {where} "
            f"ORDER BY domain, partition_key, stage_rank "
            f"LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


class RejectRepository(BaseRepository):
    """CRUD for the ``core_rejects`` table.

    Replaces inline raw SQL in :mod:`spine.ops.processing`.
    """

    TABLE = "core_rejects"

    COLUMNS = (
        "domain, partition_key, stage, reason_code, reason_detail, "
        "raw_json, record_key, source_locator, line_number, "
        "execution_id, batch_id, created_at"
    )

    def list_rejects(
        self,
        *,
        domain: str | None = None,
        partition_key: str | None = None,
        stage: str | None = None,
        reason_code: str | None = None,
        execution_id: str | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List reject records with filters.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {
                "domain": domain,
                "partition_key": partition_key,
                "stage": stage,
                "reason_code": reason_code,
                "execution_id": execution_id,
            },
            self.ph,
        )
        if since:
            clause = f"created_at >= {self.ph(1)}"
            where = f"{where} AND {clause}" if where != "1=1" else clause
            params = (*params, since)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE {where} "
            f"ORDER BY created_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def count_by_reason(
        self,
        *,
        domain: str | None = None,
        partition_key: str | None = None,
        stage: str | None = None,
        execution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group rejects by reason_code and return counts."""
        where, params = _build_where(
            {
                "domain": domain,
                "partition_key": partition_key,
                "stage": stage,
                "execution_id": execution_id,
            },
            self.ph,
        )
        return self.query(
            f"SELECT reason_code, COUNT(*) AS cnt "
            f"FROM {self.TABLE} WHERE {where} GROUP BY reason_code "
            f"ORDER BY cnt DESC",
            params,
        )


class WorkItemRepository(BaseRepository):
    """CRUD for the ``core_work_items`` table.

    Replaces inline raw SQL in :mod:`spine.ops.processing`.
    """

    TABLE = "core_work_items"

    COLUMNS = (
        "id, domain, workflow, partition_key, params_json, desired_at, "
        "priority, state, attempt_count, max_attempts, last_error, "
        "last_error_at, next_attempt_at, current_execution_id, "
        "latest_execution_id, locked_by, locked_at, "
        "created_at, updated_at, completed_at"
    )

    def list_items(
        self,
        *,
        domain: str | None = None,
        workflow: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List work items.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"domain": domain, "workflow": workflow, "state": state},
            self.ph,
        )
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE {where} "
            f"ORDER BY priority DESC, created_at ASC "
            f"LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def get_by_id(self, item_id: int) -> dict[str, Any] | None:
        """Get a single work item by ID."""
        return self.query_one(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE id = {self.ph(1)}",
            (item_id,),
        )

    def claim(self, item_id: int, locked_by: str, now: str) -> dict[str, Any] | None:
        """Atomically claim a pending work item.  Returns updated row or None."""
        self.execute(
            f"UPDATE {self.TABLE} SET state='RUNNING', "
            f"locked_by={self.ph(1)}, locked_at={self.ph(1)}, "
            f"attempt_count=attempt_count+1, "
            f"updated_at={self.ph(1)} "
            f"WHERE id={self.ph(1)} AND state='PENDING'",
            (locked_by, now, now, item_id),
        )
        return self.get_by_id(item_id)

    def complete(self, item_id: int, now: str, *, execution_id: str | None = None) -> None:
        """Mark a work item as completed."""
        self.execute(
            f"UPDATE {self.TABLE} SET state='COMPLETE', "
            f"latest_execution_id={self.ph(1)}, "
            f"completed_at={self.ph(1)}, updated_at={self.ph(1)}, "
            f"locked_by=NULL, locked_at=NULL "
            f"WHERE id={self.ph(1)}",
            (execution_id, now, now, item_id),
        )

    def fail(
        self,
        item_id: int,
        error: str,
        now: str,
        *,
        new_state: str = "FAILED",
        next_attempt_at: str | None = None,
    ) -> None:
        """Mark a work item as failed or re-queue for retry."""
        self.execute(
            f"UPDATE {self.TABLE} SET state={self.ph(1)}, "
            f"last_error={self.ph(1)}, last_error_at={self.ph(1)}, "
            f"next_attempt_at={self.ph(1)}, "
            f"locked_by=NULL, locked_at=NULL, "
            f"updated_at={self.ph(1)} "
            f"WHERE id={self.ph(1)}",
            (new_state, error, now, next_attempt_at, now, item_id),
        )

    def cancel(self, item_id: int, now: str) -> None:
        """Cancel a work item."""
        self.execute(
            f"UPDATE {self.TABLE} SET state='CANCELLED', "
            f"locked_by=NULL, locked_at=NULL, updated_at={self.ph(1)} "
            f"WHERE id={self.ph(1)}",
            (now, item_id),
        )

    def retry_failed(
        self,
        *,
        domain: str | None = None,
        workflow: str | None = None,
        now: str = "",
    ) -> int:
        """Reset all failed items back to PENDING.  Returns count affected."""
        where, params = _build_where(
            {"domain": domain, "workflow": workflow},
            self.ph,
            extra_clauses=["state='FAILED'"],
        )
        # Get count first
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        if total > 0:
            self.execute(
                f"UPDATE {self.TABLE} SET state='PENDING', "
                f"attempt_count=0, locked_by=NULL, locked_at=NULL, "
                f"last_error=NULL, last_error_at=NULL, "
                f"updated_at={self.ph(1)} WHERE {where}",
                (now, *params),
            )
        return total
