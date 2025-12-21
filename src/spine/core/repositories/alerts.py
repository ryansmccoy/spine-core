"""Alert & anomaly repositories.

Tags:
    spine-core, repository, alerts, anomalies

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.repository import BaseRepository
from ._helpers import _build_where


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
