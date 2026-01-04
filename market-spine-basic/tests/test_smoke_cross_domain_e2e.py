"""
Integration tests for cross-domain smoke tests.

These tests wrap the smoke_cross_domain.py script to ensure
cross-domain functionality works end-to-end.
"""

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
SMOKE_SCRIPT = SCRIPT_DIR / "smoke_cross_domain.py"


class TestCrossDomainSmokeE2E:
    """End-to-end tests for cross-domain functionality."""

    def test_smoke_script_exists(self):
        """Smoke test script exists."""
        assert SMOKE_SCRIPT.exists(), f"Smoke script not found: {SMOKE_SCRIPT}"

    def test_cross_domain_smoke_runs(self):
        """
        Run the cross-domain smoke test script.
        
        This executes the full end-to-end test suite including:
        - Basic cross-domain dependency
        - Year-boundary week handling
        - As-of dependency mode
        
        The script uses its own temporary database and fixtures,
        so it doesn't interfere with other tests.
        """
        # Run the smoke test script
        result = subprocess.run(
            ["uv", "run", "python", str(SMOKE_SCRIPT)],
            cwd=SCRIPT_DIR.parent,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for full E2E test
        )
        
        # Print output for debugging if test fails
        if result.returncode != 0:
            print("\n=== STDOUT ===", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            print("\n=== STDERR ===", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        
        # Script should exit with code 0 on success
        assert result.returncode == 0, f"Smoke test failed with exit code {result.returncode}"
        
        # Verify expected output patterns
        assert "Scenario 1: Basic Cross-Domain" in result.stdout
        assert "Scenario 2: Year-Boundary Week" in result.stdout
        assert "Scenario 3: As-Of Dependency" in result.stdout
        assert "cross-domain tests passed" in result.stdout

    @pytest.mark.skip(reason="Requires network or specific fixture setup")
    def test_cross_domain_with_real_calendar_api(self):
        """
        Test with real calendar API (when available).
        
        This test is skipped by default since it may require network access
        or specific configuration. Enable it when testing against a live
        calendar service.
        """
        # This would test integration with exchange_calendars package
        # or a live calendar API endpoint
        pass
