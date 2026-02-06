"""Integration tests that run spine-core examples as test cases.

These tests ensure all examples execute without errors and follow
best practices (docstrings, no external dependencies, etc.).

Run with:
    pytest tests/integration/test_examples.py -v -m integration
    pytest tests/integration/test_examples.py -v -k "ecosystem" -m integration
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Resolve examples directory
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


def get_ecosystem_examples():
    """Get ecosystem example files."""
    ecosystem_dir = EXAMPLES_DIR / "ecosystem"
    if not ecosystem_dir.exists():
        return []
    return [
        (f.stem, f)
        for f in ecosystem_dir.glob("*.py")
        if not f.name.startswith("_") and f.name != "run_all.py"
    ]


def get_main_examples():
    """Get main example files (not in subfolders)."""
    return [
        (f.stem, f)
        for f in EXAMPLES_DIR.glob("*.py")
        if not f.name.startswith("_") and f.name != "conftest.py"
    ]


@pytest.mark.integration
class TestEcosystemExamples:
    """Test ecosystem integration examples."""
    
    @pytest.mark.parametrize("name,path", get_ecosystem_examples())
    def test_ecosystem_example_runs(self, name, path):
        """Each ecosystem example should run without errors."""
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(EXAMPLES_DIR.parent),
            env={**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"},
        )
        
        assert result.returncode == 0, (
            f"Ecosystem example {name} failed:\n"
            f"STDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )
    
    @pytest.mark.parametrize("name,path", get_ecosystem_examples())
    def test_ecosystem_example_has_docstring(self, name, path):
        """Each ecosystem example should have a module docstring."""
        content = path.read_text(encoding="utf-8-sig")  # Handle BOM
        lines = content.strip().split("\n")
        
        # Skip shebang if present
        start_idx = 1 if lines[0].startswith("#!") else 0
        
        # Check for docstring
        has_docstring = (
            lines[start_idx].startswith('"""') or
            lines[start_idx].startswith("'''")
        )
        
        assert has_docstring, f"Ecosystem example {name} missing module docstring"


@pytest.mark.integration
@pytest.mark.slow
class TestMainExamples:
    """Test main example files (slow - runs actual examples)."""
    
    @pytest.mark.parametrize("name,path", get_main_examples())
    def test_main_example_runs(self, name, path):
        """Each main example should run without errors."""
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=120,  # Longer timeout for main examples
            cwd=str(EXAMPLES_DIR.parent),
            env={**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"},
        )
        
        assert result.returncode == 0, (
            f"Main example {name} failed:\n"
            f"STDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )


@pytest.mark.integration
class TestMockLayer:
    """Test the mock layer used by examples."""
    
    def test_mock_imports(self):
        """Mock layer should be importable."""
        from examples.mock import (
            MockAPIBase,
            MockResponse,
            MockEntitySpine,
            MockFeedSpine,
            MOCK_COMPANIES,
        )
        
        assert MockAPIBase is not None
        assert len(MOCK_COMPANIES) > 0
    
    @pytest.mark.asyncio
    async def test_mock_entityspine_resolve(self):
        """MockEntitySpine should resolve known companies."""
        from examples.mock import MockEntitySpine
        
        api = MockEntitySpine(latency_ms=1)
        
        # Test CIK resolution
        result = await api.resolve_by_cik("0000320193")
        assert result.success
        assert result.data["name"] == "Apple Inc."
        
        # Test ticker resolution
        result = await api.resolve_by_ticker("MSFT")
        assert result.success
        assert result.data["name"] == "Microsoft Corporation"
        
        # Test unknown CIK
        result = await api.resolve_by_cik("9999999999")
        assert not result.success
    
    @pytest.mark.asyncio
    async def test_mock_feedspine_deduplication(self):
        """MockFeedSpine should track deduplication."""
        from examples.mock import MockFeedSpine
        
        api = MockFeedSpine(latency_ms=1)
        
        # First collection - all new
        result1 = await api.collect("sec_filings")
        assert result1.success
        assert result1.data["new"] > 0
        assert result1.data["duplicates"] == 0
        
        # Second collection - all duplicates
        result2 = await api.collect("sec_filings")
        assert result2.success
        assert result2.data["new"] == 0
        assert result2.data["duplicates"] > 0


@pytest.mark.slow
class TestRunAll:
    """Test the run_all.py scripts (slow - runs all examples)."""
    
    def test_run_all_ecosystem(self):
        """run_all.py should execute all ecosystem examples."""
        run_all = EXAMPLES_DIR / "ecosystem" / "run_all.py"
        if not run_all.exists():
            pytest.skip("run_all.py not found")
        
        result = subprocess.run(
            [sys.executable, str(run_all)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(EXAMPLES_DIR.parent),
            env={**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"},
        )
        
        # Check output contains summary
        assert "SUMMARY" in result.stdout or "SUMMARY" in result.stderr
