"""Structured log collection and reporting for deploy-spine.

Collects container logs, test results, and deployment artifacts
into a structured output directory with JSON summaries and
HTML reports. Every testbed run produces a self-contained
``{run_id}/`` directory that can be archived as a CI artifact.

Why This Matters — Financial Data Pipelines:
    When nightly testbed runs fail on MySQL but pass on PostgreSQL,
    the team needs to compare container logs, schema diffs, and test
    failures side-by-side. The LogCollector structures all output into
    per-backend directories with standardised file names.

Why This Matters — General Pipelines:
    Structured output enables CI artifact upload, Elasticsearch ingestion,
    and historical trend analysis. The HTML report provides an at-a-glance
    dashboard for non-technical stakeholders.

Key Concepts:
    LogCollector: Main class — creates ``{output_dir}/{run_id}/`` tree.
    write_summary(): Serialises TestbedRunResult/DeploymentResult → JSON.
    write_html_report(): Renders dark-themed HTML with status colours.
    backend_dir(): Returns (or creates) per-backend subdirectory.
    services_dir(): Returns (or creates) service logs subdirectory.

Architecture Decisions:
    - Directory-per-run: ``{output_dir}/{run_id}/`` ensures runs never
      collide, even in parallel CI.
    - Directory-per-backend: ``{run_id}/postgresql/``, ``{run_id}/mysql/``
      with standardised filenames (``schema.json``, ``tests.json``,
      ``container.log``, ``test_results.xml``).
    - HTML inline CSS: No external dependencies — the report is a single
      self-contained HTML file.
    - Dark theme: Matches spine-core's data-dense dashboard aesthetic.

Output Structure::

    {output_dir}/{run_id}/
    ├── summary.json
    ├── report.html
    ├── postgresql/
    │   ├── container.log
    │   ├── schema.json
    │   ├── tests.json
    │   └── test_results.xml
    ├── mysql/
    │   └── ...
    └── services/
        ├── spine-core-api.log
        └── postgres.log

Related Modules:
    - :mod:`spine.deploy.results` — Models serialised by the collector
    - :mod:`spine.deploy.workflow` — Invokes collector during testbed runs
    - :mod:`spine.deploy.container` — Source of container logs

Tags:
    logs, collector, artifacts, reporting, html, structured-output
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spine.deploy.results import (
    DeploymentResult,
    TestbedRunResult,
)

logger = logging.getLogger(__name__)


class LogCollector:
    """Collects and structures logs from deploy-spine runs.

    Creates an organized output directory with container logs,
    test results, and summary reports.

    Parameters
    ----------
    output_dir
        Base directory for output.
    run_id
        Unique run identifier.

    Output structure::

        {output_dir}/{run_id}/
        ├── summary.json
        ├── report.html
        ├── postgresql/
        │   ├── container.log
        │   ├── schema.json
        │   ├── test_results.xml
        │   └── examples.json
        ├── mysql/
        │   └── ...
        └── services/
            ├── spine-core-api.log
            └── postgres.log
    """

    def __init__(self, output_dir: Path, run_id: str) -> None:
        self.run_dir = output_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id

    def backend_dir(self, backend: str) -> Path:
        """Get or create the directory for a backend."""
        d = self.run_dir / backend
        d.mkdir(parents=True, exist_ok=True)
        return d

    def services_dir(self) -> Path:
        """Get or create the directory for service logs."""
        d = self.run_dir / "services"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Log capture
    # ------------------------------------------------------------------

    def capture_container_logs(self, container_name: str, backend: str) -> Path:
        """Save container logs to a file.

        Parameters
        ----------
        container_name
            Docker container name.
        backend
            Backend name (used as subdirectory).

        Returns
        -------
        Path
            Path to the log file.
        """
        from spine.deploy.container import ContainerManager

        try:
            mgr = ContainerManager()
            from spine.deploy.container import ContainerInfo

            # Create a minimal ContainerInfo for log collection
            info = ContainerInfo(
                container_id="",
                container_name=container_name,
                host="",
                port=0,
                internal_port=0,
                network="",
                image="",
            )
            logs = mgr.collect_logs(info)
        except Exception as e:
            logs = f"Failed to collect logs: {e}"

        log_path = self.backend_dir(backend) / "container.log"
        log_path.write_text(logs, encoding="utf-8")
        logger.debug("logs.captured", extra={"backend": backend, "path": str(log_path)})
        return log_path

    def capture_service_logs(self, container_name: str, service_name: str) -> Path:
        """Save service container logs to a file."""
        from spine.deploy.container import ContainerInfo, ContainerManager

        try:
            mgr = ContainerManager()
            info = ContainerInfo(
                container_id="",
                container_name=container_name,
                host="",
                port=0,
                internal_port=0,
                network="",
                image="",
            )
            logs = mgr.collect_logs(info)
        except Exception as e:
            logs = f"Failed to collect logs: {e}"

        log_path = self.services_dir() / f"{service_name}.log"
        log_path.write_text(logs, encoding="utf-8")
        return log_path

    def save_schema_result(self, result: Any, backend: str) -> Path:
        """Save schema verification result as JSON."""
        path = self.backend_dir(backend) / "schema.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_test_result(self, result: Any, backend: str) -> Path:
        """Save test result as JSON."""
        path = self.backend_dir(backend) / "tests.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path

    def capture_test_results(self, junit_xml: Path, backend: str) -> Path:
        """Copy JUnit XML to output directory."""
        dest = self.backend_dir(backend) / "test_results.xml"
        shutil.copy2(junit_xml, dest)
        return dest

    def save_example_result(self, result: Any, backend: str) -> Path:
        """Save example run result as JSON."""
        path = self.backend_dir(backend) / "examples.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Summary reports
    # ------------------------------------------------------------------

    def write_summary(self, result: TestbedRunResult | DeploymentResult) -> Path:
        """Write machine-readable summary JSON."""
        path = self.run_dir / "summary.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("summary.written", extra={"path": str(path)})
        return path

    def write_html_report(self, result: TestbedRunResult | DeploymentResult) -> Path:
        """Generate a human-readable HTML report.

        Parameters
        ----------
        result
            Testbed or deployment result.

        Returns
        -------
        Path
            Path to the generated HTML file.
        """
        if isinstance(result, TestbedRunResult):
            html = self._generate_testbed_html(result)
        else:
            html = self._generate_deployment_html(result)

        path = self.run_dir / "report.html"
        path.write_text(html, encoding="utf-8")
        logger.info("report.written", extra={"path": str(path)})
        return path

    # ------------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_testbed_html(result: TestbedRunResult) -> str:
        """Generate testbed HTML report."""
        status_color = {
            "PASSED": "#22c55e",
            "FAILED": "#ef4444",
            "PARTIAL": "#f59e0b",
            "ERROR": "#ef4444",
            "SKIPPED": "#6b7280",
            "RUNNING": "#3b82f6",
            "PENDING": "#6b7280",
        }

        backend_rows = ""
        for b in result.backends:
            color = status_color.get(b.overall_status.value, "#6b7280")
            schema_status = "✅" if (b.schema_result and b.schema_result.success) else "❌" if b.schema_result else "—"
            test_info = f"{b.tests.passed}/{b.tests.total}" if b.tests else "—"
            example_info = f"{b.examples.passed}/{b.examples.total}" if b.examples else "—"
            backend_rows += f"""
            <tr>
                <td><strong>{b.backend}</strong></td>
                <td>{b.image or "—"}</td>
                <td style="color: {color}; font-weight: bold;">{b.overall_status.value}</td>
                <td>{schema_status}</td>
                <td>{test_info}</td>
                <td>{example_info}</td>
                <td>{b.startup_ms:.0f}ms</td>
            </tr>"""

        overall_color = status_color.get(result.overall_status.value, "#6b7280")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>deploy-spine Testbed Report — {result.run_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f172a; color: #e2e8f0; padding: 2rem; }}
        h1 {{ color: #f8fafc; margin-bottom: 0.5rem; }}
        .meta {{ color: #94a3b8; margin-bottom: 2rem; }}
        .status-banner {{
            background: {overall_color}22;
            border: 1px solid {overall_color};
            border-radius: 8px;
            padding: 1rem 1.5rem;
            margin-bottom: 2rem;
            font-size: 1.1rem;
        }}
        .status-banner strong {{ color: {overall_color}; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th {{ text-align: left; padding: 0.75rem; background: #1e293b;
             color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; }}
        td {{ padding: 0.75rem; border-bottom: 1px solid #1e293b; }}
        tr:hover td {{ background: #1e293b44; }}
        .footer {{ margin-top: 2rem; color: #64748b; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <h1>🧪 deploy-spine Testbed Report</h1>
    <div class="meta">
        Run ID: {result.run_id} &nbsp;|&nbsp;
        Started: {result.started_at} &nbsp;|&nbsp;
        Duration: {result.duration_seconds:.1f}s
    </div>
    <div class="status-banner">
        <strong>{result.overall_status.value}</strong> — {result.summary}
    </div>
    <table>
        <thead>
            <tr>
                <th>Backend</th>
                <th>Image</th>
                <th>Status</th>
                <th>Schema</th>
                <th>Tests</th>
                <th>Examples</th>
                <th>Startup</th>
            </tr>
        </thead>
        <tbody>{backend_rows}
        </tbody>
    </table>
    <div class="footer">
        Generated by deploy-spine at {datetime.now(UTC).isoformat()}
    </div>
</body>
</html>"""

    @staticmethod
    def _generate_deployment_html(result: DeploymentResult) -> str:
        """Generate deployment HTML report."""
        status_color = {
            "running": "#22c55e",
            "healthy": "#22c55e",
            "unhealthy": "#ef4444",
            "exited": "#ef4444",
            "starting": "#f59e0b",
            "not_found": "#6b7280",
        }

        service_rows = ""
        for s in result.services:
            color = status_color.get(s.status, "#6b7280")
            ports = ", ".join(f"{k}:{v}" for k, v in s.ports.items()) if s.ports else "—"
            service_rows += f"""
            <tr>
                <td><strong>{s.name}</strong></td>
                <td>{s.image or "—"}</td>
                <td style="color: {color}; font-weight: bold;">{s.status}</td>
                <td>{ports}</td>
                <td>{s.uptime_seconds:.0f}s</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>deploy-spine Deployment Report — {result.run_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f172a; color: #e2e8f0; padding: 2rem; }}
        h1 {{ color: #f8fafc; margin-bottom: 0.5rem; }}
        .meta {{ color: #94a3b8; margin-bottom: 2rem; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th {{ text-align: left; padding: 0.75rem; background: #1e293b;
             color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; }}
        td {{ padding: 0.75rem; border-bottom: 1px solid #1e293b; }}
        tr:hover td {{ background: #1e293b44; }}
        .footer {{ margin-top: 2rem; color: #64748b; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <h1>🚀 deploy-spine Deployment Report</h1>
    <div class="meta">
        Run ID: {result.run_id} &nbsp;|&nbsp;
        Mode: {result.mode} &nbsp;|&nbsp;
        Duration: {result.duration_seconds:.1f}s &nbsp;|&nbsp;
        Status: {result.overall_status.value}
    </div>
    <table>
        <thead>
            <tr>
                <th>Service</th>
                <th>Image</th>
                <th>Status</th>
                <th>Ports</th>
                <th>Uptime</th>
            </tr>
        </thead>
        <tbody>{service_rows}
        </tbody>
    </table>
    <div class="footer">
        Generated by deploy-spine at {datetime.now(UTC).isoformat()} &nbsp;|&nbsp;
        {result.summary}
    </div>
</body>
</html>"""
