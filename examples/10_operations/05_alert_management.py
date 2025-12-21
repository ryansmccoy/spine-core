#!/usr/bin/env python3
"""Alert Management — Channels, alerts, acknowledgement, and delivery tracking.

WHY OPS-LAYER ALERTING
──────────────────────
The framework alerting system (08_framework/05) sends alerts; the ops
layer *manages* the full lifecycle — creating channels, persisting alerts,
tracking deliveries, throttling duplicates, and acknowledging resolved
issues.

ARCHITECTURE
────────────
    Operation/Workflow failure
         │
         ▼
    AlertRegistry.send_to_all()        ← 08_framework/05
         │
         ▼
    ops.alerts.fire_alert()            ← this example
    ops.alerts.list_channels()
    ops.alerts.acknowledge_alert()
    ops.alerts.delivery_history()
         │
         ▼
    ┌──────────────────────────────────────┐
    │ core_alert_channels              │
    │ core_alerts                      │
    │ core_alert_deliveries            │
    │ core_alert_throttle              │
    └──────────────────────────────────────┘

BEST PRACTICES
──────────────
• Create channels at startup (ops layer ensures idempotency).
• Use throttle rules to prevent alert storms.
• Acknowledge alerts to clear dashboard noise.
• Query delivery_history() for SLA compliance reporting.

Run: python examples/10_operations/05_alert_management.py

See Also:
    08_framework/05_alert_routing — framework-level alerting
    06_source_management — source failure alerts
"""

import sys
from pathlib import Path

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env

from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.alerts import (
    list_alert_channels,
    get_alert_channel,
    create_alert_channel,
    delete_alert_channel,
    update_alert_channel,
    list_alerts,
    create_alert,
    acknowledge_alert,
    list_alert_deliveries,
)
from spine.ops.requests import (
    ListAlertChannelsRequest,
    CreateAlertChannelRequest,
    CreateAlertRequest,
    ListAlertsRequest,
    ListAlertDeliveriesRequest,
)


def main():
    print("=" * 60)
    print("Operations Layer — Alert Management")
    print("=" * 60)
    
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection()
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")

    apply_all_schemas(conn)
    ctx = OperationContext(conn=conn, caller="example")

    # --- 1. Empty channels ------------------------------------------------
    print("\n[1] List Alert Channels (empty)")

    result = list_alert_channels(ctx, ListAlertChannelsRequest())
    assert result.success
    print(f"  total : {result.total}")

    # --- 2. Create channels -----------------------------------------------
    print("\n[2] Create Alert Channels")

    channels = [
        CreateAlertChannelRequest(
            name="slack-critical",
            channel_type="slack",
            config={"webhook_url": "https://hooks.slack.com/test", "channel": "#alerts"},
            min_severity="CRITICAL",
            domains=["equity", "otc"],
            throttle_minutes=1,
        ),
        CreateAlertChannelRequest(
            name="email-ops",
            channel_type="email",
            config={"to": "ops@example.com", "from": "spine@example.com"},
            min_severity="ERROR",
            throttle_minutes=15,
        ),
        CreateAlertChannelRequest(
            name="webhook-monitoring",
            channel_type="webhook",
            config={"url": "https://monitoring.example.com/api/alerts"},
            min_severity="WARNING",
            enabled=False,
        ),
    ]

    channel_ids = []
    for req in channels:
        res = create_alert_channel(ctx, req)
        assert res.success, f"Failed: {res.error}"
        channel_ids.append(res.data["id"])
        print(f"  + {res.data['id']}  {req.name:25s}  {req.channel_type}")

    # --- 3. List all channels ---------------------------------------------
    print("\n[3] List All Channels")

    result = list_alert_channels(ctx, ListAlertChannelsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for ch in result.data:
        print(f"  {ch.id}  {ch.name:25s}  type={ch.channel_type}  enabled={ch.enabled}")

    # --- 4. Filter by type ------------------------------------------------
    print("\n[4] Filter Channels by Type = 'email'")

    result = list_alert_channels(ctx, ListAlertChannelsRequest(channel_type="email"))
    assert result.success
    print(f"  total : {result.total}")
    for ch in result.data:
        print(f"  {ch.id}  {ch.name}  {ch.channel_type}")

    # --- 5. Filter by enabled status --------------------------------------
    print("\n[5] Filter Channels by Enabled = False")

    result = list_alert_channels(ctx, ListAlertChannelsRequest(enabled=False))
    assert result.success
    print(f"  total : {result.total}")
    for ch in result.data:
        print(f"  {ch.id}  {ch.name}  enabled={ch.enabled}")

    # --- 6. Get channel detail --------------------------------------------
    print("\n[6] Get Channel Detail")

    detail = get_alert_channel(ctx, channel_ids[0])
    assert detail.success
    d = detail.data
    print(f"  id             : {d.id}")
    print(f"  name           : {d.name}")
    print(f"  type           : {d.channel_type}")
    print(f"  min_severity   : {d.min_severity}")
    print(f"  throttle_min   : {d.throttle_minutes}")
    print(f"  domains        : {d.domains}")

    # --- 7. Update channel ------------------------------------------------
    print("\n[7] Update Channel (disable + change severity)")

    upd = update_alert_channel(ctx, channel_ids[0], enabled=False, min_severity="WARNING")
    assert upd.success
    print(f"  updated : {upd.data}")

    # Verify
    verify = get_alert_channel(ctx, channel_ids[0])
    print(f"  enabled now    : {verify.data.enabled}")
    print(f"  min_severity   : {verify.data.min_severity}")

    # --- 8. Create alerts -------------------------------------------------
    print("\n[8] Create Alerts")

    alerts_data = [
        CreateAlertRequest(
            severity="CRITICAL",
            title="Price feed stale > 30 min",
            message="Equity price feed has not updated in 32 minutes",
            source="equity.price.monitor",
            domain="equity",
            execution_id="exec-001",
        ),
        CreateAlertRequest(
            severity="ERROR",
            title="OTC validation failures above threshold",
            message="17% of OTC records failed schema validation (threshold: 5%)",
            source="otc.ingest.validator",
            domain="otc",
            error_category="DATA_QUALITY",
        ),
        CreateAlertRequest(
            severity="WARNING",
            title="Disk usage above 80%",
            message="Operation storage volume at 83% capacity",
            source="infra.monitor",
        ),
        CreateAlertRequest(
            severity="INFO",
            title="Daily reconciliation complete",
            message="All 3 domains reconciled successfully",
            source="recon.scheduler",
        ),
    ]

    alert_ids = []
    for req in alerts_data:
        res = create_alert(ctx, req)
        assert res.success, f"Failed: {res.error}"
        alert_ids.append(res.data["id"])
        print(f"  + {res.data['id']}  [{req.severity:8s}]  {req.title}")

    # --- 9. List all alerts -----------------------------------------------
    print("\n[9] List All Alerts")

    result = list_alerts(ctx, ListAlertsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for a in result.data:
        print(f"  {a.id}  [{a.severity:8s}]  {a.title}")

    # --- 10. Filter alerts by severity ------------------------------------
    print("\n[10] Filter Alerts by Severity = 'CRITICAL'")

    result = list_alerts(ctx, ListAlertsRequest(severity="CRITICAL"))
    assert result.success
    print(f"  total : {result.total}")
    for a in result.data:
        print(f"  {a.id}  {a.title}")

    # --- 11. Acknowledge an alert -----------------------------------------
    print("\n[11] Acknowledge Alert")

    ack = acknowledge_alert(ctx, alert_ids[0])
    assert ack.success
    print(f"  acknowledged : {alert_ids[0]}")

    # --- 12. List deliveries (empty — no actual delivery backend) ---------
    print("\n[12] List Alert Deliveries")

    result = list_alert_deliveries(ctx, ListAlertDeliveriesRequest())
    assert result.success
    print(f"  total : {result.total}")
    print(f"  (no deliveries — expected without a notification backend)")

    # --- 13. Delete a channel ---------------------------------------------
    print("\n[13] Delete Channel")

    delete = delete_alert_channel(ctx, channel_ids[2])
    assert delete.success
    print(f"  deleted : {channel_ids[2]}")

    # Verify count decreased
    remaining = list_alert_channels(ctx, ListAlertChannelsRequest())
    print(f"  remaining channels : {remaining.total}")

    # --- 14. Get non-existent channel -------------------------------------
    print("\n[14] Get Non-Existent Channel")

    missing = get_alert_channel(ctx, "ch_doesnotexist")
    assert not missing.success
    print(f"  error.code    : {missing.error.code}")
    print(f"  error.message : {missing.error.message}")

    # --- 15. Dry-run create -----------------------------------------------
    print("\n[15] Dry-Run Create Channel")

    dry_ctx = OperationContext(conn=conn, caller="example", dry_run=True)
    dry = create_alert_channel(
        dry_ctx,
        CreateAlertChannelRequest(name="dry-run-channel", channel_type="pagerduty"),
    )
    assert dry.success
    print(f"  dry_run      : {dry.data.get('dry_run')}")
    print(f"  would_create : {dry.data.get('would_create')}")

    conn.close()
    print("\n✓ Alert management complete.")


if __name__ == "__main__":
    main()
