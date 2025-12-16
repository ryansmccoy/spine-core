#!/usr/bin/env python3
"""Standalone verification of example run results.

Reads both dialect and ORM SQLite databases and produces a detailed
comparison report.  Can also dump individual execution records.

Usage::

    # Full verification report
    python examples/verify_results.py

    # Show all recorded executions
    python examples/verify_results.py --executions

    # Show events for a specific execution
    python examples/verify_results.py --events <execution_id>

    # Dump everything to JSON
    python examples/verify_results.py --dump
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_EXAMPLES_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _EXAMPLES_DIR / "results"
_DIALECT_DB = _RESULTS_DIR / "dialect_examples.db"
_ORM_DB = _RESULTS_DIR / "orm_examples.db"


# ---------------------------------------------------------------------------
# Low-level queries (work without spine imports)
# ---------------------------------------------------------------------------


def _connect(path: Path) -> sqlite3.Connection | None:
    """Open a read-only SQLite connection, or None if missing."""
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    except Exception:
        return -1


def _get_executions(conn: sqlite3.Connection) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT id, workflow, params, status, lane, trigger_source, "
            "created_at, started_at, completed_at, result, error, retry_count "
            "FROM core_executions ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _get_events(conn: sqlite3.Connection, execution_id: str) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT id, execution_id, event_type, timestamp, data "
            "FROM core_execution_events WHERE execution_id = ? ORDER BY timestamp",
            (execution_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def table_comparison(dialect: sqlite3.Connection | None, orm: sqlite3.Connection | None) -> None:
    """Print side-by-side table row counts."""
    print("\n" + "=" * 70)
    print("TABLE ROW COUNT COMPARISON")
    print("=" * 70)

    d_tables = set(_get_tables(dialect)) if dialect else set()
    o_tables = set(_get_tables(orm)) if orm else set()
    all_tables = sorted(d_tables | o_tables)

    if not all_tables:
        print("  No tables found in either database.")
        return

    if dialect and orm:
        print(f"\n  {'Table':<38} {'Dialect':>8} {'ORM':>8} {'Match':>7}")
        print(f"  {'-'*38} {'-'*8} {'-'*8} {'-'*7}")
        for t in all_tables:
            d = _count(dialect, t) if dialect and t in d_tables else -1
            o = _count(orm, t) if orm and t in o_tables else -1
            d_str = str(d) if d >= 0 else "-"
            o_str = str(o) if o >= 0 else "-"
            match = "OK" if d == o else "DIFF"
            print(f"  {t:<38} {d_str:>8} {o_str:>8} {match:>7}")
    else:
        db = dialect or orm
        label = "Dialect" if dialect else "ORM"
        tables = d_tables if dialect else o_tables
        print(f"\n  {'Table':<38} {label:>8}")
        print(f"  {'-'*38} {'-'*8}")
        for t in sorted(tables):
            c = _count(db, t)
            print(f"  {t:<38} {c:>8}")


def execution_report(conn: sqlite3.Connection, label: str) -> list[dict]:
    """Print execution summary for one database."""
    execs = _get_executions(conn)

    print(f"\n  {label} DB: {len(execs)} executions")

    if not execs:
        return execs

    # Group by status
    by_status: dict[str, int] = {}
    for e in execs:
        s = e.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    for status, count in sorted(by_status.items()):
        print(f"    {status:<12} {count:>4}")

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for e in execs:
        params = json.loads(e.get("params") or "{}")
        cat = params.get("example_category", "unknown")
        by_cat.setdefault(cat, []).append(e)

    print(f"\n  By category:")
    for cat in sorted(by_cat):
        cat_execs = by_cat[cat]
        passed = sum(1 for x in cat_execs if x["status"] == "completed")
        failed = sum(1 for x in cat_execs if x["status"] == "failed")
        other = len(cat_execs) - passed - failed
        parts = [f"{passed} pass"]
        if failed:
            parts.append(f"{failed} fail")
        if other:
            parts.append(f"{other} other")
        print(f"    {cat:<25} {len(cat_execs):>3} runs  ({', '.join(parts)})")

    return execs


def list_executions(conn: sqlite3.Connection, label: str) -> None:
    """Print detailed execution list."""
    execs = _get_executions(conn)

    print(f"\n{'=' * 70}")
    print(f"EXECUTIONS — {label} DB ({len(execs)} total)")
    print("=" * 70)

    for e in execs:
        params = json.loads(e.get("params") or "{}")
        duration = params.get("duration_seconds", "?")
        status_marker = "PASS" if e["status"] == "completed" else "FAIL"
        print(f"\n  [{status_marker}] {e['workflow']}")
        print(f"    ID       : {e['id']}")
        print(f"    Status   : {e['status']}")
        print(f"    Duration : {duration}s")
        print(f"    Created  : {e.get('created_at', '?')}")

        if e.get("error"):
            print(f"    Error    : {e['error'][:120]}")


def show_events(conn: sqlite3.Connection, execution_id: str) -> None:
    """Print events for a specific execution."""
    events = _get_events(conn, execution_id)

    if not events:
        print(f"  No events found for execution {execution_id}")
        return

    print(f"\n  Events for {execution_id} ({len(events)} total):")
    for ev in events:
        data = json.loads(ev.get("data") or "{}")
        ts = ev.get("timestamp", "?")
        print(f"    [{ev['event_type']:<15}] {ts}")
        if ev["event_type"] == "stdout" and "lines" in data:
            for line in data["lines"][:5]:
                print(f"      | {line}")
            if len(data["lines"]) > 5:
                print(f"      ... ({len(data['lines'])} lines total)")


def dump_all(dialect: sqlite3.Connection | None, orm: sqlite3.Connection | None) -> None:
    """Dump all data to JSON."""
    output = {"dialect": {}, "orm": {}}

    for label, conn in [("dialect", dialect), ("orm", orm)]:
        if not conn:
            continue
        tables = _get_tables(conn)
        for t in tables:
            rows = conn.execute(f"SELECT * FROM [{t}]").fetchall()
            output[label][t] = [dict(r) for r in rows]

    dump_path = _RESULTS_DIR / "full_dump.json"
    with open(dump_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Dumped all data to: {dump_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify example run results")
    parser.add_argument("--executions", action="store_true", help="List all executions")
    parser.add_argument("--events", type=str, help="Show events for an execution ID")
    parser.add_argument("--dump", action="store_true", help="Dump all data to JSON")
    args = parser.parse_args()

    print("=" * 70)
    print("Example Results Verification")
    print("=" * 70)

    dialect = _connect(_DIALECT_DB)
    orm = _connect(_ORM_DB)

    print(f"\n  Dialect DB : {_DIALECT_DB} {'(found)' if dialect else '(missing)'}")
    print(f"  ORM DB     : {_ORM_DB} {'(found)' if orm else '(missing)'}")

    if not dialect and not orm:
        print("\n  No databases found. Run examples first:")
        print("    python examples/run_all.py")
        sys.exit(1)

    if args.dump:
        dump_all(dialect, orm)
        return

    if args.events:
        db = dialect or orm
        show_events(db, args.events)
        return

    # Table comparison
    table_comparison(dialect, orm)

    # Execution reports
    if dialect:
        execution_report(dialect, "Dialect")
        if args.executions:
            list_executions(dialect, "Dialect")

    if orm:
        execution_report(orm, "ORM")
        if args.executions:
            list_executions(orm, "ORM")

    # Cross-DB consistency check
    if dialect and orm:
        d_execs = _get_executions(dialect)
        o_execs = _get_executions(orm)

        d_workflows = {e["workflow"] for e in d_execs}
        o_workflows = {e["workflow"] for e in o_execs}

        only_dialect = d_workflows - o_workflows
        only_orm = o_workflows - d_workflows

        if only_dialect or only_orm:
            print("\n  CONSISTENCY ISSUES:")
            if only_dialect:
                print(f"    In dialect only: {len(only_dialect)}")
                for w in sorted(only_dialect):
                    print(f"      - {w}")
            if only_orm:
                print(f"    In ORM only: {len(only_orm)}")
                for w in sorted(only_orm):
                    print(f"      - {w}")
        else:
            print("\n  Both databases have identical workflow sets.")

    print()

    # Cleanup
    if dialect:
        dialect.close()
    if orm:
        orm.close()


if __name__ == "__main__":
    main()
