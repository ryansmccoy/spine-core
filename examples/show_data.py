#!/usr/bin/env python3
"""Display captured data from spine-core examples — Rich terminal visualization.

Shows:
- Database schema diagram (ASCII art)
- Table statistics and row counts
- Sample data from each populated table
- Cross-table relationships
- Data quality summary

Usage::
    python examples/show_data.py                # Overview
    python examples/show_data.py --schema       # Show schema diagram
    python examples/show_data.py --samples      # Show sample data
    python examples/show_data.py --all          # Everything
    python examples/show_data.py --table core_anomalies  # Specific table
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Database paths
RESULTS_DIR = Path(__file__).resolve().parent / "results"
SHARED_DB = RESULTS_DIR / "shared_demo.db"


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA DIAGRAM
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA_DIAGRAM = r"""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                          SPINE-CORE DATABASE SCHEMA                               ║
║                          ═══════════════════════════                               ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║   ┌─────────────────────┐         ┌─────────────────────┐                        ║
║   │   EXECUTION LAYER   │         │   SCHEDULING LAYER  │                        ║
║   ├─────────────────────┤         ├─────────────────────┤                        ║
║   │ core_executions     │────────▶│ core_schedules      │                        ║
║   │ • id (PK)           │         │ • id (PK)           │                        ║
║   │ • workflow          │         │ • name              │                        ║
║   │ • status            │         │ • cron_expr         │                        ║
║   │ • created_at        │         │ • workflow_name     │                        ║
║   └─────────┬───────────┘         └─────────────────────┘                        ║
║             │                                                                     ║
║             ▼                                                                     ║
║   ┌─────────────────────┐         ┌─────────────────────┐                        ║
║   │ core_execution_     │         │ core_schedule_runs  │                        ║
║   │      events         │         ├─────────────────────┤                        ║
║   ├─────────────────────┤         │ • schedule_id       │                        ║
║   │ • execution_id (FK) │         │ • execution_id      │                        ║
║   │ • event_type        │         │ • status            │                        ║
║   │ • message           │         └─────────────────────┘                        ║
║   │ • timestamp         │                                                         ║
║   └─────────────────────┘                                                         ║
║                                                                                   ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║   ┌─────────────────────┐         ┌─────────────────────┐                        ║
║   │    QUALITY LAYER    │         │   RESILIENCE LAYER  │                        ║
║   ├─────────────────────┤         ├─────────────────────┤                        ║
║   │ core_quality        │         │ core_dead_letters   │                        ║
║   │ • check_name        │         │ • id (PK)           │                        ║
║   │ • status            │         │ • queue             │                        ║
║   │ • metrics           │         │ • payload           │                        ║
║   ├─────────────────────┤         │ • error             │                        ║
║   │ core_anomalies      │         │ • retry_count       │                        ║
║   │ • severity          │         └─────────────────────┘                        ║
║   │ • category          │                                                         ║
║   │ • domain            │         ┌─────────────────────┐                        ║
║   │ • message           │         │ core_concurrency_   │                        ║
║   ├─────────────────────┤         │       locks         │                        ║
║   │ core_rejects        │         ├─────────────────────┤                        ║
║   │ • record_hash       │         │ • lock_key (PK)     │                        ║
║   │ • reason            │         │ • execution_id      │                        ║
║   │ • payload           │         │ • acquired_at       │                        ║
║   └─────────────────────┘         │ • expires_at        │                        ║
║                                   └─────────────────────┘                        ║
║                                                                                   ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║   ┌─────────────────────┐         ┌─────────────────────┐                        ║
║   │   PROGRESS LAYER    │         │    SOURCE LAYER     │                        ║
║   ├─────────────────────┤         ├─────────────────────┤                        ║
║   │ core_watermarks     │         │ core_sources        │                        ║
║   │ • domain            │         │ • id (PK)           │                        ║
║   │ • partition_key     │         │ • name              │                        ║
║   │ • watermark         │         │ • source_type       │                        ║
║   ├─────────────────────┤         │ • enabled           │                        ║
║   │ core_manifest       │         ├─────────────────────┤                        ║
║   │ • domain            │         │ core_source_fetches │                        ║
║   │ • partition_key     │         │ • source_id         │                        ║
║   │ • stage             │         │ • fetch_time        │                        ║
║   │ • row_count         │         │ • bytes_fetched     │                        ║
║   ├─────────────────────┤         ├─────────────────────┤                        ║
║   │ core_work_items     │         │ core_source_cache   │                        ║
║   │ • item_key          │         │ • source_id         │                        ║
║   │ • status            │         │ • content_hash      │                        ║
║   │ • claimed_by        │         └─────────────────────┘                        ║
║   └─────────────────────┘                                                         ║
║                                                                                   ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║   ┌─────────────────────┐         ┌─────────────────────┐                        ║
║   │    ALERT LAYER      │         │   WORKFLOW LAYER    │                        ║
║   ├─────────────────────┤         ├─────────────────────┤                        ║
║   │ core_alerts         │         │ core_workflow_runs  │                        ║
║   │ • id (PK)           │         │ • id (PK)           │                        ║
║   │ • severity          │         │ • workflow_name     │                        ║
║   │ • message           │         │ • status            │                        ║
║   │ • acknowledged      │         ├─────────────────────┤                        ║
║   ├─────────────────────┤         │ core_workflow_steps │                        ║
║   │ core_alert_channels │         │ • workflow_run_id   │                        ║
║   │ • name              │         │ • step_name         │                        ║
║   │ • channel_type      │         │ • status            │                        ║
║   │ • config            │         └─────────────────────┘                        ║
║   └─────────────────────┘                                                         ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
"""


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def get_connection() -> sqlite3.Connection | None:
    """Get a connection to the shared demo database."""
    if not SHARED_DB.exists():
        return None
    conn = sqlite3.connect(str(SHARED_DB))
    conn.row_factory = sqlite3.Row
    return conn


def format_timestamp(ts: str | None) -> str:
    """Format ISO timestamp to readable form."""
    if not ts:
        return "-"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts[:16] if len(ts) >= 16 else ts


def truncate(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return "-"
    text = str(text).replace("\n", " ")
    return text[:max_len-3] + "..." if len(text) > max_len else text


def print_box(title: str, width: int = 80) -> None:
    """Print a boxed title."""
    print()
    print("╔" + "═" * (width - 2) + "╗")
    padding = (width - 2 - len(title)) // 2
    print("║" + " " * padding + title + " " * (width - 2 - padding - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def print_section(title: str, char: str = "─", width: int = 70) -> None:
    """Print a section header."""
    print()
    print(f"  {char * 3} {title} " + char * (width - len(title) - 6))


# ═══════════════════════════════════════════════════════════════════════════════
# DATA DISPLAY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def get_table_stats(conn: sqlite3.Connection) -> list[tuple[str, int, str]]:
    """Get all tables with row counts and sample data indicators."""
    cursor = conn.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]
    
    stats = []
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            # Get column names
            cols = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
            col_names = ", ".join(c[1] for c in cols[:5])
            if len(cols) > 5:
                col_names += f" (+{len(cols)-5} more)"
            stats.append((table, count, col_names))
        except Exception:
            stats.append((table, -1, "error"))
    
    return stats


def show_overview(conn: sqlite3.Connection) -> None:
    """Show database overview."""
    print_box("SPINE-CORE SHARED DATA STORE")
    
    # Database info
    print(f"\n  Database: {SHARED_DB}")
    if SHARED_DB.exists():
        size_kb = SHARED_DB.stat().st_size / 1024
        mtime = datetime.fromtimestamp(SHARED_DB.stat().st_mtime)
        print(f"  Size: {size_kb:.1f} KB")
        print(f"  Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Table summary
    stats = get_table_stats(conn)
    total_tables = len(stats)
    populated = sum(1 for _, count, _ in stats if count > 0)
    total_rows = sum(count for _, count, _ in stats if count > 0)
    
    print()
    print(f"  Tables: {total_tables} ({populated} with data)")
    print(f"  Total rows: {total_rows:,}")
    
    # Show table counts
    print_section("TABLE ROW COUNTS")
    
    # Populated tables first
    print("\n  ✓ POPULATED TABLES:")
    for table, count, cols in sorted(stats, key=lambda x: -x[1]):
        if count > 0:
            # Category indicator
            category = "⚙️" if "execution" in table else \
                      "📊" if "quality" in table or "anomal" in table else \
                      "🔔" if "alert" in table else \
                      "📅" if "schedule" in table else \
                      "🔒" if "lock" in table else \
                      "📁" if "source" in table else \
                      "📝"
            print(f"    {category} {table:40s} {count:>6,} rows")
    
    # Empty tables
    empty_count = sum(1 for _, count, _ in stats if count == 0)
    if empty_count > 0:
        print(f"\n  ○ EMPTY TABLES ({empty_count}):")
        for table, count, _ in sorted(stats, key=lambda x: x[0]):
            if count == 0:
                print(f"      {table}")


def show_schema() -> None:
    """Show the database schema diagram."""
    print(SCHEMA_DIAGRAM)


def show_table_data(conn: sqlite3.Connection, table: str, limit: int = 10) -> None:
    """Show sample data from a specific table."""
    print_section(f"TABLE: {table}")
    
    # Get column info
    cols = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
    col_names = [c[1] for c in cols]
    
    # Get row count
    count = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    print(f"  Rows: {count}, Columns: {len(col_names)}")
    print(f"  Columns: {', '.join(col_names[:8])}" + 
          (f" (+{len(col_names)-8} more)" if len(col_names) > 8 else ""))
    
    if count == 0:
        print("  (no data)")
        return
    
    # Get sample rows
    rows = conn.execute(f"SELECT * FROM [{table}] LIMIT {limit}").fetchall()
    
    # Display as compact table
    print()
    
    # Determine which columns to show (max 5)
    display_cols = col_names[:5]
    widths = [max(len(c), 12) for c in display_cols]
    
    # Header
    header = "  │ " + " │ ".join(c.ljust(widths[i]) for i, c in enumerate(display_cols))
    if len(col_names) > 5:
        header += " │ ..."
    print(header)
    print("  │" + "─" * (len(header) - 3))
    
    # Rows
    for row in rows:
        values = []
        for i, col in enumerate(display_cols):
            val = row[col] if col in row.keys() else row[i]
            val_str = truncate(str(val) if val is not None else "-", widths[i])
            values.append(val_str.ljust(widths[i]))
        print("  │ " + " │ ".join(values) + (" │ ..." if len(col_names) > 5 else ""))
    
    if count > limit:
        print(f"  │ ... ({count - limit} more rows)")


def show_samples(conn: sqlite3.Connection) -> None:
    """Show sample data from all populated tables."""
    stats = get_table_stats(conn)
    populated = [(t, c) for t, c, _ in stats if c > 0]
    
    print_box(f"SAMPLE DATA ({len(populated)} tables with data)")
    
    for table, count in sorted(populated, key=lambda x: -x[1]):
        show_table_data(conn, table, limit=5)


def show_anomalies(conn: sqlite3.Connection) -> None:
    """Show detailed anomaly report."""
    print_section("ANOMALY REPORT")
    
    count = conn.execute("SELECT COUNT(*) FROM core_anomalies").fetchone()[0]
    if count == 0:
        print("  No anomalies recorded.")
        return
    
    print(f"\n  Total anomalies: {count}")
    
    # By severity
    by_sev = conn.execute("""
        SELECT severity, COUNT(*) as cnt 
        FROM core_anomalies 
        GROUP BY severity 
        ORDER BY cnt DESC
    """).fetchall()
    
    print("\n  By Severity:")
    sev_icons = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵", "CRITICAL": "⛔"}
    for row in by_sev:
        icon = sev_icons.get(row[0], "⚪")
        print(f"    {icon} {row[0]:12s} {row[1]:>4}")
    
    # By category
    by_cat = conn.execute("""
        SELECT category, COUNT(*) as cnt 
        FROM core_anomalies 
        GROUP BY category 
        ORDER BY cnt DESC
    """).fetchall()
    
    print("\n  By Category:")
    for row in by_cat:
        print(f"    • {row[0]:20s} {row[1]:>4}")
    
    # Recent anomalies
    recent = conn.execute("""
        SELECT severity, category, domain, message, detected_at, resolved_at
        FROM core_anomalies 
        ORDER BY detected_at DESC 
        LIMIT 10
    """).fetchall()
    
    print("\n  Recent Anomalies:")
    for row in recent:
        status = "✓ RESOLVED" if row[5] else "⊘ OPEN"
        print(f"    [{row[0]:5s}] {row[1]:15s} {truncate(row[3], 40)}")
        print(f"             {status} | {row[2]} | {format_timestamp(row[4])}")


def show_executions(conn: sqlite3.Connection) -> None:
    """Show execution summary."""
    print_section("EXECUTION SUMMARY")
    
    count = conn.execute("SELECT COUNT(*) FROM core_executions").fetchone()[0]
    if count == 0:
        print("  No executions recorded.")
        return
    
    print(f"\n  Total executions: {count}")
    
    # By status
    by_status = conn.execute("""
        SELECT status, COUNT(*) as cnt 
        FROM core_executions 
        GROUP BY status 
        ORDER BY cnt DESC
    """).fetchall()
    
    print("\n  By Status:")
    status_icons = {"completed": "✅", "running": "🔄", "failed": "❌", 
                    "cancelled": "⏹️", "pending": "⏳"}
    for row in by_status:
        icon = status_icons.get(row[0].lower() if row[0] else "?", "⚪")
        print(f"    {icon} {row[0] or 'unknown':15s} {row[1]:>4}")
    
    # By workflow
    by_wf = conn.execute("""
        SELECT workflow, COUNT(*) as cnt 
        FROM core_executions 
        WHERE workflow IS NOT NULL
        GROUP BY workflow 
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    
    if by_wf:
        print("\n  Top Workflows:")
        for row in by_wf:
            print(f"    • {truncate(row[0], 35):35s} {row[1]:>4} runs")


def show_watermarks(conn: sqlite3.Connection) -> None:
    """Show watermark tracking."""
    print_section("WATERMARK TRACKING")
    
    count = conn.execute("SELECT COUNT(*) FROM core_watermarks").fetchone()[0]
    if count == 0:
        print("  No watermarks recorded.")
        return
    
    print(f"\n  Total watermarks: {count}")
    
    watermarks = conn.execute("""
        SELECT domain, source, partition_key, high_water, updated_at
        FROM core_watermarks 
        ORDER BY updated_at DESC
        LIMIT 20
    """).fetchall()
    
    print("\n  Domain                     Source             High Water")
    print("  " + "─" * 70)
    for row in watermarks:
        print(f"  {truncate(row[0], 25):25s}  {truncate(row[1], 18):18s}  {truncate(row[3], 25)}")


def show_relationship_map(conn: sqlite3.Connection) -> None:
    """Show relationships between data."""
    print_section("DATA RELATIONSHIPS")
    
    # Check for linked data
    print("\n  Cross-table connections:")
    
    # Executions with events
    exec_with_events = conn.execute("""
        SELECT COUNT(DISTINCT e.id) 
        FROM core_executions e
        JOIN core_execution_events ee ON e.id = ee.execution_id
    """).fetchone()[0]
    total_exec = conn.execute("SELECT COUNT(*) FROM core_executions").fetchone()[0]
    print(f"    • Executions with events: {exec_with_events}/{total_exec}")
    
    # Check workflow runs with steps
    try:
        wf_with_steps = conn.execute("""
            SELECT COUNT(DISTINCT wr.id) 
            FROM core_workflow_runs wr
            JOIN core_workflow_steps ws ON wr.id = ws.workflow_run_id
        """).fetchone()[0]
        total_wf = conn.execute("SELECT COUNT(*) FROM core_workflow_runs").fetchone()[0]
        if total_wf > 0:
            print(f"    • Workflow runs with steps: {wf_with_steps}/{total_wf}")
    except Exception:
        pass
    
    # Sources with fetches
    try:
        src_with_fetch = conn.execute("""
            SELECT COUNT(DISTINCT s.id) 
            FROM core_sources s
            JOIN core_source_fetches sf ON s.id = sf.source_id
        """).fetchone()[0]
        total_src = conn.execute("SELECT COUNT(*) FROM core_sources").fetchone()[0]
        if total_src > 0:
            print(f"    • Sources with fetch history: {src_with_fetch}/{total_src}")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Display spine-core example data with rich formatting"
    )
    parser.add_argument("--schema", action="store_true", 
                       help="Show database schema diagram")
    parser.add_argument("--samples", action="store_true",
                       help="Show sample data from all tables")
    parser.add_argument("--table", type=str,
                       help="Show data from specific table")
    parser.add_argument("--anomalies", action="store_true",
                       help="Show detailed anomaly report")
    parser.add_argument("--executions", action="store_true",
                       help="Show execution summary")
    parser.add_argument("--watermarks", action="store_true",
                       help="Show watermark tracking")
    parser.add_argument("--all", action="store_true",
                       help="Show everything")
    
    args = parser.parse_args()
    
    # Show schema (doesn't need DB)
    if args.schema:
        show_schema()
        if not args.all:
            return
    
    # Connect to database
    conn = get_connection()
    if conn is None:
        print(f"\n❌ Database not found: {SHARED_DB}")
        print("\n   Run examples with SPINE_EXAMPLES_PERSIST=1 to create data:")
        print("   $ python examples/run_all.py")
        return 0  # Not a failure — just no data yet
    
    try:
        # Default: show overview
        if not any([args.samples, args.table, args.anomalies, 
                   args.executions, args.watermarks, args.all]):
            show_overview(conn)
            return
        
        if args.all or args.samples:
            show_overview(conn)
        
        if args.all or args.anomalies:
            show_anomalies(conn)
        
        if args.all or args.executions:
            show_executions(conn)
        
        if args.all or args.watermarks:
            show_watermarks(conn)
        
        if args.all:
            show_relationship_map(conn)
        
        if args.samples:
            show_samples(conn)
        
        if args.table:
            show_table_data(conn, args.table, limit=20)
            
    finally:
        conn.close()
    
    print()


if __name__ == "__main__":
    exit(main() or 0)
