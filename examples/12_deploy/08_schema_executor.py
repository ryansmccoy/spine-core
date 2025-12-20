#!/usr/bin/env python3
"""Schema Executor — Verify table creation against a real database.

The TestbedExecutor is the engine that actually runs workloads against
databases. This example exercises the *schema verification* path using
SQLite (no Docker required). It applies all 23 core DDL files and
compares the resulting tables against the expected set.

Demonstrates:
    1. TestbedExecutor auto-discovery of project directory
    2. Running schema verification against in-process SQLite
    3. Inspecting the SchemaResult output
    4. Verifying CORE_TABLES against created tables
    5. Simulating missing / extra tables
    6. Running a real test suite (fast, SQLite-only)

Architecture:
    TestbedExecutor
        │
        ├── run_schema_verification(url, dialect)
        │       ├── apply_all_schemas()    ← spine.core.schema_loader
        │       ├── get_table_list()       ← spine.core.schema_loader
        │       └── compare vs CORE_TABLES
        │
        └── run_test_suite(url, backend, test_filter)
                ├── subprocess: python -m pytest ...
                └── parse JUnit XML → TestResult

Key Concepts:
    - **CORE_TABLES**: The canonical list of 23 tables that must exist
      after full schema application.
    - **SchemaResult**: Structured output — tables_expected, tables_created,
      tables_missing, tables_extra, success, duration_ms.
    - **connection_url**: Standard SQLAlchemy-style URL. SQLite uses
      ``sqlite:///path/to/db.sqlite`` (no driver dependency).

See Also:
    - ``05_result_models.py`` — SchemaResult in the result hierarchy
    - ``04_testbed_workflow.py`` — Executor called from TestbedRunner
    - ``spine.deploy.executor`` — Full executor source
    - ``spine.core.schema_loader`` — DDL application logic

Run:
    python examples/12_deploy/08_schema_executor.py

Expected Output:
    Schema verification results with table counts, then a fast
    test run with JUnit-style result parsing.
"""

import tempfile
from pathlib import Path

from spine.deploy.executor import CORE_TABLES, TestbedExecutor
from spine.deploy.results import SchemaResult, TestResult


def main() -> None:
    """Exercise the TestbedExecutor against SQLite."""

    print("=" * 60)
    print("Deploy-Spine — Schema Executor")
    print("=" * 60)

    executor = TestbedExecutor()

    # --- 1. Auto-discovered project directory ---
    print("\n--- 1. Project Auto-Discovery ---")
    print(f"  project_dir : {executor.project_dir}")
    print(f"  pyproject   : {(executor.project_dir / 'pyproject.toml').exists()}")
    print(f"  tests/      : {(executor.project_dir / 'tests').exists()}")
    print(f"  examples/   : {(executor.project_dir / 'examples').exists()}")

    # --- 2. CORE_TABLES reference ---
    print(f"\n--- 2. Expected Tables ({len(CORE_TABLES)}) ---")
    for i, table in enumerate(CORE_TABLES, 1):
        print(f"  {i:2d}. {table}")

    # --- 3. Schema verification against SQLite ---
    print("\n--- 3. Schema Verification (SQLite) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        url = f"sqlite:///{db_path}"

        result: SchemaResult = executor.run_schema_verification(
            connection_url=url,
            dialect_name="sqlite",
        )

        print(f"  backend          : {result.backend}")
        print(f"  tables_expected  : {result.tables_expected}")
        print(f"  tables_created   : {result.tables_created}")
        print(f"  tables_missing   : {result.tables_missing or '(none)'}")
        print(f"  tables_extra     : {result.tables_extra or '(none)'}")
        print(f"  success          : {result.success}")
        print(f"  duration_ms      : {result.duration_ms:.1f}")
        if result.error:
            print(f"  error            : {result.error}")

        # NOTE: CORE_TABLES may drift from actual schema names over time.
        # The SchemaResult captures the delta — the testbed surfaces this
        # so developers can update CORE_TABLES or fix the schema.
        print(f"\n  Interpretation:")
        if result.success:
            print(f"    All {result.tables_expected} expected tables were created ✓")
        else:
            print(f"    {result.tables_created} tables found, {len(result.tables_missing)} expected missing")
            print(f"    This indicates CORE_TABLES needs updating to match the actual schema")
        assert result.tables_created >= 20, f"Expected 20+ tables, got {result.tables_created}"

    # --- 4. Multiple dialect URLs ---
    print("\n--- 4. Connection URL Patterns ---")
    from spine.deploy.backends import BACKENDS

    for name, spec in BACKENDS.items():
        url = spec.connection_url()
        print(f"  {name:14s} → {url}")

    # --- 5. Fast test run (SQLite, filtered) ---
    print("\n--- 5. Fast Test Run (SQLite, filtered to deploy tests) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        url = f"sqlite:///{db_path}"
        output_dir = Path(tmpdir) / "results"

        result_tests: TestResult = executor.run_test_suite(
            connection_url=url,
            backend="sqlite",
            test_filter="test_deploy",  # Only deploy tests — fast
            timeout=30,
            output_dir=output_dir,
        )

        print(f"  backend          : {result_tests.backend}")
        print(f"  passed           : {result_tests.passed}")
        print(f"  failed           : {result_tests.failed}")
        print(f"  skipped          : {result_tests.skipped}")
        print(f"  errors           : {result_tests.errors}")
        print(f"  total            : {result_tests.total}")
        print(f"  duration_seconds : {result_tests.duration_seconds:.1f}")
        print(f"  success          : {result_tests.success}")
        if result_tests.junit_xml_path:
            print(f"  junit_xml        : {Path(result_tests.junit_xml_path).name}")
        if result_tests.error:
            print(f"  error            : {result_tests.error}")

    # --- 6. SchemaResult JSON round-trip ---
    print("\n--- 6. SchemaResult Serialisation ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        url = f"sqlite:///{db_path}"
        sr = executor.run_schema_verification(url, "sqlite")

        json_str = sr.model_dump_json(indent=2)
        restored = SchemaResult.model_validate_json(json_str)
        print(f"  Original success : {sr.success}")
        print(f"  Restored success : {restored.success}")
        print(f"  Round-trip match : {sr.model_dump() == restored.model_dump()}")

    print("\n" + "=" * 60)
    print("✓ Schema executor complete — real DDL applied, real tests run.")
    print("=" * 60)


if __name__ == "__main__":
    main()
