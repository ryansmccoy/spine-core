#!/usr/bin/env python3
"""Log Collector — Structured output, summaries, and HTML reports.

The log collector organises testbed and deployment output into a clean
directory tree with JSON summaries and optional HTML reports. This
example demonstrates the full collection lifecycle without needing
Docker.

Demonstrates:
    1. Creating a LogCollector with run-scoped output directory
    2. Creating per-backend subdirectories
    3. Writing JSON summaries from result models
    4. Generating HTML reports
    5. Services log organisation
    6. Directory structure conventions

Architecture:
    TestbedRunResult ──▶ LogCollector ──▶  {output_dir}/{run_id}/
                                           ├── summary.json
                                           ├── report.html
                                           ├── postgresql/
                                           │   ├── schema.json
                                           │   └── container.log
                                           └── mysql/
                                               ├── schema.json
                                               └── container.log

Key Concepts:
    - **LogCollector**: Creates structured output directories per run
    - **write_summary()**: Serialises TestbedRunResult → summary.json
    - **write_html_report()**: Renders results as a browsable HTML page
    - **backend_dir()**: Returns (or creates) the directory for a backend

See Also:
    - ``04_testbed_workflow.py`` — LogCollector in a full testbed run
    - ``05_result_models.py`` — The result models that feed into logs
    - ``spine.deploy.log_collector`` — Module source

Run:
    python examples/12_deploy/06_log_collector.py

Expected Output:
    Directory listing of generated output structure with file sizes.
"""

import json
import tempfile
from pathlib import Path

from spine.deploy.log_collector import LogCollector
from spine.deploy.results import (
    BackendResult,
    DeploymentResult,
    OverallStatus,
    SchemaResult,
    ServiceStatus,
    TestbedRunResult,
    TestResult,
)


def _make_sample_result() -> TestbedRunResult:
    """Build a sample TestbedRunResult for demonstration."""
    pg = BackendResult(
        backend="postgresql",
        image="postgres:16-alpine",
        startup_ms=1200.0,
        schema_result=SchemaResult(
            backend="postgresql",
            tables_expected=23,
            tables_created=23,
            success=True,
            duration_ms=350.0,
        ),
        tests=TestResult(
            backend="postgresql",
            passed=58,
            failed=0,
            skipped=2,
            duration_seconds=12.5,
        ),
    )
    pg.overall_status = pg.compute_status()

    mysql = BackendResult(
        backend="mysql",
        image="mysql:8.0",
        startup_ms=2100.0,
        schema_result=SchemaResult(
            backend="mysql",
            tables_expected=23,
            tables_created=23,
            success=True,
            duration_ms=480.0,
        ),
        tests=TestResult(
            backend="mysql",
            passed=55,
            failed=3,
            skipped=2,
            duration_seconds=16.2,
        ),
    )
    mysql.overall_status = mysql.compute_status()

    result = TestbedRunResult(
        run_id="log-demo-001",
        backends=[pg, mysql],
    )
    result.mark_complete()
    return result


def main() -> None:
    """Demonstrate the LogCollector lifecycle."""

    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Log Collector")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = _make_sample_result()

        # --- 1. Create collector ---
        print("\n--- 1. Create LogCollector ---")
        collector = LogCollector(Path(tmpdir), result.run_id)
        print(f"  run_dir : {collector.run_dir}")
        print(f"  run_id  : {collector.run_id}")
        assert collector.run_dir.exists()
        print(f"  ✓ Output directory created")

        # --- 2. Backend directories ---
        print("\n--- 2. Backend Directories ---")
        for br in result.backends:
            bd = collector.backend_dir(br.backend)
            print(f"  Created : {bd.name}/")

            # Write simulated artifacts
            schema_data = br.schema_result.model_dump() if br.schema_result else {}
            (bd / "schema.json").write_text(json.dumps(schema_data, indent=2))

            test_data = br.tests.model_dump() if br.tests else {}
            (bd / "test_results.json").write_text(json.dumps(test_data, indent=2))

            (bd / "container.log").write_text(
                f"Starting {br.backend}...\n"
                f"Ready to accept connections on port {5432 if br.backend == 'postgresql' else 3306}\n"
            )

        # --- 3. Services directory ---
        print("\n--- 3. Services Directory ---")
        svc_dir = collector.services_dir()
        (svc_dir / "spine-core-api.log").write_text("Uvicorn running on 0.0.0.0:12000\n")
        print(f"  Created : {svc_dir.name}/")

        # --- 4. Write summary ---
        print("\n--- 4. Write Summary (JSON) ---")
        collector.write_summary(result)
        summary_path = collector.run_dir / "summary.json"
        if summary_path.exists():
            size = summary_path.stat().st_size
            # Peek at the summary
            summary = json.loads(summary_path.read_text())
            print(f"  File    : summary.json ({size} bytes)")
            print(f"  run_id  : {summary.get('run_id', 'N/A')}")
            print(f"  status  : {summary.get('overall_status', 'N/A')}")

        # --- 5. Write HTML report ---
        print("\n--- 5. Write HTML Report ---")
        collector.write_html_report(result)
        report_path = collector.run_dir / "report.html"
        if report_path.exists():
            size = report_path.stat().st_size
            content = report_path.read_text()
            print(f"  File    : report.html ({size} bytes)")
            print(f"  Has <html> tag : {'<html>' in content.lower()}")
            print(f"  Has status     : {'PASSED' in content or 'PARTIAL' in content}")

        # --- 6. Full directory listing ---
        print("\n--- 6. Output Directory Structure ---")
        print(f"  {collector.run_dir.name}/")
        for item in sorted(collector.run_dir.rglob("*")):
            rel = item.relative_to(collector.run_dir)
            depth = len(rel.parts) - 1
            indent = "    " + "  " * depth
            if item.is_dir():
                print(f"{indent}📁 {item.name}/")
            else:
                size = item.stat().st_size
                print(f"{indent}📄 {item.name} ({size} bytes)")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Log collector demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
