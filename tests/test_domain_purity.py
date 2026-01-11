"""
Domain purity guardrail tests.

These tests ensure that domain code doesn't import forbidden modules
that would couple it to specific infrastructure.

FORBIDDEN IMPORTS in spine.domains.*:
- sqlite3, asyncpg, psycopg2, psycopg (DB drivers)
- celery (task queue)
- redis (cache/queue)
- boto3, botocore (AWS SDK)
- httpx, requests, aiohttp (HTTP clients)

Domains should use:
- spine.core.* (platform primitives)
- Standard library (dataclasses, typing, enum, etc.)
- Pure computation libraries (decimal, statistics, etc.)
"""

import ast
import os
from pathlib import Path
from typing import Iterator


# Forbidden imports that indicate infrastructure coupling
FORBIDDEN_IMPORTS = {
    # Database drivers
    "sqlite3",
    "asyncpg",
    "psycopg2",
    "psycopg",
    "pymysql",
    "aiomysql",
    "aiosqlite",
    # Task queues
    "celery",
    "dramatiq",
    "rq",
    # Caching
    "redis",
    "memcache",
    # Cloud SDKs
    "boto3",
    "botocore",
    "google.cloud",
    "azure",
    # HTTP clients (domains shouldn't make HTTP calls)
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    # Other infrastructure
    "kafka",
    "pika",  # RabbitMQ
}


def get_domain_files(base_path: Path) -> Iterator[Path]:
    """Yield all Python files in spine/domains/."""
    domains_path = base_path / "src" / "spine" / "domains"
    if not domains_path.exists():
        return

    for py_file in domains_path.rglob("*.py"):
        yield py_file


def extract_imports(file_path: Path) -> list[str]:
    """Extract all import statements from a Python file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def check_forbidden_imports(file_path: Path, imports: list[str]) -> list[str]:
    """Check if any imports are forbidden."""
    violations = []
    for imp in imports:
        # Check both exact match and prefix match (e.g., "sqlite3" matches "sqlite3.Connection")
        top_module = imp.split(".")[0]
        if top_module in FORBIDDEN_IMPORTS:
            violations.append(f"{file_path}: imports '{imp}'")
    return violations


def test_domain_purity():
    """
    Test that domain code doesn't import forbidden infrastructure modules.

    This test should be run in CI to catch infrastructure coupling.
    """
    # Find the project root (where market-spine-basic is)
    test_dir = Path(__file__).parent
    project_root = test_dir.parent

    # Check all tier directories
    tier_dirs = [
        project_root / "market-spine-basic",
        project_root / "market-spine-intermediate",
        project_root / "market-spine-advanced",
        project_root / "market-spine-full",
    ]

    all_violations = []

    for tier_dir in tier_dirs:
        if not tier_dir.exists():
            continue

        for py_file in get_domain_files(tier_dir):
            imports = extract_imports(py_file)
            violations = check_forbidden_imports(py_file, imports)
            all_violations.extend(violations)

    if all_violations:
        violation_msg = "\n".join(all_violations)
        raise AssertionError(
            f"Domain purity violation! Domains must not import infrastructure modules:\n{violation_msg}"
        )


def test_domains_only_import_core():
    """
    Test that domain code only imports from allowed modules.

    Allowed:
    - spine.core.*
    - spine.domains.* (same or other domains)
    - Standard library
    - Type hints from typing module
    """
    # This is a softer check - just verify no FORBIDDEN imports
    test_domain_purity()


if __name__ == "__main__":
    # Run as script for quick check
    print("Checking domain purity...")

    project_root = Path(__file__).parent.parent

    violations = []
    for tier_dir in [
        project_root / "market-spine-basic",
        project_root / "market-spine-intermediate",
        project_root / "market-spine-advanced",
        project_root / "market-spine-full",
    ]:
        if not tier_dir.exists():
            continue

        for py_file in get_domain_files(tier_dir):
            imports = extract_imports(py_file)
            file_violations = check_forbidden_imports(py_file, imports)
            violations.extend(file_violations)

    if violations:
        print("❌ Domain purity violations found:")
        for v in violations:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ All domains are pure - no forbidden imports found")
        exit(0)
