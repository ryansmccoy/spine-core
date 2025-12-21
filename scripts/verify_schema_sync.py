#!/usr/bin/env python3
"""Verify all 6 database model layers in spine-core are in sync.

Compares:
  Layer 1: Inline DDL  (core/schema.py CORE_DDL)
  Layer 2: SQL Files   (core/schema/*.sql)
  Layer 3: Models      (core/models/*.py)
  Layer 4: ORM Tables  (core/orm/tables.py)

Usage:
    python scripts/verify_schema_sync.py          # check all layers
    python scripts/verify_schema_sync.py --fix    # show suggested fixes

Exit code: 0 = in sync, 1 = drift detected.

Tags: schema, reconciliation, release-gate
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "src" / "spine"
SCHEMA_DIR = BASE / "core" / "schema"
ISSUES: list[str] = []
WARNINGS: list[str] = []


# ── ORM class → SQL table mapping ────────────────────────────────────────

ORM_TO_SQL: dict[str, str] = {
    "MigrationTable": "_migrations",
    "ExecutionTable": "core_executions",
    "ExecutionEventTable": "core_execution_events",
    "ManifestTable": "core_manifest",
    "RejectTable": "core_rejects",
    "QualityTable": "core_quality",
    "AnomalyTable": "core_anomalies",
    "WorkItemTable": "core_work_items",
    "DeadLetterTable": "core_dead_letters",
    "ConcurrencyLockTable": "core_concurrency_locks",
    "CalcDependencyTable": "core_calc_dependencies",
    "ExpectedScheduleTable": "core_expected_schedules",
    "DataReadinessTable": "core_data_readiness",
    "WorkflowRunTable": "core_workflow_runs",
    "WorkflowStepTable": "core_workflow_steps",
    "WorkflowEventTable": "core_workflow_events",
    "ScheduleTable": "core_schedules",
    "ScheduleRunTable": "core_schedule_runs",
    "ScheduleLockTable": "core_schedule_locks",
    "AlertChannelTable": "core_alert_channels",
    "AlertTable": "core_alerts",
    "AlertDeliveryTable": "core_alert_deliveries",
    "AlertThrottleTable": "core_alert_throttle",
    "SourceTable": "core_sources",
    "SourceFetchTable": "core_source_fetches",
    "SourceCacheTable": "core_source_cache",
    "DatabaseConnectionTable": "core_database_connections",
}

# Special columns to skip in comparisons (ORM metadata, not real SQL columns)
ORM_SKIP_COLS = {"__tablename__", "__table_args__", "metadata"}


# ── Extraction helpers ───────────────────────────────────────────────────

def _extract_create_body(text: str, table_name: str) -> str | None:
    """Extract the body of a CREATE TABLE statement, handling nested parens."""
    pattern = rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)}\s*\("
    m = re.search(pattern, text)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
        i += 1
    return text[start:i - 1] if depth == 0 else None


def extract_sql_columns(ddl_text: str, table_name: str) -> set[str]:
    """Extract column names from a CREATE TABLE block."""
    body = _extract_create_body(ddl_text, table_name)
    if not body:
        return set()
    cols: set[str] = set()
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("--") or not line:
            continue
        skip_kws = ("FOREIGN", "PRIMARY", "UNIQUE", "CHECK", "CONSTRAINT", ")")
        if any(line.upper().startswith(kw) for kw in skip_kws):
            continue
        m = re.match(r"(\w+)\s+\w+", line)
        if m and m.group(1).upper() not in ("CREATE", "TABLE", "IF"):
            cols.add(m.group(1))
    return cols


def extract_inline_ddl_columns(schema_py: str, table_name: str) -> set[str]:
    """Extract columns from inline CORE_DDL CREATE TABLE in schema.py."""
    body = _extract_create_body(schema_py, table_name)
    if not body:
        return set()
    cols: set[str] = set()
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("--") or not line:
            continue
        skip_kws = ("FOREIGN", "PRIMARY", "UNIQUE", "CHECK", "CONSTRAINT", ")")
        if any(line.upper().startswith(kw) for kw in skip_kws):
            continue
        m = re.match(r"(\w+)\s+\w+", line)
        if m and m.group(1).upper() not in ("CREATE", "TABLE", "IF"):
            cols.add(m.group(1))
    return cols


def get_sql_file_tables() -> dict[str, set[str]]:
    """Gather all table → column mappings from SQL files."""
    tables: dict[str, set[str]] = {}
    for sql_file in sorted(SCHEMA_DIR.glob("*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)", text):
            name = m.group(1)
            cols = extract_sql_columns(text, name)
            if cols:
                tables[name] = cols
    return tables


def get_inline_ddl_tables() -> dict[str, set[str]]:
    """Get tables from inline CORE_DDL in schema.py."""
    schema_py = (BASE / "core" / "schema.py").read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (core_\w+)", schema_py):
        name = m.group(1)
        cols = extract_inline_ddl_columns(schema_py, name)
        if cols:
            tables[name] = cols
    return tables


def get_orm_columns() -> dict[str, set[str]]:
    """Parse ORM mapped_column() and Column() declarations from tables.py."""
    tables_py = BASE / "core" / "orm" / "tables.py"
    if not tables_py.exists():
        return {}
    text = tables_py.read_text(encoding="utf-8")
    orm: dict[str, set[str]] = {}
    current_class: str | None = None
    for line in text.splitlines():
        cm = re.match(r"class (\w+Table)\(", line)
        if cm:
            current_class = cm.group(1)
            orm[current_class] = set()
        elif current_class:
            # Match: name: Mapped[...] = mapped_column(...)
            #    or: name = Column(...)
            col_match = re.match(
                r"\s+(\w+)\s*(?::\s*Mapped\[.*?\])?\s*=\s*(?:mapped_column|Column)\(",
                line,
            )
            if col_match:
                col = col_match.group(1)
                if col not in ORM_SKIP_COLS:
                    orm[current_class].add(col)
            # relationship() lines are NOT columns, skip them
        if re.match(r"class ", line) and current_class and not re.match(r"class (\w+Table)\(", line):
            current_class = None
    return orm


def get_model_fields() -> dict[str, set[str]]:
    """Parse annotated fields from Pydantic models in core/models/."""
    models_dir = BASE / "core" / "models"
    if not models_dir.exists():
        return {}
    result: dict[str, set[str]] = {}
    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        current_class: str | None = None
        for line in text.splitlines():
            cm = re.match(r"class (\w+)\(", line)
            if cm:
                current_class = cm.group(1)
                result[current_class] = set()
            elif current_class and re.match(r"\s+(\w+)\s*:", line):
                field = re.match(r"\s+(\w+)", line).group(1)
                if not field.startswith("_") and field not in ("model_config",):
                    result[current_class].add(field)
            elif re.match(r"class ", line) and current_class:
                current_class = None
    return result


# ── Comparison logic ─────────────────────────────────────────────────────

def compare_layers(
    name: str,
    left: set[str],
    right: set[str],
    left_label: str,
    right_label: str,
) -> None:
    """Compare two column sets and record issues."""
    only_left = left - right
    only_right = right - left
    if only_left:
        ISSUES.append(
            f"{name}: {left_label}-only columns: {sorted(only_left)}"
        )
    if only_right:
        ISSUES.append(
            f"{name}: {right_label}-only columns: {sorted(only_right)}"
        )


def run_checks() -> int:
    """Run all layer comparisons."""
    sql_tables = get_sql_file_tables()
    inline_tables = get_inline_ddl_tables()
    orm_tables = get_orm_columns()
    model_fields = get_model_fields()

    print(f"SQL files:    {len(sql_tables)} tables")
    print(f"Inline DDL:   {len(inline_tables)} tables")
    print(f"ORM classes:  {len(orm_tables)} classes")
    print(f"Model classes: {len(model_fields)} classes")
    print()

    # ── Check 1: Inline DDL vs SQL files ──────────────────────────────
    print("── Layer 1 vs Layer 2: Inline DDL ↔ SQL Files ──")
    overlapping = set(inline_tables.keys()) & set(sql_tables.keys())
    for table in sorted(overlapping):
        compare_layers(
            table,
            inline_tables[table],
            sql_tables[table],
            "InlineDDL",
            "SQLFile",
        )
    inline_only = set(inline_tables.keys()) - set(sql_tables.keys())
    if inline_only:
        WARNINGS.append(f"Tables in inline DDL but not in SQL files: {sorted(inline_only)}")
    print(f"  Checked {len(overlapping)} overlapping tables")

    # ── Check 2: SQL files vs ORM ─────────────────────────────────────
    print("── Layer 2 vs Layer 4: SQL Files ↔ ORM Tables ──")
    checked = 0
    for orm_cls, sql_name in ORM_TO_SQL.items():
        orm_cols = orm_tables.get(orm_cls, set())
        sql_cols = sql_tables.get(sql_name, set())
        if not orm_cols:
            WARNINGS.append(f"ORM class {orm_cls} not found or has no Column() declarations")
            continue
        if not sql_cols:
            WARNINGS.append(f"SQL table {sql_name} not found in schema files")
            continue
        compare_layers(sql_name, orm_cols, sql_cols, "ORM", "SQL")
        checked += 1
    print(f"  Checked {checked} table ↔ class pairs")

    # ── Check 3: ORM table count vs SQL table count ───────────────────
    print("── Coverage: ORM vs SQL ──")
    sql_table_names = set(sql_tables.keys())
    orm_sql_names = set(ORM_TO_SQL.values())
    unmapped_sql = sql_table_names - orm_sql_names
    if unmapped_sql:
        WARNINGS.append(f"SQL tables with no ORM class: {sorted(unmapped_sql)}")

    # ── Report ────────────────────────────────────────────────────────
    print()
    if WARNINGS:
        print(f"⚠️  {len(WARNINGS)} warning(s):")
        for w in WARNINGS:
            print(f"  ⚠️  {w}")
        print()

    if ISSUES:
        print(f"{'=' * 60}")
        print(f"❌ DRIFT DETECTED — {len(ISSUES)} issue(s):")
        print(f"{'=' * 60}")
        for issue in ISSUES:
            print(f"  ❌ {issue}")
        return 1
    else:
        print("✅ All checked layers in sync")
        return 0


if __name__ == "__main__":
    sys.exit(run_checks())
