#!/usr/bin/env python3
"""CI Artifacts — Structured output for continuous integration.

After a testbed run, CI pipelines need machine-readable artifacts
for test reporting, trend analysis, and failure triage. This example
shows how to produce a complete artifact directory from a testbed run
— including JSON summaries, HTML reports, JUnit XML, and per-backend
log directories.

Demonstrates:
    1. Running a real testbed against SQLite with artifact collection
    2. Inspecting the artifact directory structure
    3. Reading back the JSON summary
    4. HTML report generation
    5. JUnit XML for CI test reporters (dorny/test-reporter, etc.)
    6. Artifact upload patterns for GitHub Actions / GitLab CI

Architecture:
    TestbedRunner.run()
        └── LogCollector
            ├── write_summary()      → summary.json
            ├── write_html_report()  → report.html
            ├── save_schema_result() → {backend}/schema.json
            ├── save_test_result()   → {backend}/tests.json
            └── backend_dir()        → {backend}/ (JUnit XML, logs)

Key Concepts:
    - **LogCollector**: Creates ``{output_dir}/{run_id}/`` with all artifacts.
    - **summary.json**: Machine-readable aggregate result (CI exit code).
    - **report.html**: Self-contained dark-themed dashboard.
    - **JUnit XML**: Per-backend ``test_results.xml`` for CI reporters.
    - **schema.json**: Per-backend schema verification details.

See Also:
    - ``06_log_collector.py`` — LogCollector basics
    - ``08_schema_executor.py`` — Schema + test execution
    - ``11_cli_programmatic.py`` — Programmatic testbed runs
    - ``spine.deploy.log_collector`` — Full source

Run:
    python examples/12_deploy/12_ci_artifacts.py

Expected Output:
    A complete artifact directory with JSON, HTML, and per-backend
    results from a real SQLite testbed run.
"""

import json
import tempfile
from pathlib import Path

from spine.deploy.config import TestbedConfig
from spine.deploy.log_collector import LogCollector
from spine.deploy.results import OverallStatus
from spine.deploy.workflow import TestbedRunner


def main() -> None:
    """Produce CI artifacts from a real testbed run."""

    print("=" * 60)
    print("Deploy-Spine — CI Artifacts")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "testbed-results"

        # --- 1. Run testbed with artifact collection ---
        print("\n--- 1. Testbed Run with Artifact Collection ---")
        config = TestbedConfig(
            backends=["sqlite"],
            run_schema=True,
            run_tests=True,
            run_examples=False,
            test_filter="test_deploy",   # Fast — deploy tests only
            output_dir=output_dir,
            output_format="all",
        )
        print(f"  backends     : {config.backends}")
        print(f"  run_id       : {config.run_id}")
        print(f"  output_dir   : {output_dir}")
        print(f"  output_format: {config.output_format}")

        runner = TestbedRunner(config)
        result = runner.run()

        print(f"\n  Result: {result.overall_status.value}")
        print(f"  Duration: {result.duration_seconds:.1f}s")
        print(f"  Summary: {result.summary}")

        # --- 2. Artifact directory structure ---
        print("\n--- 2. Artifact Directory Structure ---")
        run_dir = output_dir / config.run_id
        if run_dir.exists():
            for item in sorted(run_dir.rglob("*")):
                rel = item.relative_to(run_dir)
                if item.is_dir():
                    print(f"  📁 {rel}/")
                else:
                    size = item.stat().st_size
                    print(f"  📄 {rel} ({size:,d} bytes)")
        else:
            print(f"  (No artifacts generated — run_dir: {run_dir})")

        # --- 3. Read back JSON summary ---
        print("\n--- 3. JSON Summary (summary.json) ---")
        summary_path = run_dir / "summary.json"
        if summary_path.exists():
            data = json.loads(summary_path.read_text())
            print(f"  run_id         : {data.get('run_id', 'N/A')}")
            print(f"  overall_status : {data.get('overall_status', 'N/A')}")
            print(f"  started_at     : {data.get('started_at', 'N/A')}")
            print(f"  completed_at   : {data.get('completed_at', 'N/A')}")
            print(f"  duration       : {data.get('duration_seconds', 0):.1f}s")
            backends = data.get("backends", [])
            print(f"  backends       : {len(backends)}")
            for b in backends:
                print(f"    {b['backend']:15s} → {b['overall_status']}")
        else:
            print("  (summary.json not found)")

        # --- 4. Per-backend artifacts ---
        print("\n--- 4. Per-Backend Artifacts ---")
        for br in result.backends:
            backend_dir = run_dir / br.backend
            if backend_dir.exists():
                print(f"\n  [{br.backend}/]")
                for f in sorted(backend_dir.iterdir()):
                    size = f.stat().st_size
                    print(f"    {f.name:25s} {size:>7,d} bytes")

                # Show schema.json content
                schema_file = backend_dir / "schema.json"
                if schema_file.exists():
                    schema = json.loads(schema_file.read_text())
                    print(f"    → tables: {schema.get('tables_created', '?')}/{schema.get('tables_expected', '?')}")

                # Show tests.json summary
                tests_file = backend_dir / "tests.json"
                if tests_file.exists():
                    tests = json.loads(tests_file.read_text())
                    print(f"    → tests: {tests.get('passed', 0)} passed, {tests.get('failed', 0)} failed")

        # --- 5. HTML report ---
        print("\n--- 5. HTML Report ---")
        report_path = run_dir / "report.html"
        if report_path.exists():
            content = report_path.read_text(encoding="utf-8", errors="replace")
            print(f"  File size    : {len(content):,d} bytes")
            print(f"  Has dark CSS : {'--bg-color' in content or 'dark' in content.lower()}")
            print(f"  Has PASSED   : {'PASSED' in content}")
            print(f"  Self-contained (no external CSS/JS): {content.startswith('<!DOCTYPE') or content.startswith('<html')}")
        else:
            print("  (report.html not found)")

        # --- 6. CI integration patterns ---
        print("\n--- 6. CI Integration Patterns ---")
        print()
        print("  GitHub Actions:")
        print("    - uses: dorny/test-reporter@v1")
        print("      with:")
        print("        name: SQLite Tests")
        print("        path: testbed-results/*/sqlite/sqlite_results.xml")
        print("        reporter: java-junit")
        print()
        print("    - uses: actions/upload-artifact@v4")
        print("      with:")
        print("        name: testbed-results")
        print("        path: testbed-results/")
        print()
        print("  GitLab CI:")
        print("    artifacts:")
        print("      reports:")
        print("        junit: testbed-results/*/*_results.xml")
        print("      paths:")
        print("        - testbed-results/")
        print()
        print("  Exit code:")
        exit_code = 0 if result.overall_status == OverallStatus.PASSED else 1
        print(f"    result.overall_status = {result.overall_status.value}")
        print(f"    exit_code = {exit_code}")
        print("    (PASSED → 0, FAILED/PARTIAL/ERROR → 1)")

    print("\n" + "=" * 60)
    print("✓ CI artifacts complete — all files produced in temp directory.")
    print("=" * 60)


if __name__ == "__main__":
    main()
