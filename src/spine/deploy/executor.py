"""Test and task executors for deploy-spine.

Provides executors for running workloads against database backends:
schema verification, pytest suites, example scripts, smoke tests,
and arbitrary commands. Each executor method returns a typed result
model from :mod:`spine.deploy.results`.

Why This Matters — Financial Data Operations:
    After spinning up a PostgreSQL container, the testbed needs to:
    (1) apply all 23 core DDL files and verify table creation,
    (2) run 2000+ pytest cases with JUnit XML output,
    (3) optionally run example scripts. Each phase produces a typed
    result that feeds into the ``BackendResult`` aggregate.

Why This Matters — General Operations:
    The executor pattern separates "what to run" from "where to run it".
    ``TestbedExecutor`` can run locally or inside a Docker container by
    simply changing the ``project_dir`` and ``connection_url``.

Key Concepts:
    TestbedExecutor: Main class — ``run_schema_verification()``,
        ``run_test_suite()``, ``run_examples()``, ``run_smoke_test()``,
        ``run_command()``.
    CORE_TABLES: List of 23 expected tables after full schema application,
        used for verification.
    JUnit XML parsing: ``_parse_junit_xml()`` extracts pass/fail counts
        and failure messages from pytest's ``--junitxml`` output.

Architecture Decisions:
    - subprocess for test execution: Runs ``python -m pytest`` as a child
      process to isolate test state from the orchestrator.
    - ``SPINE_DATABASE_URL`` env var: The standard way to inject connection
      URLs into the test suite.
    - Auto-discovery of project_dir: Walks up from ``__file__`` to find
      ``pyproject.toml``, falling back to ``cwd``.
    - ``_get_connection()`` supports SQLite (direct) and SQLAlchemy
      (PostgreSQL, MySQL, etc.) — same as ``spine.api.deps.get_connection()``.

Best Practices:
    - Always use ``output_dir`` for JUnit XML — it enables structured
      log collection and CI artifact upload.
    - Set ``test_filter`` (pytest ``-k``) for focused testing during
      development; omit for CI full-suite runs.
    - Smoke tests require a live API — run after ``docker compose up``.

Related Modules:
    - :mod:`spine.deploy.workflow` — Orchestrates executor calls
    - :mod:`spine.deploy.results` — SchemaResult, TestResult, etc.
    - :mod:`spine.deploy.log_collector` — Persists executor outputs
    - :mod:`spine.core.schema_loader` — Schema application logic

Tags:
    executor, tests, schema, examples, pytest, junit, smoke
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from spine.deploy.results import (
    ExampleResult,
    ExampleRun,
    SchemaResult,
    SmokeResult,
    TestFailure,
    TestResult,
)

logger = logging.getLogger(__name__)

# Core tables expected after full schema application
CORE_TABLES = [
    "core_workflow_definitions",
    "core_workflow_runs",
    "core_workflow_steps",
    "core_operation_runs",
    "core_idempotency_keys",
    "core_quality_checks",
    "core_rejects",
    "core_anomaly_detections",
    "core_anomaly_rules",
    "core_processing_locks",
    "core_dlq_entries",
    "core_workflow_history",
    "core_scheduler_jobs",
    "core_scheduler_executions",
    "core_alert_channels",
    "core_alert_rules",
    "core_alert_events",
    "core_data_sources",
    "core_fetch_history",
    "core_temporal_series",
    "core_temporal_snapshots",
    "core_temporal_corrections",
]


class TestbedExecutor:
    """Executes test phases against database backends.

    Can run locally (native) or inside a Docker container. Uses
    the existing spine-core schema loader, test suite, and examples
    infrastructure.

    Parameters
    ----------
    project_dir
        Path to the spine-core project directory.
    """

    def __init__(self, project_dir: str | Path | None = None) -> None:
        self.project_dir = Path(project_dir) if project_dir else self._find_project_dir()

    @staticmethod
    def _find_project_dir() -> Path:
        """Auto-discover the spine-core project directory."""
        # Try relative to this file
        candidate = Path(__file__).resolve().parent.parent.parent.parent
        if (candidate / "pyproject.toml").exists():
            return candidate
        # Fallback: current working directory
        return Path.cwd()

    # ------------------------------------------------------------------
    # Schema verification
    # ------------------------------------------------------------------

    def run_schema_verification(
        self,
        connection_url: str,
        dialect_name: str,
        schema_dir: str | None = None,
    ) -> SchemaResult:
        """Apply all schemas and verify table creation.

        Uses the existing ``apply_all_schemas()`` from spine.core.schema_loader
        with dialect-specific SQL subdirectories.

        Parameters
        ----------
        connection_url
            Database connection URL.
        dialect_name
            Dialect name (sqlite, postgresql, mysql, db2, oracle).
        schema_dir
            Override schema directory. If None, uses dialect subdirectory.

        Returns
        -------
        SchemaResult
        """
        start = time.time()
        result = SchemaResult(
            backend=dialect_name,
            tables_expected=len(CORE_TABLES),
        )

        try:
            from spine.core.dialect import get_dialect
            from spine.core.schema_loader import SCHEMA_DIR, apply_all_schemas, get_table_list

            # Determine schema directory
            if schema_dir:
                target_dir = Path(schema_dir)
            elif dialect_name and dialect_name != "sqlite":
                target_dir = SCHEMA_DIR / dialect_name
            else:
                target_dir = SCHEMA_DIR

            # Get connection
            conn = self._get_connection(connection_url)

            try:
                # Apply schemas
                applied = apply_all_schemas(conn, schema_dir=target_dir)
                logger.info(
                    "schema.applied",
                    extra={"backend": dialect_name, "files": len(applied)},
                )

                # Verify tables
                dialect = get_dialect(dialect_name)
                tables = get_table_list(conn, dialect)
                result.tables_created = len(tables)

                # Compare against expected
                expected_set = set(CORE_TABLES)
                created_set = set(tables)
                result.tables_missing = sorted(expected_set - created_set)
                result.tables_extra = sorted(created_set - expected_set)
                result.success = len(result.tables_missing) == 0

            finally:
                if hasattr(conn, "close"):
                    conn.close()

        except Exception as e:
            result.error = str(e)
            result.success = False
            logger.error("schema.failed", extra={"backend": dialect_name, "error": str(e)})

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Test suite
    # ------------------------------------------------------------------

    def run_test_suite(
        self,
        connection_url: str,
        backend: str = "unknown",
        test_filter: str | None = None,
        timeout: int = 300,
        output_dir: Path | None = None,
    ) -> TestResult:
        """Run pytest against a database backend.

        Sets ``SPINE_DATABASE_URL`` and runs the test suite, capturing
        JUnit XML results.

        Parameters
        ----------
        connection_url
            Database connection URL.
        backend
            Backend name for result labeling.
        test_filter
            pytest ``-k`` filter expression.
        timeout
            Command timeout in seconds.
        output_dir
            Directory for JUnit XML output.

        Returns
        -------
        TestResult
        """
        result = TestResult(backend=backend)
        junit_path = None

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            junit_path = output_dir / f"{backend}_results.xml"

        cmd = [
            "python", "-m", "pytest",
            str(self.project_dir / "tests"),
            "--ignore=tests/test_docker_comprehensive.py",
            "--ignore=tests/integration",
            "--tb=short",
            "-q",
            "--timeout=10",
        ]
        if junit_path:
            cmd.extend(["--junitxml", str(junit_path)])
        if test_filter:
            cmd.extend(["-k", test_filter])

        env = {**os.environ, "SPINE_DATABASE_URL": connection_url}

        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_dir),
                env=env,
            )
            result.duration_seconds = time.time() - start

            # Parse JUnit XML if available
            if junit_path and junit_path.exists():
                result.junit_xml_path = str(junit_path)
                self._parse_junit_xml(junit_path, result)
            else:
                # Parse from output
                self._parse_pytest_output(proc.stdout, result)

            if proc.returncode != 0 and result.failed == 0 and result.errors == 0:
                result.error = f"pytest exited with code {proc.returncode}"

        except subprocess.TimeoutExpired:
            result.error = f"Test suite timed out after {timeout}s"
            result.duration_seconds = timeout
        except Exception as e:
            result.error = str(e)
            result.duration_seconds = time.time() - start

        return result

    # ------------------------------------------------------------------
    # Example scripts
    # ------------------------------------------------------------------

    def run_examples(
        self,
        connection_url: str,
        backend: str = "unknown",
        categories: list[str] | None = None,
        timeout: int = 120,
    ) -> ExampleResult:
        """Run example scripts against a database backend.

        Discovers examples using the ``examples/_registry.py`` infrastructure
        and runs each one, capturing output.

        Parameters
        ----------
        connection_url
            Database connection URL.
        backend
            Backend name for result labeling.
        categories
            Category directories to run (e.g., ``["01_core"]``). All if None.
        timeout
            Per-example timeout in seconds.

        Returns
        -------
        ExampleResult
        """
        result = ExampleResult(backend=backend)
        examples_dir = self.project_dir / "examples"

        if not examples_dir.exists():
            result.error = f"Examples directory not found: {examples_dir}"
            return result

        # Discover examples
        example_files = self._discover_examples(examples_dir, categories)
        result.total = len(example_files)

        env = {**os.environ, "SPINE_DATABASE_URL": connection_url}

        for example_path in example_files:
            run = ExampleRun(name=example_path.stem)
            start = time.time()

            try:
                proc = subprocess.run(
                    ["python", str(example_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(self.project_dir),
                    env=env,
                )
                run.duration_ms = (time.time() - start) * 1000
                run.output = proc.stdout[-2000:] if len(proc.stdout) > 2000 else proc.stdout

                if proc.returncode == 0:
                    run.status = "passed"
                    result.passed += 1
                else:
                    run.status = "failed"
                    run.error = proc.stderr[-1000:] if proc.stderr else f"Exit code {proc.returncode}"
                    result.failed += 1

            except subprocess.TimeoutExpired:
                run.status = "error"
                run.error = f"Timed out after {timeout}s"
                run.duration_ms = timeout * 1000
                result.failed += 1
            except Exception as e:
                run.status = "error"
                run.error = str(e)
                run.duration_ms = (time.time() - start) * 1000
                result.failed += 1

            result.results.append(run)

        return result

    # ------------------------------------------------------------------
    # Smoke tests
    # ------------------------------------------------------------------

    def run_smoke_test(
        self,
        api_url: str,
        backend: str = "unknown",
        timeout: int = 120,
    ) -> SmokeResult:
        """Run smoke tests against a live API.

        Uses the existing ``test_docker_comprehensive.py`` test module.

        Parameters
        ----------
        api_url
            Base URL of the running API (e.g., ``http://localhost:12000``).
        backend
            Backend name for result labeling.
        timeout
            Command timeout in seconds.

        Returns
        -------
        SmokeResult
        """
        result = SmokeResult(backend=backend, api_url=api_url)

        test_file = self.project_dir / "tests" / "test_docker_comprehensive.py"
        if not test_file.exists():
            result.error = f"Smoke test file not found: {test_file}"
            return result

        env = {**os.environ, "SPINE_API_URL": api_url}
        cmd = [
            "python", "-m", "pytest",
            str(test_file),
            "--tb=short",
            "-q",
        ]

        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_dir),
                env=env,
            )
            result.duration_seconds = time.time() - start
            self._parse_pytest_summary(proc.stdout, result)
        except subprocess.TimeoutExpired:
            result.error = f"Smoke tests timed out after {timeout}s"
            result.duration_seconds = timeout
        except Exception as e:
            result.error = str(e)
            result.duration_seconds = time.time() - start

        return result

    # ------------------------------------------------------------------
    # Generic script/command execution
    # ------------------------------------------------------------------

    def run_command(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int = 300,
    ) -> dict[str, Any]:
        """Run an arbitrary command, capturing output.

        Parameters
        ----------
        command
            Command and arguments.
        env
            Environment variables (merged with os.environ).
        cwd
            Working directory.
        timeout
            Command timeout in seconds.

        Returns
        -------
        dict
            Keys: exit_code, stdout, stderr, duration_seconds, error
        """
        full_env = {**os.environ, **(env or {})}
        start = time.time()

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or str(self.project_dir),
                env=full_env,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "duration_seconds": time.time() - start,
                "error": None,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "duration_seconds": timeout,
                "error": f"Command timed out after {timeout}s",
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "duration_seconds": time.time() - start,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_connection(connection_url: str) -> Any:
        """Create a database connection from a URL.

        Supports sqlite, postgresql (via psycopg2 or SQLAlchemy).
        """
        if connection_url.startswith("sqlite"):
            import sqlite3

            path = connection_url.replace("sqlite:///", "").replace("sqlite://", "")
            if path in ("", ":memory:"):
                return sqlite3.connect(":memory:")
            # Ensure parent directory exists
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            return sqlite3.connect(path)

        # For other backends, try SQLAlchemy
        try:
            from spine.core.orm.session import SAConnectionBridge, SpineSession, create_spine_engine

            engine = create_spine_engine(connection_url)
            session = SpineSession(bind=engine)
            return SAConnectionBridge(session)
        except ImportError as e:
            raise ImportError(
                f"SQLAlchemy is required for {connection_url.split(':')[0]} connections. "
                "Install with: pip install spine-core[postgresql]"
            ) from e

    @staticmethod
    def _parse_junit_xml(path: Path, result: TestResult) -> None:
        """Parse JUnit XML and populate TestResult."""
        try:
            tree = ElementTree.parse(path)
            root = tree.getroot()
            # Handle both <testsuites> and <testsuite> root
            if root.tag == "testsuites":
                suites = root.findall("testsuite")
            else:
                suites = [root]

            for suite in suites:
                result.passed += int(suite.get("tests", "0")) - int(suite.get("failures", "0")) - int(suite.get("errors", "0"))
                result.failed += int(suite.get("failures", "0"))
                result.errors += int(suite.get("errors", "0"))
                result.skipped += int(suite.get("skipped", "0"))

                for testcase in suite.findall(".//testcase"):
                    failure = testcase.find("failure")
                    if failure is not None:
                        result.failures.append(TestFailure(
                            name=f"{testcase.get('classname', '')}.{testcase.get('name', '')}",
                            message=failure.get("message", ""),
                            traceback=failure.text or "",
                        ))
                    error = testcase.find("error")
                    if error is not None:
                        result.failures.append(TestFailure(
                            name=f"{testcase.get('classname', '')}.{testcase.get('name', '')}",
                            message=error.get("message", ""),
                            traceback=error.text or "",
                        ))
        except Exception as e:
            logger.warning("junit.parse_failed", extra={"path": str(path), "error": str(e)})

    @staticmethod
    def _parse_pytest_output(output: str, result: TestResult) -> None:
        """Parse pytest summary line (e.g., '2036 passed, 3 skipped')."""
        import re

        # Match patterns like "2036 passed", "3 failed", "1 error"
        for match in re.finditer(r"(\d+)\s+(passed|failed|error|skipped|warnings)", output):
            count = int(match.group(1))
            category = match.group(2)
            if category == "passed":
                result.passed = count
            elif category == "failed":
                result.failed = count
            elif category == "error":
                result.errors = count
            elif category == "skipped":
                result.skipped = count

    @staticmethod
    def _parse_pytest_summary(output: str, result: SmokeResult) -> None:
        """Parse pytest summary for smoke test results."""
        import re

        for match in re.finditer(r"(\d+)\s+(passed|failed|skipped)", output):
            count = int(match.group(1))
            category = match.group(2)
            if category == "passed":
                result.passed = count
            elif category == "failed":
                result.failed = count
            elif category == "skipped":
                result.skipped = count

    @staticmethod
    def _discover_examples(
        examples_dir: Path,
        categories: list[str] | None = None,
    ) -> list[Path]:
        """Discover example scripts using numbering convention."""
        examples = []
        for category_dir in sorted(examples_dir.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith(("_", ".")):
                continue
            if categories and category_dir.name not in categories:
                continue
            for py_file in sorted(category_dir.glob("[0-9]*.py")):
                if py_file.name.startswith("_"):
                    continue
                examples.append(py_file)
        return examples
