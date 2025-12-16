#!/usr/bin/env python3
"""Run all spine-core examples, record results to dual SQLite databases.

Uses :class:`ExampleRegistry` for auto-discovery and :mod:`_db` for
persistent run recording.  After all examples complete, prints a
verification report comparing the dialect and ORM databases.

Usage::

    # Run all examples with persistent recording
    python examples/run_all.py

    # Verify results only (skip running)
    python examples/run_all.py --verify-only

    # Run a single category
    python examples/run_all.py --category 01_core

    # Show detailed table population
    python examples/run_all.py --verify-only --detail

Configuration is read from ``examples/.env`` — see ``_db.py`` for
environment variable documentation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from _db import (
    _DIALECT_DB_PATH,
    _ORM_DB_PATH,
    _RESULTS_DIR,
    get_example_connection,
    get_orm_connection,
    load_env,
    print_table_counts,
    record_example_run,
)
from _registry import ExampleInfo, ExampleRegistry


# ---------------------------------------------------------------------------
# Run one example
# ---------------------------------------------------------------------------


def run_example(
    ex: ExampleInfo,
    *,
    timeout: int = 120,
) -> tuple[bool, list[str], float]:
    """Run a single example via subprocess.

    Returns (success, stdout_lines, duration_seconds).
    """
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(ex.path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=ex.path.parent.parent,  # Run from examples/
        )
        duration = time.monotonic() - t0
        all_output = result.stdout + result.stderr
        lines = [ln for ln in all_output.splitlines() if ln.strip()]

        if result.returncode == 0:
            return True, lines, duration
        else:
            return False, lines, duration

    except subprocess.TimeoutExpired:
        duration = time.monotonic() - t0
        return False, [f"TIMEOUT after {timeout}s"], duration
    except Exception as e:
        duration = time.monotonic() - t0
        return False, [f"ERROR: {e}"], duration


# ---------------------------------------------------------------------------
# Verify databases
# ---------------------------------------------------------------------------


def _count_table(conn: Any, table: str) -> int:
    """Count rows in a table, returning -1 on error."""
    try:
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    except Exception:
        return -1


def _get_all_tables(conn: Any) -> list[str]:
    """Get all core_* table names."""
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'core_%' ORDER BY name"
        ).fetchall()
        return [r[0] if isinstance(r, (tuple, list)) else r["name"] for r in rows]
    except Exception:
        return []


def verify_databases(
    dialect_conn: Any | None = None,
    orm_conn: Any | None = None,
    *,
    detail: bool = False,
) -> dict[str, Any]:
    """Compare row counts across both databases.

    Returns a summary dict with table-level comparison.
    """
    report: dict[str, Any] = {"dialect": {}, "orm": {}, "match": True}

    # Dialect DB
    if dialect_conn:
        tables = _get_all_tables(dialect_conn)
        for t in tables:
            report["dialect"][t] = _count_table(dialect_conn, t)

    # ORM DB
    if orm_conn:
        tables = _get_all_tables(orm_conn)
        for t in tables:
            report["orm"][t] = _count_table(orm_conn, t)

    # Compare
    all_tables = sorted(set(report["dialect"]) | set(report["orm"]))
    mismatches = []
    for t in all_tables:
        d = report["dialect"].get(t, -1)
        o = report["orm"].get(t, -1)
        if d != o:
            mismatches.append((t, d, o))
            report["match"] = False

    report["mismatches"] = mismatches
    report["total_tables"] = len(all_tables)

    return report


def print_verification_report(
    report: dict[str, Any],
    *,
    detail: bool = False,
) -> None:
    """Print a formatted verification report to stdout."""
    print("\n" + "=" * 70)
    print("DATABASE VERIFICATION REPORT")
    print("=" * 70)

    has_dialect = bool(report.get("dialect"))
    has_orm = bool(report.get("orm"))

    if not has_dialect and not has_orm:
        print("  No databases to verify (set SPINE_EXAMPLES_DB=file)")
        return

    print(f"\n  Tables found: {report.get('total_tables', 0)}")

    # Header
    if has_dialect and has_orm:
        print(f"\n  {'Table':<35} {'Dialect':>10} {'ORM':>10} {'Match':>7}")
        print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*7}")
    elif has_dialect:
        print(f"\n  {'Table':<35} {'Rows':>10}")
        print(f"  {'-'*35} {'-'*10}")

    all_tables = sorted(set(report.get("dialect", {})) | set(report.get("orm", {})))
    for t in all_tables:
        d = report.get("dialect", {}).get(t, -1)
        o = report.get("orm", {}).get(t, -1)

        if has_dialect and has_orm:
            d_str = str(d) if d >= 0 else "-"
            o_str = str(o) if o >= 0 else "-"
            match = "OK" if d == o else "MISMATCH"
            print(f"  {t:<35} {d_str:>10} {o_str:>10} {match:>7}")
        elif has_dialect:
            d_str = str(d) if d >= 0 else "-"
            print(f"  {t:<35} {d_str:>10}")

    if report.get("mismatches"):
        print(f"\n  WARNING: {len(report['mismatches'])} table(s) have mismatched counts!")
    elif has_dialect and has_orm:
        print(f"\n  All tables match between dialect and ORM databases.")

    # Execution summary
    for label, db_key in [("Dialect", "dialect"), ("ORM", "orm")]:
        counts = report.get(db_key, {})
        exec_count = counts.get("core_executions", 0)
        event_count = counts.get("core_execution_events", 0)
        if exec_count > 0:
            print(f"\n  {label} DB: {exec_count} executions, {event_count} events recorded")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all examples and produce verification report."""
    import argparse

    parser = argparse.ArgumentParser(description="Run spine-core examples")
    parser.add_argument("--verify-only", action="store_true", help="Skip running, just verify DBs")
    parser.add_argument("--category", type=str, help="Run only this category (e.g. 01_core)")
    parser.add_argument("--detail", action="store_true", help="Show detailed table info")
    parser.add_argument("--timeout", type=int, default=120, help="Per-example timeout (seconds)")
    args = parser.parse_args()

    # Load .env from examples/ directory
    load_env()

    # Banner
    print("=" * 70)
    print("Spine-Core Examples Runner  (persistent + tagged)")
    print("=" * 70)

    # Set up databases
    dialect_conn, dialect_info = get_example_connection()
    print(f"\n  Dialect DB : {dialect_info.resolved_path or dialect_info.url or 'in-memory'}")

    orm_result = get_orm_connection()
    orm_conn = None
    if orm_result:
        orm_conn, orm_engine, orm_info = orm_result
        print(f"  ORM DB     : {orm_info.resolved_path or orm_info.url}")
    else:
        print("  ORM DB     : disabled (set SPINE_EXAMPLES_ORM_DB=file)")

    if args.verify_only:
        report = verify_databases(dialect_conn, orm_conn, detail=args.detail)
        print_verification_report(report, detail=args.detail)

        # Save report JSON
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = _RESULTS_DIR / "verification_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report saved to: {report_path}")
        return

    # Discover
    registry = ExampleRegistry()
    if args.category:
        examples = registry.by_category(args.category)
        if not examples:
            print(f"\n  No examples found in category '{args.category}'")
            print(f"  Available: {', '.join(registry.categories)}")
            sys.exit(1)
    else:
        examples = list(registry.examples)

    print(f"\n  Discovered {len(examples)} examples across {len(registry.categories)} categories")
    for cat in registry.categories:
        if args.category and cat != args.category:
            continue
        cat_examples = registry.by_category(cat)
        print(f"    [{cat}] {len(cat_examples)} examples")

    # Run
    results: list[tuple[ExampleInfo, bool, list[str], float]] = []
    total = len(examples)

    for idx, ex in enumerate(examples, 1):
        print(f"\n{'─' * 70}")
        print(f"  [{idx}/{total}] {ex.name}")
        print(f"  Title: {ex.title}")

        success, stdout_lines, duration = run_example(ex, timeout=args.timeout)
        results.append((ex, success, stdout_lines, duration))

        status_str = "PASS" if success else "FAIL"
        print(f"  Result: {status_str}  ({duration:.1f}s)")

        # Show last few lines
        for line in stdout_lines[-5:]:
            print(f"    | {line}")

        # Parse example number from name (e.g. "01_core/03_result_pattern" → 3)
        stem = ex.path.stem
        import re
        m = re.match(r"(\d+)_(.+)", stem)
        ex_number = int(m.group(1)) if m else 0
        ex_name = m.group(2) if m else stem

        # Record to dialect DB
        record_example_run(
            dialect_conn,
            category=ex.category,
            number=ex_number,
            name=ex_name,
            title=ex.title,
            status=status_str,
            stdout_lines=stdout_lines,
            duration_seconds=duration,
        )

        # Record to ORM DB
        if orm_conn:
            record_example_run(
                orm_conn,
                category=ex.category,
                number=ex_number,
                name=ex_name,
                title=ex.title,
                status=status_str,
                stdout_lines=stdout_lines,
                duration_seconds=duration,
            )

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("RESULTS SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, s, _, _ in results if s)
    failed = total - passed

    for ex, success, _, dur in results:
        mark = "PASS" if success else "FAIL"
        print(f"  [{mark}] {ex.name:<50} {dur:>6.1f}s")

    print(f"\n  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")

    # Failures detail
    if failed:
        print(f"\n  FAILURES ({failed}):")
        for ex, success, stdout_lines, _ in results:
            if not success:
                print(f"    {ex.name}")
                for line in stdout_lines[-3:]:
                    print(f"      | {line}")

    # Verification
    report = verify_databases(dialect_conn, orm_conn)
    print_verification_report(report)

    # Save results
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results_data = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "examples": [
            {
                "name": ex.name,
                "category": ex.category,
                "title": ex.title,
                "status": "PASS" if s else "FAIL",
                "duration_seconds": round(d, 3),
                "stdout_tail": lines[-5:] if lines else [],
            }
            for ex, s, lines, d in results
        ],
        "verification": report,
    }

    report_path = _RESULTS_DIR / "run_results.json"
    with open(report_path, "w") as f:
        json.dump(results_data, f, indent=2)
    print(f"\n  Results saved to: {report_path}")

    if failed > 0:
        sys.exit(1)

    print("\n  All examples passed!")


if __name__ == "__main__":
    main()
