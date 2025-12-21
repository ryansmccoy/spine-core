#!/usr/bin/env python3
"""Schedule Metadata — Calc dependencies, expected schedules, and data readiness.

WHY SCHEDULE METADATA
─────────────────────
Workflows often depend on upstream data arriving on schedule.
The ops layer tracks which calculations depend on which data sources,
when data is expected, and whether it has arrived — enabling
data-driven scheduling instead of blind cron timers.

ARCHITECTURE
────────────
    Scheduler / Workflow trigger
         │
         ▼
    check_data_readiness("finra.otc.weekly")
         │
         ├─▶ core_calc_dependencies   → what inputs needed
         ├─▶ core_expected_schedules  → when data expected
         └─▶ core_data_readiness      → has it arrived?
         │
    all ready? ──▶ trigger workflow
    not ready?  ──▶ skip / alert

DEPENDENCY GRAPH EXAMPLE
────────────────────────
    finra.otc.weekly_report
       └─ depends_on: finra.otc.ingest (data)
       └─ depends_on: sec.filings.daily (data)
       └─ schedule: every Monday 06:00 UTC

BEST PRACTICES
──────────────
• Register calc dependencies at operation build time.
• Use data_readiness to avoid running workflows on stale data.
• Configure expected_schedules for SLA alerting.
• Combine with 11_scheduling/ for automated triggers.

Run: python examples/10_operations/08_schedule_metadata.py

See Also:
    11_scheduling/ — schedule definitions and execution
    09_locks_dlq_quality — lock management for scheduled runs
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env

from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.schedules import (
    list_schedules,
    get_schedule,
    create_schedule,
    update_schedule,
    delete_schedule,
    list_calc_dependencies,
    list_expected_schedules,
    check_data_readiness,
)
from spine.ops.requests import (
    CreateScheduleRequest,
    GetScheduleRequest,
    UpdateScheduleRequest,
    DeleteScheduleRequest,
    ListCalcDependenciesRequest,
    ListExpectedSchedulesRequest,
    CheckDataReadinessRequest,
)


def _seed_calc_dependencies(conn) -> None:
    """Insert sample calculation dependency records."""
    now = datetime.now(timezone.utc).isoformat()
    deps = [
        ("equity", "eod.calc", None, "market", "price.ingest", "REQUIRED", "equity eod depends on market prices"),
        ("equity", "eod.calc", None, "equity", "corporate_actions", "REQUIRED", "equity eod depends on corp actions"),
        ("otc", "otc.valuation", None, "otc", "otc.ingest", "REQUIRED", "otc valuation depends on otc ingest"),
        ("otc", "otc.valuation", None, "market", "rate.ingest", "OPTIONAL", "otc valuation depends on rates"),
        ("options", "greeks.calc", None, "equity", "eod.calc", "REQUIRED", "options greeks depend on equity eod"),
    ]
    for calc_domain, calc_operation, calc_table, dep_domain, dep_table, dep_type, desc in deps:
        conn.execute(
            "INSERT INTO core_calc_dependencies "
            "(calc_domain, calc_operation, calc_table, depends_on_domain, depends_on_table, "
            "dependency_type, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (calc_domain, calc_operation, calc_table, dep_domain, dep_table, dep_type, desc, now),
        )
    conn.commit()


def _seed_expected_schedules(conn) -> None:
    """Insert sample expected schedule records."""
    now = datetime.now(timezone.utc).isoformat()
    schedules = [
        ("otc", "finra.otc.ingest", "daily", "0 18 * * 1-5", '{"date": "${DATE}"}', 2, None, "OTC daily ingest"),
        ("equity", "equity.eod.calc", "daily", "0 19 * * 1-5", '{"date": "${DATE}"}', 3, None, "Equity EOD calc"),
        ("equity", "equity.eod.report", "daily", "0 20 * * 1-5", '{"date": "${DATE}"}', 4, None, "Equity EOD report"),
        ("options", "greeks.calc", "daily", "30 19 * * 1-5", '{"date": "${DATE}"}', 3, None, "Options greeks"),
        ("recon", "full.recon", "weekly", "0 6 * * 6", '{"week_ending": "${SATURDAY}"}', 24, 48, "Weekly recon"),
    ]
    for domain, workflow, stype, cron, part_tmpl, delay_h, prelim_h, desc in schedules:
        conn.execute(
            "INSERT INTO core_expected_schedules "
            "(domain, workflow, schedule_type, cron_expression, partition_template, "
            "expected_delay_hours, preliminary_hours, description, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (domain, workflow, stype, cron, part_tmpl, delay_h, prelim_h, desc, now, now),
        )
    conn.commit()


def _seed_data_readiness(conn) -> None:
    """Insert sample data readiness records."""
    now = datetime.now(timezone.utc).isoformat()
    entries = [
        ("otc", "2026-02-15", 1, "trading", 1, 1, 1, 1, None, now),
        ("otc", "2026-02-15", 0, "compliance", 1, 0, 1, 0, '["stage validate incomplete"]', None),
        ("equity", "2026-02-15", 1, "trading", 1, 1, 1, 1, None, now),
        ("equity", "2026-02-15", 0, "research", 1, 1, 0, 0, '["critical anomaly: schema drift"]', None),
        ("market", "2026-02-15", 1, "trading", 1, 1, 1, 1, None, now),
    ]
    for domain, pk, ready, ready_for, parts, stages, no_anom, deps, issues, cert_at in entries:
        conn.execute(
            "INSERT INTO core_data_readiness "
            "(domain, partition_key, is_ready, ready_for, all_partitions_present, "
            "all_stages_complete, no_critical_anomalies, dependencies_current, "
            "blocking_issues, certified_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (domain, pk, ready, ready_for, parts, stages, no_anom, deps, issues, cert_at, now, now),
        )
    conn.commit()


def main():
    print("=" * 60)
    print("Operations Layer — Schedule Metadata")
    print("=" * 60)
    
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection()
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")

    apply_all_schemas(conn)
    ctx = OperationContext(conn=conn, caller="example")

    # === SCHEDULE CRUD ====================================================
    print("\n" + "-" * 40)
    print("SCHEDULE CRUD")
    print("-" * 40)

    # --- 1. Empty schedules -----------------------------------------------
    print("\n[1] List Schedules (empty)")

    result = list_schedules(ctx)
    assert result.success
    print(f"  total : {result.total}")

    # --- 2. Create schedules ----------------------------------------------
    print("\n[2] Create Schedules")

    schedule_data = [
        CreateScheduleRequest(
            name="otc-daily-ingest",
            target_type="operation",
            target_name="finra.otc.ingest",
            cron_expression="0 18 * * 1-5",
            enabled=True,
        ),
        CreateScheduleRequest(
            name="equity-eod-calc",
            target_type="operation",
            target_name="equity.eod.calc",
            cron_expression="0 19 * * 1-5",
            enabled=True,
        ),
        CreateScheduleRequest(
            name="weekly-recon",
            target_type="workflow",
            target_name="full.reconciliation",
            cron_expression="0 6 * * 6",
            enabled=False,
        ),
    ]

    schedule_ids = []
    for req in schedule_data:
        res = create_schedule(ctx, req)
        assert res.success, f"Failed: {res.error}"
        schedule_ids.append(res.data.schedule_id)
        print(f"  + {res.data.schedule_id}  {req.name:22s}  cron={req.cron_expression}  enabled={req.enabled}")

    # --- 3. List all schedules --------------------------------------------
    print("\n[3] List All Schedules")

    result = list_schedules(ctx)
    assert result.success
    print(f"  total : {result.total}")
    for s in result.data:
        print(f"  {s.schedule_id}  {s.name:22s}  target={s.target_name}  enabled={s.enabled}")

    # --- 4. Get schedule detail -------------------------------------------
    print("\n[4] Get Schedule Detail")

    detail = get_schedule(ctx, GetScheduleRequest(schedule_id=schedule_ids[0]))
    assert detail.success
    d = detail.data
    print(f"  id          : {d.schedule_id}")
    print(f"  name        : {d.name}")
    print(f"  target_type : {d.target_type}")
    print(f"  target_name : {d.target_name}")
    print(f"  cron        : {d.cron_expression}")
    print(f"  enabled     : {d.enabled}")

    # --- 5. Update schedule -----------------------------------------------
    print("\n[5] Update Schedule (disable)")

    upd = update_schedule(ctx, UpdateScheduleRequest(
        schedule_id=schedule_ids[0],
        enabled=False,
    ))
    assert upd.success
    print(f"  updated : {upd.data}")

    # --- 6. Delete schedule -----------------------------------------------
    print("\n[6] Delete Schedule")

    delete = delete_schedule(ctx, DeleteScheduleRequest(schedule_id=schedule_ids[2]))
    assert delete.success
    print(f"  deleted : {schedule_ids[2]}")

    remaining = list_schedules(ctx)
    print(f"  remaining : {remaining.total}")

    # === CALC DEPENDENCIES ================================================
    print("\n" + "-" * 40)
    print("CALC DEPENDENCIES")
    print("-" * 40)

    # --- 7. Seed dependencies ---------------------------------------------
    print("\n[7] Seed Calc Dependencies")
    _seed_calc_dependencies(conn)
    print("  + 5 dependency records seeded")

    # --- 8. List all dependencies -----------------------------------------
    print("\n[8] List All Calc Dependencies")

    result = list_calc_dependencies(ctx, ListCalcDependenciesRequest())
    assert result.success
    print(f"  total : {result.total}")
    for d in result.data:
        print(f"  {d.calc_domain}.{d.calc_operation} → {d.depends_on_domain}.{d.depends_on_table}  (type={d.dependency_type})")

    # --- 9. Filter by calc domain -----------------------------------------
    print("\n[9] Filter Dependencies for Domain = 'equity'")

    result = list_calc_dependencies(ctx, ListCalcDependenciesRequest(calc_domain="equity"))
    assert result.success
    print(f"  total : {result.total}")
    for d in result.data:
        print(f"  depends on: {d.depends_on_domain}.{d.depends_on_table}")

    # === EXPECTED SCHEDULES ===============================================
    print("\n" + "-" * 40)
    print("EXPECTED SCHEDULES")
    print("-" * 40)

    # --- 10. Seed expected schedules --------------------------------------
    print("\n[10] Seed Expected Schedules")
    _seed_expected_schedules(conn)
    print("  + 5 expected schedule records seeded")

    # --- 11. List all expected schedules ----------------------------------
    print("\n[11] List All Expected Schedules")

    result = list_expected_schedules(ctx, ListExpectedSchedulesRequest())
    assert result.success
    print(f"  total : {result.total}")
    for s in result.data:
        print(f"  {s.domain:10s}  {s.workflow:25s}  {s.schedule_type:8s}  cron={s.cron_expression}  delay_h={s.expected_delay_hours}")

    # --- 12. Filter by schedule type --------------------------------------
    print("\n[12] Filter Expected Schedules by Type = 'weekly'")

    result = list_expected_schedules(ctx, ListExpectedSchedulesRequest(schedule_type="weekly"))
    assert result.success
    print(f"  total : {result.total}")
    for s in result.data:
        print(f"  {s.domain}  {s.workflow}  cron={s.cron_expression}")

    # === DATA READINESS ===================================================
    print("\n" + "-" * 40)
    print("DATA READINESS")
    print("-" * 40)

    # --- 13. Seed data readiness ------------------------------------------
    print("\n[13] Seed Data Readiness")
    _seed_data_readiness(conn)
    print("  + 5 readiness records seeded")

    # --- 14. Check readiness for OTC domain --------------------------------
    print("\n[14] Check Data Readiness for Domain = 'otc'")

    result = check_data_readiness(ctx, CheckDataReadinessRequest(domain="otc"))
    assert result.success
    for r in result.data:
        print(f"  {r.domain:10s}  pk={r.partition_key}  ready={r.is_ready}  for={r.ready_for}")

    # --- 15. Check readiness for equity domain ----------------------------
    print("\n[15] Check Data Readiness for Domain = 'equity'")

    result = check_data_readiness(ctx, CheckDataReadinessRequest(domain="equity"))
    assert result.success
    for r in result.data:
        print(f"  {r.domain:10s}  pk={r.partition_key}  ready={r.is_ready}  for={r.ready_for}")

    # --- 16. Check with partition key -------------------------------------
    print("\n[16] Check Readiness for Domain = 'otc', Partition = '2026-02-15'")

    result = check_data_readiness(ctx, CheckDataReadinessRequest(
        domain="otc",
        partition_key="2026-02-15",
    ))
    assert result.success
    for r in result.data:
        print(f"  {r.domain:10s}  ready={r.is_ready}  blocking={r.blocking_issues}")

    conn.close()
    print("\n✓ Schedule metadata complete.")


if __name__ == "__main__":
    main()
