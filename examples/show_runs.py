#!/usr/bin/env python3
"""Display all example execution runs from the local SQLite database.

Shows:
- Grouped runs by category
- Rich execution details
- Table population status
- Data quality checks

Usage::
    python examples/show_runs.py
    python examples/show_runs.py --category 01_core
    python examples/show_runs.py --check-tables
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Database paths
RESULTS_DIR = Path(__file__).resolve().parent / "results"
DIALECT_DB = RESULTS_DIR / "dialect_examples.db"
ORM_DB = RESULTS_DIR / "orm_examples.db"


def get_connection(db_path: Path) -> sqlite3.Connection | None:
    """Get a connection to the database if it exists."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 0.001:
        return "<1ms"
    elif seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"


def format_timestamp(ts: str | None) -> str:
    """Format ISO timestamp to readable form."""
    if not ts:
        return "-"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts[:19] if len(ts) >= 19 else ts


def print_header(text: str, char: str = "=", width: int = 80) -> None:
    """Print a formatted header."""
    print()
    print(char * width)
    print(f" {text}")
    print(char * width)


def print_subheader(text: str, char: str = "-", width: int = 70) -> None:
    """Print a formatted subheader."""
    print()
    print(f"  {char * 3} {text} {char * (width - len(text) - 6)}")


def get_table_stats(conn: sqlite3.Connection) -> dict[str, dict]:
    """Get statistics for all tables."""
    stats = {}
    
    # Get all tables
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'core_%' ORDER BY name"
    ).fetchall()
    
    for row in tables:
        table = row["name"]
        
        # Row count
        count = conn.execute(f"SELECT COUNT(1) FROM [{table}]").fetchone()[0]
        
        # Column info
        columns = []
        for col in conn.execute(f"PRAGMA table_info([{table}])"):
            columns.append({
                "name": col["name"],
                "type": col["type"],
                "nullable": not col["notnull"],
                "default": col["dflt_value"],
            })
        
        # Sample null percentages for populated tables
        null_stats = {}
        if count > 0:
            for col_info in columns:
                col = col_info["name"]
                try:
                    null_count = conn.execute(
                        f"SELECT COUNT(1) FROM [{table}] WHERE [{col}] IS NULL"
                    ).fetchone()[0]
                    null_stats[col] = round(null_count / count * 100, 1)
                except Exception:
                    null_stats[col] = -1
        
        stats[table] = {
            "count": count,
            "columns": columns,
            "null_stats": null_stats,
        }
    
    return stats


def show_executions(conn: sqlite3.Connection, category_filter: str | None = None) -> None:
    """Display all executions grouped by category."""
    
    # Fetch all executions
    query = """
        SELECT 
            id, workflow, params, status, lane, trigger_source,
            created_at, started_at, completed_at, result, error
        FROM core_executions
        ORDER BY workflow, created_at DESC
    """
    executions = conn.execute(query).fetchall()
    
    if not executions:
        print("\n  No executions found in database.")
        return
    
    # Group by category
    by_category: dict[str, list] = defaultdict(list)
    for ex in executions:
        workflow = ex["workflow"] or "unknown"
        # Parse: example.01_core.01_result_pattern
        parts = workflow.split(".")
        if len(parts) >= 2 and parts[0] == "example":
            cat = parts[1]
        else:
            cat = "other"
        
        if category_filter and cat != category_filter:
            continue
            
        by_category[cat].append(ex)
    
    # Summary
    total = sum(len(exs) for exs in by_category.values())
    passed = sum(1 for exs in by_category.values() for ex in exs if ex["status"] == "completed")
    failed = total - passed
    
    print_header(f"EXECUTION RUNS  ({total} total, {passed} passed, {failed} failed)")
    
    # Show each category
    for cat in sorted(by_category.keys()):
        exs = by_category[cat]
        cat_passed = sum(1 for ex in exs if ex["status"] == "completed")
        cat_failed = len(exs) - cat_passed
        
        status_icon = "✓" if cat_failed == 0 else "✗"
        print_subheader(f"{cat}  [{status_icon} {cat_passed}/{len(exs)}]")
        
        for ex in exs:
            workflow = ex["workflow"] or "?"
            status = ex["status"]
            
            # Parse example name from workflow
            parts = workflow.split(".")
            if len(parts) >= 3:
                name = parts[2]
            else:
                name = workflow
            
            # Parse result for duration
            duration = "?"
            try:
                result = json.loads(ex["result"]) if ex["result"] else {}
                duration = format_duration(result.get("duration_seconds", 0))
            except Exception:
                pass
            
            # Parse params for title
            title = ""
            try:
                params = json.loads(ex["params"]) if ex["params"] else {}
                title = params.get("example_title", "")[:45]
            except Exception:
                pass
            
            # Status icon
            if status == "completed":
                status_str = "✓ PASS"
            elif status == "failed":
                status_str = "✗ FAIL"
            else:
                status_str = f"? {status}"
            
            # Format line
            timestamp = format_timestamp(ex["created_at"])
            print(f"    {name:35} {status_str:8} {duration:>8}  {timestamp}")
            if title:
                print(f"      └─ {title}")
            
            # Show error for failures
            if status == "failed" and ex["error"]:
                error_preview = ex["error"][:80].replace("\n", " ")
                print(f"      └─ ERROR: {error_preview}...")


def show_events(conn: sqlite3.Connection, limit: int = 20) -> None:
    """Show recent execution events."""
    
    events = conn.execute("""
        SELECT 
            e.id, e.execution_id, e.event_type, e.timestamp, e.data,
            x.workflow
        FROM core_execution_events e
        LEFT JOIN core_executions x ON e.execution_id = x.id
        ORDER BY e.timestamp DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    if not events:
        print("\n  No events found.")
        return
    
    total = conn.execute("SELECT COUNT(1) FROM core_execution_events").fetchone()[0]
    print_header(f"EXECUTION EVENTS  (showing {len(events)} of {total})")
    
    print(f"\n  {'Event Type':<15} {'Workflow':<40} {'Timestamp':<20}")
    print(f"  {'-'*15} {'-'*40} {'-'*20}")
    
    for ev in events:
        event_type = ev["event_type"] or "?"
        workflow = (ev["workflow"] or "?")[:40]
        timestamp = format_timestamp(ev["timestamp"])
        print(f"  {event_type:<15} {workflow:<40} {timestamp}")


def show_table_status(conn: sqlite3.Connection, detail: bool = False) -> None:
    """Show population status of all core tables."""
    
    stats = get_table_stats(conn)
    
    populated = sum(1 for s in stats.values() if s["count"] > 0)
    empty = len(stats) - populated
    
    print_header(f"TABLE POPULATION STATUS  ({populated} populated, {empty} empty)")
    
    # Group tables
    populated_tables = {k: v for k, v in stats.items() if v["count"] > 0}
    empty_tables = {k: v for k, v in stats.items() if v["count"] == 0}
    
    # Show populated tables
    if populated_tables:
        print_subheader("Populated Tables")
        print(f"\n  {'Table':<40} {'Rows':>10} {'Columns':>10}")
        print(f"  {'-'*40} {'-'*10} {'-'*10}")
        
        for table, info in sorted(populated_tables.items()):
            print(f"  {table:<40} {info['count']:>10,} {len(info['columns']):>10}")
            
            # Show null statistics for key columns
            if detail and info["null_stats"]:
                high_null_cols = [
                    (col, pct) for col, pct in info["null_stats"].items()
                    if pct > 50 and pct >= 0
                ]
                if high_null_cols:
                    print(f"    └─ High null%: ", end="")
                    print(", ".join(f"{col}={pct:.0f}%" for col, pct in high_null_cols[:5]))
    
    # Show empty tables
    if empty_tables:
        print_subheader("Empty Tables (not populated by examples)")
        
        # Group by expected source
        execution_related = ["core_executions", "core_execution_events", "core_workflow_runs", 
                            "core_workflow_steps", "core_workflow_events"]
        schedule_related = ["core_schedules", "core_schedule_runs", "core_schedule_locks",
                           "core_expected_schedules"]
        alert_related = ["core_alerts", "core_alert_channels", "core_alert_deliveries",
                        "core_alert_throttle", "core_anomalies"]
        data_related = ["core_sources", "core_source_cache", "core_source_fetches",
                       "core_watermarks", "core_quality", "core_rejects", "core_dead_letters",
                       "core_manifest", "core_bitemporal_facts"]
        other = ["core_concurrency_locks", "core_backfill_plans", "core_calc_dependencies",
                "core_data_readiness", "core_database_connections", "core_work_items"]
        
        groups = [
            ("Scheduling", schedule_related),
            ("Alerts & Anomalies", alert_related),
            ("Data Operation", data_related),
            ("Other", other),
        ]
        
        for group_name, expected in groups:
            empty_in_group = [t for t in expected if t in empty_tables]
            if empty_in_group:
                print(f"\n    {group_name}:")
                for t in empty_in_group:
                    print(f"      - {t}")


def check_data_quality(conn: sqlite3.Connection) -> None:
    """Run data quality checks on populated tables."""
    
    print_header("DATA QUALITY CHECKS")
    
    issues = []
    
    # Check core_executions
    print_subheader("core_executions")
    
    # Check for missing workflow names
    missing_workflow = conn.execute(
        "SELECT COUNT(1) FROM core_executions WHERE workflow IS NULL OR workflow = ''"
    ).fetchone()[0]
    if missing_workflow:
        issues.append(f"core_executions: {missing_workflow} rows with missing workflow")
        print(f"    ✗ {missing_workflow} executions missing workflow name")
    else:
        print(f"    ✓ All executions have workflow names")
    
    # Check status distribution
    statuses = conn.execute(
        "SELECT status, COUNT(1) FROM core_executions GROUP BY status"
    ).fetchall()
    print(f"    ✓ Status distribution: ", end="")
    print(", ".join(f"{s['status']}={s[1]}" for s in statuses))
    
    # Check for executions without events
    orphan_execs = conn.execute("""
        SELECT COUNT(1) FROM core_executions e
        WHERE NOT EXISTS (
            SELECT 1 FROM core_execution_events ev WHERE ev.execution_id = e.id
        )
    """).fetchone()[0]
    if orphan_execs:
        issues.append(f"core_executions: {orphan_execs} executions without events")
        print(f"    ✗ {orphan_execs} executions have no associated events")
    else:
        print(f"    ✓ All executions have associated events")
    
    # Check timestamps
    missing_created = conn.execute(
        "SELECT COUNT(1) FROM core_executions WHERE created_at IS NULL"
    ).fetchone()[0]
    if missing_created:
        issues.append(f"core_executions: {missing_created} rows missing created_at")
        print(f"    ✗ {missing_created} executions missing created_at")
    else:
        print(f"    ✓ All executions have created_at timestamps")
    
    # Check core_execution_events
    print_subheader("core_execution_events")
    
    # Orphan events
    orphan_events = conn.execute("""
        SELECT COUNT(1) FROM core_execution_events ev
        WHERE NOT EXISTS (
            SELECT 1 FROM core_executions e WHERE e.id = ev.execution_id
        )
    """).fetchone()[0]
    if orphan_events:
        issues.append(f"core_execution_events: {orphan_events} orphan events")
        print(f"    ✗ {orphan_events} events reference non-existent executions")
    else:
        print(f"    ✓ All events reference valid executions")
    
    # Event type distribution
    event_types = conn.execute(
        "SELECT event_type, COUNT(1) FROM core_execution_events GROUP BY event_type ORDER BY COUNT(1) DESC"
    ).fetchall()
    print(f"    ✓ Event types: ", end="")
    print(", ".join(f"{e['event_type']}={e[1]}" for e in event_types[:5]))
    
    # Summary
    print_subheader("Summary")
    if issues:
        print(f"\n    Found {len(issues)} data quality issue(s):")
        for issue in issues:
            print(f"      ✗ {issue}")
    else:
        print(f"\n    ✓ No data quality issues found!")


def explain_empty_tables() -> None:
    """Explain why certain tables are empty."""
    
    print_header("WHY TABLES ARE EMPTY")
    
    explanation = """
    The examples runner stores METADATA about example runs, not the actual
    data created by each example. Here's why:

    POPULATED TABLES:
      • core_executions      - One row per example run (pass/fail, duration)
      • core_execution_events - Lifecycle events + stdout capture per run

    EMPTY TABLES (by design):
      Each example runs in ISOLATION with its own temporary database.
      This prevents examples from interfering with each other.

      • Scheduling tables    - Examples don't create real schedules
      • Alert tables         - Alerts are created in example's temp DB
      • Data operation tables - Sources/quality checked in isolation
      • Lock tables          - Concurrency locks are per-process

    TO POPULATE ALL TABLES:
      Individual examples DO write to their own temp databases.
      To see that data, run an example directly:

        python examples/07_alerts/01_alert_repository.py
        python examples/05_infrastructure/01_complete_operation.py

      Or use --detail with run_all.py to see per-example DB stats.
    """
    print(explanation)


def main() -> None:
    parser = argparse.ArgumentParser(description="Display example execution runs")
    parser.add_argument("--category", type=str, help="Filter by category (e.g. 01_core)")
    parser.add_argument("--events", action="store_true", help="Show recent events")
    parser.add_argument("--events-limit", type=int, default=20, help="Number of events to show")
    parser.add_argument("--tables", action="store_true", help="Show table population status")
    parser.add_argument("--check", action="store_true", help="Run data quality checks")
    parser.add_argument("--explain", action="store_true", help="Explain why tables are empty")
    parser.add_argument("--detail", action="store_true", help="Show detailed information")
    parser.add_argument("--all", action="store_true", help="Show everything")
    parser.add_argument("--db", type=str, choices=["dialect", "orm"], default="dialect",
                       help="Which database to query")
    args = parser.parse_args()
    
    # Select database
    db_path = DIALECT_DB if args.db == "dialect" else ORM_DB
    
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " SPINE-CORE EXAMPLE RUNS VIEWER ".center(78) + "║")
    print("╚" + "═" * 78 + "╝")
    
    conn = get_connection(db_path)
    if not conn:
        print(f"\n  ✗ Database not found: {db_path}")
        print(f"    Run 'python examples/run_all.py' first to generate data.")
        return
    
    print(f"\n  Database: {db_path}")
    print(f"  Size: {db_path.stat().st_size / 1024:.1f} KB")
    print(f"  Modified: {datetime.fromtimestamp(db_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Default: show executions
    show_all = args.all or not any([args.events, args.tables, args.check, args.explain])
    
    if show_all or not any([args.events, args.tables, args.check, args.explain]):
        show_executions(conn, args.category)
    
    if args.events or args.all:
        show_events(conn, args.events_limit)
    
    if args.tables or args.all:
        show_table_status(conn, detail=args.detail)
    
    if args.check or args.all:
        check_data_quality(conn)
    
    if args.explain:
        explain_empty_tables()
    
    conn.close()
    print()


if __name__ == "__main__":
    main()
