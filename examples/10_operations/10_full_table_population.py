#!/usr/bin/env python3
"""Full Table Population - Populates ALL 27 tables into a persistent SQLite file.

Exercises every ops-layer function and writes data into a real SQLite database
file so you can inspect table contents.  Creates ``full_demo.db`` in the
examples directory.

Run: python examples/10_operations/10_full_table_population.py
Then: sqlite3 examples/full_demo.db ".tables"

Tables populated (27):
  _migrations, core_executions, core_execution_events, core_manifest,
  core_rejects, core_quality, core_anomalies, core_work_items,
  core_dead_letters, core_concurrency_locks, core_calc_dependencies,
  core_expected_schedules, core_data_readiness, core_workflow_runs,
  core_workflow_steps, core_workflow_events, core_schedules,
  core_schedule_runs, core_schedule_locks, core_alert_channels,
  core_alerts, core_alert_deliveries, core_alert_throttle,
  core_sources, core_source_fetches, core_source_cache,
  core_database_connections
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from spine.core.schema import create_core_tables
from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.sqlite_conn import SqliteConnection

# --- Ops imports (all subsystems) ----------------------------------------
from spine.ops.runs import submit_run, list_runs, get_run_events, get_run_steps
from spine.ops.requests import (
    SubmitRunRequest,
    ListRunsRequest,
    GetRunEventsRequest,
    GetRunStepsRequest,
    CreateScheduleRequest,
    CreateAlertChannelRequest,
    CreateAlertRequest,
    CreateSourceRequest,
    CreateDatabaseConnectionRequest,
    ListAlertChannelsRequest,
    ListAlertsRequest,
    ListSourcesRequest,
    ListDatabaseConnectionsRequest,
    ListManifestEntriesRequest,
    ListRejectsRequest,
    ListWorkItemsRequest,
    ListDeadLettersRequest,
    ListAnomaliesRequest,
    ListQualityResultsRequest,
    ListCalcDependenciesRequest,
    ListExpectedSchedulesRequest,
    CheckDataReadinessRequest,
    ListScheduleLocksRequest,
    ListAlertDeliveriesRequest,
    ClaimWorkItemRequest,
)
from spine.ops.alerts import (
    create_alert_channel, create_alert, list_alert_channels, list_alerts,
    list_alert_deliveries, acknowledge_alert,
)
from spine.ops.sources import (
    register_source, list_sources, list_source_fetches, list_source_cache,
    list_database_connections, register_database_connection,
)
from spine.ops.schedules import (
    create_schedule, list_schedules, list_calc_dependencies,
    list_expected_schedules, check_data_readiness,
)
from spine.ops.processing import (
    list_manifest_entries, list_rejects, list_work_items,
    claim_work_item, complete_work_item, fail_work_item,
)
from spine.ops.locks import list_locks, list_schedule_locks
from spine.ops.dlq import list_dead_letters
from spine.ops.anomalies import list_anomalies
from spine.ops.quality import list_quality_results
from spine.ops.database import get_table_counts


DB_PATH = str(Path(__file__).parent / "full_demo.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_raw(conn, table: str, columns: list[str], rows: list[tuple]) -> int:
    """Insert raw rows into a table. Returns count inserted."""
    placeholders = ", ".join("?" * len(columns))
    col_str = ", ".join(columns)
    for row in rows:
        conn.execute(f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})", row)
    conn.commit()
    return len(rows)


def populate_executions(ctx, conn):
    """Populate core_executions + core_execution_events via ops layer."""
    print("\n  [executions]")

    runs = [
        SubmitRunRequest(kind="pipeline", name="finra.otc.ingest"),
        SubmitRunRequest(kind="pipeline", name="equity.price.ingest"),
        SubmitRunRequest(kind="pipeline", name="options.chain.ingest"),
    ]
    for req in runs:
        res = submit_run(ctx, req)
        assert res.success, f"submit_run failed: {res.error}"
        print(f"    + execution {res.data.run_id}  {req.name}")

    result = list_runs(ctx, ListRunsRequest())
    print(f"    total executions: {result.total}")
    print(f"    events per run seeded via submit_run")


def populate_manifest(conn):
    """Populate core_manifest."""
    print("\n  [manifest]")
    now = _now()
    count = _seed_raw(conn, "core_manifest",
        ["domain", "partition_key", "stage", "stage_rank", "row_count", "execution_id", "batch_id", "updated_at"],
        [
            ("otc", "2026-02-15", "ingest", 1, 5000, "exec-001", "batch-a", now),
            ("otc", "2026-02-15", "validate", 2, 4800, "exec-001", "batch-a", now),
            ("otc", "2026-02-15", "transform", 3, 4800, "exec-001", "batch-a", now),
            ("otc", "2026-02-15", "load", 4, 4800, "exec-001", "batch-a", now),
            ("equity", "2026-02-15", "ingest", 1, 12000, "exec-002", "batch-b", now),
            ("equity", "2026-02-15", "validate", 2, 11500, "exec-002", "batch-b", now),
            ("options", "2026-02-15", "ingest", 1, 8000, "exec-003", "batch-c", now),
        ])
    print(f"    + {count} manifest entries")


def populate_rejects(conn):
    """Populate core_rejects."""
    print("\n  [rejects]")
    now = _now()
    count = _seed_raw(conn, "core_rejects",
        ["domain", "partition_key", "stage", "reason_code", "execution_id", "reason_detail", "raw_json", "created_at"],
        [
            ("otc", "2026-02-15", "validate", "MISSING_FIELD", "exec-001", "CIK is null", '{"row":42}', now),
            ("otc", "2026-02-15", "validate", "INVALID_FORMAT", "exec-001", "Bad date", '{"row":87}', now),
            ("otc", "2026-02-15", "validate", "MISSING_FIELD", "exec-001", "Empty symbol", '{"row":153}', now),
            ("equity", "2026-02-15", "validate", "OUT_OF_RANGE", "exec-002", "Negative price", '{"row":7}', now),
            ("equity", "2026-02-15", "validate", "DUPLICATE", "exec-002", "Dup ticker", '{"row":201}', now),
            ("options", "2026-02-15", "validate", "SCHEMA_MISMATCH", "exec-003", "Extra column", '{"col":"greek_v2"}', now),
        ])
    print(f"    + {count} reject records")


def populate_quality(conn):
    """Populate core_quality."""
    print("\n  [quality]")
    now = _now()
    count = _seed_raw(conn, "core_quality",
        ["domain", "partition_key", "check_name", "category", "status", "message",
         "actual_value", "expected_value", "details_json", "execution_id", "created_at"],
        [
            ("otc", "2026-02-15", "completeness", "COMPLETENESS", "PASS", "98% complete", "0.98", "0.95", '{}', "exec-001", now),
            ("otc", "2026-02-15", "freshness", "COMPLETENESS", "PASS", "Within SLA", "1.0", "0.99", '{}', "exec-001", now),
            ("otc", "2026-02-15", "uniqueness", "INTEGRITY", "FAIL", "400 dups", "0.92", "0.95", '{"dups":400}', "exec-001", now),
            ("equity", "2026-02-15", "completeness", "COMPLETENESS", "PASS", "All present", "1.0", "0.95", '{}', "exec-002", now),
            ("equity", "2026-02-15", "validity", "BUSINESS_RULE", "WARN", "480 invalid", "0.96", "0.98", '{"invalid":480}', "exec-002", now),
            ("options", "2026-02-15", "completeness", "COMPLETENESS", "PASS", "99% complete", "0.99", "0.95", '{}', "exec-003", now),
        ])
    print(f"    + {count} quality checks")


def populate_anomalies(conn):
    """Populate core_anomalies."""
    print("\n  [anomalies]")
    now = _now()
    count = _seed_raw(conn, "core_anomalies",
        ["domain", "workflow", "partition_key", "stage", "severity", "category",
         "message", "details_json", "affected_records", "detected_at", "created_at"],
        [
            ("otc", "finra.otc.ingest", None, "validate", "WARNING", "ROW_COUNT_DROP",
             "Row count drop 36%", None, 1800, now, now),
            ("equity", "equity.price.ingest", None, "ingest", "ERROR", "SCHEMA_DRIFT",
             "Schema drift: extra col", None, None, now, now),
            ("otc", "finra.otc.ingest", None, "transform", "INFO", "NEW_SYMBOL",
             "New symbol ACME", None, 1, now, now),
            ("options", "options.chain.ingest", None, "validate", "WARNING", "STALE_DATA",
             "Stale greeks", None, None, now, now),
        ])
    print(f"    + {count} anomalies")


def populate_work_items(ctx, conn):
    """Populate core_work_items and exercise lifecycle."""
    print("\n  [work_items]")
    now = _now()
    count = _seed_raw(conn, "core_work_items",
        ["id", "domain", "pipeline", "partition_key", "desired_at", "state",
         "locked_by", "created_at", "updated_at"],
        [
            (1, "otc", "finra.otc.ingest", '{"date":"2026-02-15"}', now, "PENDING", None, now, now),
            (2, "otc", "finra.otc.validate", '{"date":"2026-02-15"}', now, "PENDING", None, now, now),
            (3, "equity", "equity.market.calc", '{"date":"2026-02-15"}', now, "PENDING", None, now, now),
            (4, "options", "options.chain.ingest", '{"date":"2026-02-15"}', now, "PENDING", None, now, now),
            (5, "equity", "equity.eod.report", '{"date":"2026-02-14"}', now, "PENDING", None, now, now),
        ])
    print(f"    + {count} work items")

    # Exercise lifecycle: claim → complete / fail
    claim_work_item(ctx, ClaimWorkItemRequest(item_id=1, worker_id="worker-alpha"))
    complete_work_item(ctx, item_id=1)
    claim_work_item(ctx, ClaimWorkItemRequest(item_id=2, worker_id="worker-beta"))
    fail_work_item(ctx, item_id=2, error="Timeout")
    print("    lifecycle: #1 completed, #2 failed, #3-5 pending")


def populate_dead_letters(conn):
    """Populate core_dead_letters."""
    print("\n  [dead_letters]")
    now = _now()
    count = _seed_raw(conn, "core_dead_letters",
        ["id", "execution_id", "workflow", "params", "error",
         "retry_count", "max_retries", "created_at"],
        [
            ("dl-001", "exec-f1", "finra.otc.ingest", '{}', "ConnectionError", 3, 3, now),
            ("dl-002", "exec-f2", "equity.calc", '{}', "ValueError: negative", 1, 3, now),
        ])
    print(f"    + {count} dead letters")


def populate_locks(conn):
    """Populate core_concurrency_locks."""
    print("\n  [concurrency_locks]")
    now = datetime.now(timezone.utc)
    count = _seed_raw(conn, "core_concurrency_locks",
        ["lock_key", "execution_id", "acquired_at", "expires_at"],
        [
            ("pipeline:otc.ingest", "exec-001", now.isoformat(), (now + timedelta(minutes=30)).isoformat()),
            ("pipeline:equity.eod", "exec-002", now.isoformat(), (now + timedelta(minutes=20)).isoformat()),
        ])
    print(f"    + {count} concurrency locks")


def populate_schedule_locks(conn):
    """Populate core_schedule_locks."""
    print("\n  [schedule_locks]")
    now = datetime.now(timezone.utc)
    count = _seed_raw(conn, "core_schedule_locks",
        ["schedule_id", "locked_by", "locked_at", "expires_at"],
        [
            ("sched:otc-daily", "scheduler-01", now.isoformat(), (now + timedelta(minutes=5)).isoformat()),
            ("sched:equity-eod", "scheduler-01", now.isoformat(), (now + timedelta(minutes=5)).isoformat()),
        ])
    print(f"    + {count} schedule locks")


def populate_schedules(ctx):
    """Populate core_schedules via ops layer."""
    print("\n  [schedules]")
    scheds = [
        CreateScheduleRequest(name="otc-daily-ingest", target_type="pipeline",
                             target_name="finra.otc.ingest", cron_expression="0 18 * * 1-5"),
        CreateScheduleRequest(name="equity-eod-calc", target_type="pipeline",
                             target_name="equity.eod.calc", cron_expression="0 19 * * 1-5"),
        CreateScheduleRequest(name="weekly-recon", target_type="workflow",
                             target_name="full.reconciliation", cron_expression="0 6 * * 6", enabled=False),
    ]
    for req in scheds:
        res = create_schedule(ctx, req)
        assert res.success, f"create_schedule failed: {res.error}"
        print(f"    + schedule {res.data.schedule_id}  {req.name}")


def populate_calc_dependencies(conn):
    """Populate core_calc_dependencies."""
    print("\n  [calc_dependencies]")
    now = _now()
    count = _seed_raw(conn, "core_calc_dependencies",
        ["calc_domain", "calc_pipeline", "calc_table", "depends_on_domain",
         "depends_on_table", "dependency_type", "description", "created_at"],
        [
            ("equity", "eod.calc", None, "market", "price.ingest", "REQUIRED", "EOD depends on prices", now),
            ("equity", "eod.calc", None, "equity", "corporate_actions", "REQUIRED", "EOD depends on corp actions", now),
            ("otc", "otc.valuation", None, "otc", "otc.ingest", "REQUIRED", "Valuation depends on ingest", now),
            ("options", "greeks.calc", None, "equity", "eod.calc", "REQUIRED", "Greeks depend on equity EOD", now),
        ])
    print(f"    + {count} calc dependencies")


def populate_expected_schedules(conn):
    """Populate core_expected_schedules."""
    print("\n  [expected_schedules]")
    now = _now()
    count = _seed_raw(conn, "core_expected_schedules",
        ["domain", "pipeline", "schedule_type", "cron_expression", "partition_template",
         "expected_delay_hours", "preliminary_hours", "description", "is_active", "created_at", "updated_at"],
        [
            ("otc", "finra.otc.ingest", "daily", "0 18 * * 1-5", '{"date":"${DATE}"}', 2, None, "OTC daily ingest", 1, now, now),
            ("equity", "equity.eod.calc", "daily", "0 19 * * 1-5", '{"date":"${DATE}"}', 3, None, "Equity EOD calc", 1, now, now),
            ("equity", "equity.eod.report", "daily", "0 20 * * 1-5", '{"date":"${DATE}"}', 4, None, "Equity EOD report", 1, now, now),
            ("options", "greeks.calc", "daily", "30 19 * * 1-5", '{"date":"${DATE}"}', 3, None, "Options greeks", 1, now, now),
            ("recon", "full.recon", "weekly", "0 6 * * 6", '{"week":"${SATURDAY}"}', 24, 48, "Weekly recon", 1, now, now),
        ])
    print(f"    + {count} expected schedules")


def populate_data_readiness(conn):
    """Populate core_data_readiness."""
    print("\n  [data_readiness]")
    now = _now()
    count = _seed_raw(conn, "core_data_readiness",
        ["domain", "partition_key", "is_ready", "ready_for",
         "all_partitions_present", "all_stages_complete",
         "no_critical_anomalies", "dependencies_current",
         "blocking_issues", "certified_at", "created_at", "updated_at"],
        [
            ("otc", "2026-02-15", 1, "trading", 1, 1, 1, 1, None, now, now, now),
            ("otc", "2026-02-15", 0, "compliance", 1, 0, 1, 0, '["validate incomplete"]', None, now, now),
            ("equity", "2026-02-15", 1, "trading", 1, 1, 1, 1, None, now, now, now),
            ("equity", "2026-02-15", 0, "research", 1, 1, 0, 0, '["schema drift"]', None, now, now),
            ("market", "2026-02-15", 1, "trading", 1, 1, 1, 1, None, now, now, now),
        ])
    print(f"    + {count} data readiness records")


def populate_alerts(ctx):
    """Populate core_alert_channels + core_alerts + core_alert_deliveries."""
    print("\n  [alert_channels]")
    channels = [
        CreateAlertChannelRequest(name="slack-critical", channel_type="slack",
            config={"webhook": "https://hooks.slack.com"}, min_severity="CRITICAL",
            domains=["equity", "otc"], throttle_minutes=1),
        CreateAlertChannelRequest(name="email-ops", channel_type="email",
            config={"to": "ops@example.com"}, min_severity="ERROR"),
    ]
    ch_ids = []
    for req in channels:
        res = create_alert_channel(ctx, req)
        assert res.success
        ch_ids.append(res.data["id"])
        print(f"    + channel {res.data['id']}  {req.name}")

    print("\n  [alerts]")
    alerts = [
        CreateAlertRequest(severity="CRITICAL", title="Price feed stale",
            message="No updates in 30 min", source="equity.monitor", domain="equity"),
        CreateAlertRequest(severity="ERROR", title="Validation threshold exceeded",
            message="17% reject rate", source="otc.validator", domain="otc"),
        CreateAlertRequest(severity="WARNING", title="Disk 83% full",
            message="Storage warning", source="infra.monitor"),
    ]
    for req in alerts:
        res = create_alert(ctx, req)
        assert res.success
        print(f"    + alert {res.data['id']}  [{req.severity}] {req.title}")

    # Seed some delivery records manually (since no real notification backend)
    print("\n  [alert_deliveries]")
    now = _now()
    conn = ctx.conn
    conn.execute(
        "INSERT INTO core_alert_deliveries "
        "(id, alert_id, channel_id, channel_name, status, delivered_at, response_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"del_{uuid.uuid4().hex[:8]}", res.data["id"], ch_ids[0], "slack-critical",
         "SENT", now, '{"status_code": 200}'))
    conn.commit()
    print("    + 1 delivery record")

    # Seed throttle record
    print("\n  [alert_throttle]")
    conn.execute(
        "INSERT INTO core_alert_throttle "
        "(dedup_key, last_sent_at, send_count, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (f"{ch_ids[0]}:equity.monitor:CRITICAL", now,
         1, datetime.now(timezone.utc).__add__(timedelta(minutes=5)).isoformat()))
    conn.commit()
    print("    + 1 throttle record")


def populate_sources(ctx, conn):
    """Populate core_sources + core_source_fetches + core_source_cache + core_database_connections."""
    print("\n  [sources]")
    sources = [
        CreateSourceRequest(name="sec-edgar-rss", source_type="http",
            config={"url": "https://sec.gov/cgi-bin/browse-edgar"}, domain="sec"),
        CreateSourceRequest(name="finra-otc-file", source_type="file",
            config={"path": "/data/finra/otc"}, domain="otc"),
        CreateSourceRequest(name="equity-s3", source_type="s3",
            config={"bucket": "market-data"}, domain="equity"),
    ]
    src_ids = []
    for req in sources:
        res = register_source(ctx, req)
        assert res.success
        src_ids.append(res.data["id"])
        print(f"    + source {res.data['id']}  {req.name}")

    # Seed fetch history
    print("\n  [source_fetches]")
    now = _now()
    count = _seed_raw(conn, "core_source_fetches",
        ["id", "source_id", "source_name", "source_type", "source_locator",
         "status", "record_count", "byte_count", "started_at", "completed_at", "error", "created_at"],
        [
            (f"fetch_{uuid.uuid4().hex[:8]}", src_ids[0], "sec-edgar-rss", "http",
             "https://sec.gov/cgi-bin/browse-edgar", "SUCCESS", 150, 45000, now, now, None, now),
            (f"fetch_{uuid.uuid4().hex[:8]}", src_ids[0], "sec-edgar-rss", "http",
             "https://sec.gov/cgi-bin/browse-edgar", "SUCCESS", 142, 42000, now, now, None, now),
            (f"fetch_{uuid.uuid4().hex[:8]}", src_ids[1], "finra-otc-file", "file",
             "/data/finra/otc/latest.csv", "FAILED", 0, 0, now, now, "File not found", now),
        ])
    print(f"    + {count} fetch records")

    # Seed cache
    print("\n  [source_cache]")
    count = _seed_raw(conn, "core_source_cache",
        ["cache_key", "source_id", "source_type", "source_locator",
         "content_hash", "content_size", "fetched_at", "expires_at", "created_at"],
        [
            ("edgar/2026-02-15", src_ids[0], "http", "https://sec.gov/cgi-bin/browse-edgar",
             "sha256:abc123", 45000, now, now, now),
            ("equity/daily/2026-02-15", src_ids[2], "s3", "s3://market-data/equity/daily/",
             "sha256:def456", 120000, now, now, now),
        ])
    print(f"    + {count} cache entries")

    # Seed database connections
    print("\n  [database_connections]")
    db_conns = [
        CreateDatabaseConnectionRequest(name="prod-postgres", dialect="postgresql",
            host="db.example.com", port=5432, database="spine_prod",
            username="spine_app", password_ref="vault:secrets/db"),
        CreateDatabaseConnectionRequest(name="local-sqlite", dialect="sqlite",
            database="/data/local.db"),
    ]
    for req in db_conns:
        res = register_database_connection(ctx, req)
        assert res.success
        print(f"    + db_conn {res.data['id']}  {req.name}  ({req.dialect})")


def populate_workflows(conn):
    """Populate core_workflow_runs + core_workflow_steps + core_workflow_events."""
    print("\n  [workflow_runs + steps + events]")
    now = _now()
    run_id = f"wfr_{uuid.uuid4().hex[:8]}"

    _seed_raw(conn, "core_workflow_runs",
        ["run_id", "workflow_name", "workflow_version", "status", "started_at", "completed_at",
         "triggered_by", "created_at"],
        [(run_id, "wf-daily-pipeline", 1, "COMPLETED", now, now, "manual", now)])

    steps = [
        (f"step_{uuid.uuid4().hex[:8]}", run_id, "ingest", "pipeline", 1, "COMPLETED", now, now, None),
        (f"step_{uuid.uuid4().hex[:8]}", run_id, "validate", "pipeline", 2, "COMPLETED", now, now, None),
        (f"step_{uuid.uuid4().hex[:8]}", run_id, "transform", "pipeline", 3, "COMPLETED", now, now, None),
    ]
    _seed_raw(conn, "core_workflow_steps",
        ["step_id", "run_id", "step_name", "step_type", "step_order", "status",
         "started_at", "completed_at", "error"],
        steps)

    _seed_raw(conn, "core_workflow_events",
        ["run_id", "step_id", "event_type", "timestamp", "payload"],
        [
            (run_id, steps[0][0], "step_started", now, '{}'),
            (run_id, steps[0][0], "step_completed", now, '{}'),
            (run_id, steps[1][0], "step_started", now, '{}'),
            (run_id, steps[1][0], "step_completed", now, '{}'),
        ])

    print(f"    + 1 workflow run, {len(steps)} steps, 4 events")


def populate_schedule_runs(conn):
    """Populate core_schedule_runs."""
    print("\n  [schedule_runs]")
    now = _now()
    count = _seed_raw(conn, "core_schedule_runs",
        ["id", "schedule_id", "schedule_name", "scheduled_at", "started_at",
         "completed_at", "status", "created_at"],
        [
            (f"sr_{uuid.uuid4().hex[:8]}", "sched-placeholder", "otc-daily", now, now, now, "COMPLETED", now),
            (f"sr_{uuid.uuid4().hex[:8]}", "sched-placeholder", "otc-daily", now, now, now, "FAILED", now),
        ])
    print(f"    + {count} schedule runs")


def verify_all_tables(ctx, conn):
    """Query every table through the ops layer and report counts."""
    print("\n" + "=" * 60)
    print("TABLE VERIFICATION")
    print("=" * 60)

    # Use get_table_counts from database ops
    tc_result = get_table_counts(ctx)
    if tc_result.success:
        print(f"\n  {'Table':<35s}  {'Rows':>5s}")
        print(f"  {'─' * 35}  {'─' * 5}")
        total_rows = 0
        populated = 0
        for tc in tc_result.data:
            name = tc.table
            count = tc.count
            marker = "✓" if count > 0 else "✗"
            print(f"  {marker} {name:<33s}  {count:>5d}")
            total_rows += count
            if count > 0:
                populated += 1
        print(f"\n  Core tables: {populated} populated, {total_rows} rows")

    # Full verification via direct SQL (covers ALL tables including migration-only ones)
    conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row["name"] for row in conn.fetchall()]
    print(f"\n  {'Table':<35s}  {'Rows':>5s}")
    print(f"  {'─' * 35}  {'─' * 5}")
    total_rows = 0
    populated = 0
    for t in tables:
        conn.execute(f"SELECT COUNT(*) as cnt FROM [{t}]")
        count = conn.fetchone()["cnt"]
        marker = "✓" if count > 0 else "✗"
        print(f"  {marker} {t:<33s}  {count:>5d}")
        total_rows += count
        if count > 0:
            populated += 1
    print(f"\n  Total: {populated}/{len(tables)} tables populated, {total_rows} total rows")


def main():
    # Remove old DB if present
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print("=" * 60)
    print("Full Table Population → full_demo.db")
    print("=" * 60)
    print(f"  DB: {DB_PATH}")

    conn = SqliteConnection(DB_PATH)
    create_core_tables(conn)
    apply_all_schemas(conn)
    ctx = OperationContext(conn=conn, caller="example")

    print("\nPopulating all 27 tables...")

    # --- Phase 1: Core tables (via ops + raw seeding) ---------------------
    populate_executions(ctx, conn)
    populate_manifest(conn)
    populate_rejects(conn)
    populate_quality(conn)
    populate_anomalies(conn)
    populate_work_items(ctx, conn)
    populate_dead_letters(conn)
    populate_locks(conn)

    # --- Phase 2: Scheduling tables ---------------------------------------
    populate_schedules(ctx)
    populate_schedule_locks(conn)
    populate_schedule_runs(conn)
    populate_calc_dependencies(conn)
    populate_expected_schedules(conn)
    populate_data_readiness(conn)

    # --- Phase 3: Workflow history ----------------------------------------
    populate_workflows(conn)

    # --- Phase 4: Alerting ------------------------------------------------
    populate_alerts(ctx)

    # --- Phase 5: Sources -------------------------------------------------
    populate_sources(ctx, conn)

    # --- Phase 6: Migrations marker ---------------------------------------
    print("\n  [_migrations]")
    conn.execute(
        "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
        ("00_core.sql", _now()))
    conn.execute(
        "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
        ("02_workflow_history.sql", _now()))
    conn.execute(
        "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
        ("03_scheduler.sql", _now()))
    conn.execute(
        "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
        ("04_alerting.sql", _now()))
    conn.execute(
        "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
        ("05_sources.sql", _now()))
    conn.commit()
    print("    + 5 migration records")

    # --- Verify all tables -----------------------------------------------
    verify_all_tables(ctx, conn)

    conn.close()

    print(f"\n✓ All 27 tables populated in {DB_PATH}")
    print(f"  Inspect with: sqlite3 {DB_PATH} \".tables\"")
    print(f"  Or: sqlite3 {DB_PATH} \"SELECT name, (SELECT COUNT(*) FROM [\" || name || \"]) as cnt FROM sqlite_master WHERE type='table' ORDER BY name;\"")


if __name__ == "__main__":
    main()
