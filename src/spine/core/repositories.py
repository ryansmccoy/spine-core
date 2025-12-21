"""Repositories for spine-core domain tables.

Each repository class extends :class:`BaseRepository` and provides
typed, dialect-aware CRUD for a specific domain aggregate.  Operations
in ``spine.ops`` should use these repositories instead of
inline raw SQL.

Manifesto:
    Raw SQL scattered across ops modules is unmaintainable, untestable,
    and dialect-dependent. Repositories centralize data access:

    - **Typed methods:** create(), list(), update() with clear signatures
    - **Dialect-aware:** SQL generated via Dialect, not hardcoded
    - **Testable:** Mock at repository boundary, not SQL strings
    - **Auditable:** One place per table for all SQL operations

Architecture::

    ┌───────────────────────────────────────────────────────────────────┐
    │  ops/runs.py,  ops/processing.py,  ops/alerts.py  ...            │
    │  (operation functions — business orchestration)                   │
    └──────────────────────────┬────────────────────────────────────────┘
                               │ uses
                               ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │  repositories.py                                                  │
    │                                                                   │
    │  ExecutionRepository    — core_executions + core_execution_events │
    │  ManifestRepository     — core_manifest                           │
    │  RejectRepository       — core_rejects                            │
    │  WorkItemRepository     — core_work_items                         │
    │  AnomalyRepository      — core_anomalies                         │
    │  AlertRepository        — core_alerts + channels + deliveries     │
    │  DeadLetterRepository   — core_dead_letters                       │
    │  QualityRepository      — core_quality                            │
    │  WorkflowRepository     — core_workflow_runs/steps/events         │
    │  SourceRepository       — core_sources + fetches + cache          │
    └──────────────────────────┬────────────────────────────────────────┘
                               │ inherits
                               ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │  BaseRepository  (spine.core.repository)                          │
    │   .execute()  .query()  .insert()  .ph()  .commit()               │
    └───────────────────────────────────────────────────────────────────┘

Features:
    - **14 repository classes:** One per domain table/aggregate
    - **Consistent API:** list() returns (list[dict], int) tuples
    - **Factory helpers:** _xxx_repo(ctx) pattern for ops modules
    - **Dialect portability:** All SQL via BaseRepository helpers

Guardrails:
    ❌ DON'T: Write raw SQL in ops modules
    ✅ DO: Use the appropriate repository class

    ❌ DON'T: Return raw cursor results from repositories
    ✅ DO: Return typed dicts or (list[dict], int) tuples

Tags:
    repository, sql, domain, refactoring, spine-core,
    data-access, crud, dialect-aware

Doc-Types:
    - API Reference
    - Architecture Documentation
    - Repository Pattern Guide
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spine.core.repository import BaseRepository

# =============================================================================
# Shared helpers
# =============================================================================


@dataclass(frozen=True, slots=True)
class PageSlice:
    """Pagination params used by list operations."""

    limit: int = 50
    offset: int = 0


def _build_where(
    conditions: dict[str, Any],
    dialect_ph: Any,
    *,
    extra_clauses: list[str] | None = None,
) -> tuple[str, tuple]:
    """Build a WHERE clause from a conditions dict.

    Returns ``(where_fragment, params_tuple)``.  Skips ``None`` values.
    ``extra_clauses`` are appended literally (no params).
    """
    parts: list[str] = []
    params: list[Any] = []
    idx = 0
    for col, val in conditions.items():
        if val is None:
            continue
        parts.append(f"{col} = ?")
        params.append(val)
        idx += 1
    if extra_clauses:
        parts.extend(extra_clauses)
    where = " AND ".join(parts) if parts else "1=1"
    return where, tuple(params)


# =============================================================================
# Execution Repository — core_executions + core_execution_events
# =============================================================================


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


# =============================================================================
# Manifest Repository — core_manifest
# =============================================================================


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


# =============================================================================
# Reject Repository — core_rejects
# =============================================================================


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


# =============================================================================
# Work Item Repository — core_work_items
# =============================================================================


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


# =============================================================================
# Anomaly Repository — core_anomalies
# =============================================================================


class AnomalyRepository(BaseRepository):
    """CRUD for the ``core_anomalies`` table.

    Replaces inline raw SQL in :mod:`spine.ops.anomalies`.
    """

    TABLE = "core_anomalies"

    def list_anomalies(
        self,
        *,
        workflow: str | None = None,
        severity: str | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List anomalies with filters.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"workflow": workflow, "severity": severity},
            self.ph,
        )
        if since:
            clause = f"detected_at >= {self.ph(1)}"
            where = f"{where} AND {clause}" if where != "1=1" else clause
            params = (*params, since)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.TABLE} WHERE {where} "
            f"ORDER BY detected_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


# =============================================================================
# Alert Repository — core_alerts + core_alert_channels + core_alert_deliveries
# =============================================================================


class AlertRepository(BaseRepository):
    """CRUD for alert-related tables.

    Replaces inline raw SQL in :mod:`spine.ops.alerts`.
    """

    CHANNELS_TABLE = "core_alert_channels"
    ALERTS_TABLE = "core_alerts"
    DELIVERIES_TABLE = "core_alert_deliveries"

    # -- channels --------------------------------------------------------------

    def list_channels(
        self,
        *,
        enabled: bool | None = None,
        channel_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List alert channels.  Returns ``(rows, total)``."""
        conds: dict[str, Any] = {"channel_type": channel_type}
        if enabled is not None:
            conds["enabled"] = 1 if enabled else 0
        where, params = _build_where(conds, self.ph)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.CHANNELS_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.CHANNELS_TABLE} WHERE {where} "
            f"ORDER BY name ASC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        """Get a channel by ID."""
        return self.query_one(
            f"SELECT * FROM {self.CHANNELS_TABLE} WHERE id = {self.ph(1)}",
            (channel_id,),
        )

    def create_channel(self, data: dict[str, Any]) -> None:
        """Insert a new alert channel."""
        self.insert(self.CHANNELS_TABLE, data)

    def delete_channel(self, channel_id: str) -> None:
        """Delete an alert channel by ID."""
        self.execute(
            f"DELETE FROM {self.CHANNELS_TABLE} WHERE id = {self.ph(1)}",
            (channel_id,),
        )

    def update_channel(self, channel_id: str, updates: dict[str, Any]) -> None:
        """Update fields on an alert channel."""
        if not updates:
            return
        sets = ", ".join(f"{k} = {self.ph(1)}" for k in updates)
        vals = tuple(updates.values())
        self.execute(
            f"UPDATE {self.CHANNELS_TABLE} SET {sets} WHERE id = {self.ph(1)}",
            (*vals, channel_id),
        )

    # -- alerts ----------------------------------------------------------------

    def list_alerts(
        self,
        *,
        severity: str | None = None,
        domain: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List alerts.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"severity": severity, "domain": domain, "source": source},
            self.ph,
        )
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.ALERTS_TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.ALERTS_TABLE} WHERE {where} "
            f"ORDER BY created_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total

    def create_alert(self, data: dict[str, Any]) -> None:
        """Insert a new alert."""
        self.insert(self.ALERTS_TABLE, data)

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        """Get a single alert by ID."""
        return self.query_one(
            f"SELECT * FROM {self.ALERTS_TABLE} WHERE id = {self.ph(1)}",
            (alert_id,),
        )

    def get_alert_metadata(self, alert_id: str) -> str | None:
        """Get metadata_json for acknowledge workflow."""
        row = self.query_one(
            f"SELECT metadata_json FROM {self.ALERTS_TABLE} "
            f"WHERE id = {self.ph(1)}",
            (alert_id,),
        )
        return row.get("metadata_json") if row else None

    def update_alert_metadata(self, alert_id: str, metadata_json: str) -> None:
        """Update metadata_json field on an alert."""
        self.execute(
            f"UPDATE {self.ALERTS_TABLE} SET metadata_json = {self.ph(1)} "
            f"WHERE id = {self.ph(1)}",
            (metadata_json, alert_id),
        )

    # -- deliveries ------------------------------------------------------------

    def list_deliveries(
        self,
        *,
        alert_id: str | None = None,
        channel_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List alert deliveries.  Returns ``(rows, total)``."""
        where, params = _build_where(
            {"alert_id": alert_id, "channel_id": channel_id, "status": status},
            self.ph,
        )
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.DELIVERIES_TABLE} WHERE {where}",
            params,
        )
        total = (count_row or {}).get("cnt", 0)

        rows = self.query(
            f"SELECT * FROM {self.DELIVERIES_TABLE} WHERE {where} "
            f"ORDER BY created_at DESC LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


# =============================================================================
# Dead Letter Repository — core_dead_letters
# =============================================================================


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


# =============================================================================
# Quality Repository — core_quality
# =============================================================================


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


# =============================================================================
# Lock Repository — core_concurrency_locks + core_schedule_locks
# =============================================================================


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


# =============================================================================
# Workflow Repository — core_workflow_runs + steps + events
# =============================================================================


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


# =============================================================================
# Source Repository — core_sources + core_source_fetches + core_source_cache
# =============================================================================


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


# =============================================================================
# Schedule Repository — core_schedules  (extends existing in scheduling/)
# =============================================================================


class ScheduleOpsRepository(BaseRepository):
    """CRUD for the ``core_schedules`` table used by ops/schedules.py.

    This complements the existing ``ScheduleRepository`` in
    ``spine.core.scheduling.repository`` — that one is an older standalone
    implementation.  This version extends ``BaseRepository`` for consistency
    with the rest of the repository layer.
    """

    TABLE = "core_schedules"

    COLUMNS = (
        "id, name, target_type, target_name, params, schedule_type, "
        "cron_expression, interval_seconds, run_at, timezone, enabled, "
        "max_instances, misfire_grace_seconds, last_run_at, next_run_at, "
        "last_run_status, created_at, updated_at, created_by, version"
    )

    def list_schedules(self) -> list[dict[str, Any]]:
        """List all schedules ordered by name."""
        return self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} ORDER BY name ASC"
        )

    def get_by_id(self, schedule_id: str) -> dict[str, Any] | None:
        """Get a schedule by ID."""
        return self.query_one(
            f"SELECT * FROM {self.TABLE} WHERE id = {self.ph(1)}",
            (schedule_id,),
        )

    def create_schedule(self, data: dict[str, Any]) -> None:
        """Insert a new schedule."""
        self.insert(self.TABLE, data)

    def update_schedule(self, schedule_id: str, updates: dict[str, Any]) -> None:
        """Update fields on a schedule."""
        if not updates:
            return
        sets = ", ".join(f"{k} = {self.ph(1)}" for k in updates)
        vals = tuple(updates.values())
        self.execute(
            f"UPDATE {self.TABLE} SET {sets} WHERE id = {self.ph(1)}",
            (*vals, schedule_id),
        )

    def delete_schedule(self, schedule_id: str) -> None:
        """Delete a schedule."""
        self.execute(
            f"DELETE FROM {self.TABLE} WHERE id = {self.ph(1)}",
            (schedule_id,),
        )


# =============================================================================
# Calc Dependency / Expected Schedule / Data Readiness repos
# =============================================================================


class CalcDependencyRepository(BaseRepository):
    """CRUD for ``core_calc_dependencies``."""

    TABLE = "core_calc_dependencies"

    COLUMNS = (
        "id, calc_domain, calc_operation, calc_table, "
        "depends_on_domain, depends_on_table, dependency_type, "
        "description, created_at"
    )

    def list_deps(
        self,
        *,
        calc_domain: str | None = None,
        calc_operation: str | None = None,
        depends_on_domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where, params = _build_where(
            {
                "calc_domain": calc_domain,
                "calc_operation": calc_operation,
                "depends_on_domain": depends_on_domain,
            },
            self.ph,
        )
        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)
        rows = self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE {where} "
            f"ORDER BY calc_domain, calc_operation "
            f"LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


class ExpectedScheduleRepository(BaseRepository):
    """CRUD for ``core_expected_schedules``."""

    TABLE = "core_expected_schedules"

    COLUMNS = (
        "id, domain, workflow, schedule_type, cron_expression, "
        "partition_template, partition_values, expected_delay_hours, "
        "preliminary_hours, description, is_active, created_at, updated_at"
    )

    def list_schedules(
        self,
        *,
        domain: str | None = None,
        workflow: str | None = None,
        schedule_type: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conds: dict[str, Any] = {
            "domain": domain,
            "workflow": workflow,
            "schedule_type": schedule_type,
        }
        if is_active is not None:
            conds["is_active"] = 1 if is_active else 0
        where, params = _build_where(conds, self.ph)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)
        rows = self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE {where} "
            f"ORDER BY domain, workflow "
            f"LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


class DataReadinessRepository(BaseRepository):
    """CRUD for ``core_data_readiness``."""

    TABLE = "core_data_readiness"

    COLUMNS = (
        "id, domain, partition_key, is_ready, ready_for, "
        "all_partitions_present, all_stages_complete, "
        "no_critical_anomalies, dependencies_current, "
        "age_exceeds_preliminary, blocking_issues, "
        "certified_at, certified_by, created_at, updated_at"
    )

    def check_readiness(
        self,
        *,
        domain: str | None = None,
        partition_key: str | None = None,
        ready_for: str | None = None,
        is_ready: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conds: dict[str, Any] = {
            "domain": domain,
            "partition_key": partition_key,
            "ready_for": ready_for,
        }
        if is_ready is not None:
            conds["is_ready"] = 1 if is_ready else 0
        where, params = _build_where(conds, self.ph)

        count_row = self.query_one(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE} WHERE {where}", params,
        )
        total = (count_row or {}).get("cnt", 0)
        rows = self.query(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE {where} "
            f"ORDER BY domain, partition_key "
            f"LIMIT {self.ph(1)} OFFSET {self.ph(1)}",
            (*params, limit, offset),
        )
        return rows, total


# =============================================================================
# Public API
# =============================================================================


__all__ = [
    "PageSlice",
    "ExecutionRepository",
    "ManifestRepository",
    "RejectRepository",
    "WorkItemRepository",
    "AnomalyRepository",
    "AlertRepository",
    "DeadLetterRepository",
    "QualityRepository",
    "LockRepository",
    "WorkflowRunRepository",
    "SourceRepository",
    "ScheduleOpsRepository",
    "CalcDependencyRepository",
    "ExpectedScheduleRepository",
    "DataReadinessRepository",
]
