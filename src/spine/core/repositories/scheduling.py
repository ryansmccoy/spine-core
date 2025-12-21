"""Scheduling repositories — schedules, calc dependencies, expected schedules, data readiness.

Tags:
    spine-core, repository, scheduling, readiness

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.repository import BaseRepository
from ._helpers import _build_where


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
