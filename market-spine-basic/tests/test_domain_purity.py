"""
Tests for domain purity - ensuring spine.domains.* doesn't import forbidden infra libs.

Domain code should only depend on:
- spine.core (primitives)
- Standard library
- Pure computation libraries (dataclasses, decimal, datetime, etc.)

Forbidden dependencies:
- sqlite3, asyncpg, psycopg2 (DB drivers)
- celery, redis (orchestration)
- requests, httpx, aiohttp (HTTP clients)
- boto3, azure-storage (cloud SDKs)
- fastapi, flask, django (web frameworks)

This ensures domains remain shareable across tiers.
"""

import ast
from pathlib import Path

import pytest

# Forbidden imports that indicate tier-specific infrastructure
FORBIDDEN_MODULES = {
    # Database drivers
    "sqlite3",
    "asyncpg",
    "psycopg2",
    "pymongo",
    "redis",
    # Orchestration
    "celery",
    "dramatiq",
    "rq",
    # HTTP clients
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    # Cloud SDKs
    "boto3",
    "botocore",
    "azure",
    "google.cloud",
    # Web frameworks
    "fastapi",
    "flask",
    "django",
    "tornado",
    "sanic",
    # Async frameworks
    "asyncio",  # Domains should be sync-only
    "trio",
    "anyio",
}


def extract_imports(file_path: Path) -> set[str]:
    """
    Extract all top-level module imports from a Python file.

    Returns set of top-level module names (e.g., "requests", "boto3").
    """
    with file_path.open(encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(file_path))
        except SyntaxError:
            # Skip files with syntax errors
            return set()

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Extract top-level module (e.g., "boto3" from "boto3.s3")
                top_level = alias.name.split(".")[0]
                imports.add(top_level)

        elif isinstance(node, ast.ImportFrom) and node.module:
            # Extract top-level module
            top_level = node.module.split(".")[0]
            imports.add(top_level)

    return imports


class TestDomainPurity:
    """Tests for domain code purity (no infrastructure dependencies)."""

    def test_otc_domain_has_no_forbidden_imports(self):
        """Test that spine.domains.finra.otc_transparency doesn't import forbidden infrastructure libs."""
        # Look in packages directory since code moved there
        domain_path = (
            Path(__file__).parent.parent.parent
            / "packages/spine-domains/finra/otc-transparency/src/spine/domains/finra/otc_transparency"
        )

        if not domain_path.exists():
            pytest.skip("spine.domains.finra.otc_transparency folder not found")

        violations = []

        # Check all Python files in the domain
        for py_file in domain_path.glob("**/*.py"):
            if py_file.name.startswith("__"):
                continue  # Skip __init__.py, __pycache__

            imports = extract_imports(py_file)
            forbidden_found = imports & FORBIDDEN_MODULES

            if forbidden_found:
                violations.append(
                    {
                        "file": py_file.name,
                        "imports": sorted(forbidden_found),
                    }
                )

        assert len(violations) == 0, "Found forbidden imports in domain code:\n" + "\n".join(
            f"  {v['file']}: {v['imports']}" for v in violations
        )

    def test_domains_only_import_spine_core(self):
        """
        Test that domain logic doesn't import from market_spine.

        Exception: pipelines.py can import from spine.framework (for registration),
        but calculation/normalizer/connector logic should only use spine.core.
        """
        domain_path = (
            Path(__file__).parent.parent.parent
            / "packages/spine-domains/finra/otc-transparency/src/spine/domains/finra/otc_transparency"
        )

        if not domain_path.exists():
            pytest.skip("spine.domains.finra.otc_transparency folder not found")

        violations = []

        for py_file in domain_path.glob("**/*.py"):
            if py_file.name.startswith("__"):
                continue

            # Allow pipelines.py to import from spine.framework (for registration)
            if py_file.name == "pipelines.py":
                continue

            imports = extract_imports(py_file)

            # Check for market_spine imports (should use spine.core instead)
            if "market_spine" in imports:
                violations.append(
                    {
                        "file": py_file.name,
                        "issue": "imports from market_spine (should use spine.core)",
                    }
                )

        assert len(violations) == 0, (
            "Domain logic should not import from market_spine (except pipelines.py):\n"
            + "\n".join(f"  {v['file']}: {v['issue']}" for v in violations)
        )

    def test_no_asyncio_in_domains(self):
        """Test that domain code doesn't use asyncio (should be sync-only)."""
        domain_path = (
            Path(__file__).parent.parent.parent
            / "packages/spine-domains/finra/otc-transparency/src/spine/domains/finra/otc_transparency"
        )

        if not domain_path.exists():
            pytest.skip("spine.domains.finra.otc_transparency folder not found")

        violations = []

        for py_file in domain_path.glob("**/*.py"):
            if py_file.name.startswith("__"):
                continue

            # Check file content for async keywords
            content = py_file.read_text(encoding="utf-8")

            # Look for async def or await keywords
            if "async def" in content or "await " in content:
                violations.append(py_file.name)

        assert len(violations) == 0, (
            "Domains should be sync-only (no async/await):\n  " + "\n  ".join(violations)
        )
