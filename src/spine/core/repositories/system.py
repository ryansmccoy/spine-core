"""System repositories — dead letters, quality, locks, workflow runs.

Tags:
    spine-core, repository, dlq, quality, locks, workflows

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.repository import BaseRepository
from ._helpers import _build_where


class DeadLetterRepository(BaseRepository):
    """CRUD for the ``core_dead_letters`` table.

    Replaces inline raw SQL in :mod:`spine.ops.dlq`.
    """

    TABLE = "core_dead_letters"

    def list_dead_letters(
        self,
        *,
        workflow: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List dead letters.  Returns ``(rows, total)``."""
        where, params = _build_where({"workflow": workflow}, self.ph)
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.TABLE} WHERE {where} "
            f"ORDER BY created_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def exists(self, dead_letter_id: str) -> bool:
        """Check if a dead letter exists."""
        row = self.query_one(
            f"SELECT id FROM {self.TABLE} WHERE id = {self.ph(1)}",
            (dead_letter_id,),
        )
        return row is not None

    def increment_replay(self, dead_letter_id: str) -> None:
        """Increment replay count for a dead letter."""
        self.execute(
            f"UPDATE {self.TABLE} SET retry_count = retry_count + 1 "
            f"WHERE id = {self.ph(1)}",
            (dead_letter_id,),
        )


class QualityRepository(BaseRepository):
    """CRUD for the ``core_quality`` table.

    Replaces inline raw SQL in :mod:`spine.ops.quality`.
    """

    TABLE = "core_quality"

    def aggregate_by_workflow(
        self,
        *,
        workflow: str | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Aggregate quality results by domain.

        Returns ``(rows, distinct_domain_count)``.  Column aliases match
        the :class:`~spine.ops.responses.QualityResultSummary` fields:
        ``workflow``, ``checks_passed``, ``checks_failed``, ``score``,
        ``run_at``.
        """
        where, params = _build_where({"domain": workflow}, self.ph)
        if since:
            clause = f"created_at >= {self.ph(1)}"
            where = f"{where} AND {clause}" if where != "1=1" else clause
            params = (*params, since)

        count_row = self.query_one(
            f"SELECT COUNT(DISTINCT domain) AS cnt FROM {self.TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT "
            f"domain AS workflow, "
            f"SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS checks_passed, "
            f"SUM(CASE WHEN status != 'PASS' THEN 1 ELSE 0 END) AS checks_failed, "
            f"ROUND("
            f"CAST(SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS REAL) "
            f"/ MAX(COUNT(*), 1), 4) AS score, "
            f"MAX(created_at) AS run_at "
            f"FROM {self.TABLE} WHERE {where} "
            f"GROUP BY domain ORDER BY run_at DESC "
            f"LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


class LockRepository(BaseRepository):
    """CRUD for lock tables.

    Replaces inline raw SQL in :mod:`spine.ops.locks`.
    """

    LOCKS_TABLE = "core_concurrency_locks"
    SCHEDULE_LOCKS_TABLE = "core_schedule_locks"

    def list_locks(self) -> list[dict[str, Any]]:
        """List all concurrency locks."""
        return self.query(
            f"SELECT lock_key, execution_id AS owner, acquired_at, expires_at "
            f"FROM {self.LOCKS_TABLE} "
            f"ORDER BY acquired_at DESC"
        )

    def release_lock(self, lock_key: str) -> None:
        """Release a concurrency lock."""
        self.execute(
            f"DELETE FROM {self.LOCKS_TABLE} WHERE lock_key = {self.ph(1)}",
            (lock_key,),
        )

    def list_schedule_locks(self) -> tuple[list[dict[str, Any]], int]:
        """List schedule locks.  Returns ``(rows, total)``."""
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.SCHEDULE_LOCKS_TABLE}"
        )
        total = (count_row or {}).get("cnt", 0)
        rows = self.query(
            f"SELECT schedule_id, locked_by, locked_at, expires_at "
            f"FROM {self.SCHEDULE_LOCKS_TABLE}"
        )
        return rows, total

    def release_schedule_lock(self, schedule_id: str) -> None:
        """Release a schedule lock."""
        self.execute(
            f"DELETE FROM {self.SCHEDULE_LOCKS_TABLE} "
            f"WHERE schedule_id = {self.ph(1)}",
            (schedule_id,),
        )


class WorkflowRunRepository(BaseRepository):
    """CRUD for workflow-related tables.

    Replaces inline raw SQL in :mod:`spine.ops.workflows` and parts of runs.py.
    """

    RUNS_TABLE = "core_workflow_runs"
    STEPS_TABLE = "core_workflow_steps"
    EVENTS_TABLE = "core_workflow_events"

    def list_steps(
        self,
        run_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List workflow steps for a run.  Returns ``(rows, total)``."""
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.STEPS_TABLE} "
            f"WHERE run_id = {self.ph(1)}",
            (run_id,),
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.STEPS_TABLE} "
            f"WHERE run_id = {self.ph(1)} "
            f"ORDER BY step_order ASC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (run_id, limit, offset),
        )
        return rows, total

    def list_events(
        self,
        *,
        run_id: str | None = None,
        step_id: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List workflow events.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"run_id": run_id, "step_id": step_id, "event_type": event_type},
            self.ph,
        )
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.EVENTS_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.EVENTS_TABLE} WHERE {where} "
            f"ORDER BY timestamp ASC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total
