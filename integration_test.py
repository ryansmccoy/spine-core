#!/usr/bin/env python3
"""
Integration test for spine-core Docker tiers.

Tests real API endpoints with actual workflow submission and retrieval.
Run against Tier 1 (minimal), Tier 2 (standard), and Tier 3 (full).
"""

import sys
import time
from typing import Dict, Any
import requests

API_BASE = "http://localhost:12000"
FRONTEND_BASE = "http://localhost:12001"


def test_health() -> bool:
    """Test /health endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ Health: {data.get('status')} (uptime: {data.get('uptime_s')}s)")
        return data.get("status") == "healthy"
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


def test_capabilities() -> bool:
    """Test /api/v1/capabilities endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/capabilities", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        caps = data.get("data", {})
        print(f"✓ Capabilities: database={caps.get('database')}, worker={caps.get('worker')}")
        return True
    except Exception as e:
        print(f"✗ Capabilities failed: {e}")
        return False


def test_database_health() -> bool:
    """Test /api/v1/database/health endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/database/health", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        db = data.get("data", {})
        print(f"✓ Database: connected={db.get('connected')}, dialect={db.get('dialect')}")
        return db.get("connected") is True
    except Exception as e:
        print(f"✗ Database health failed: {e}")
        return False


def test_submit_run() -> str | None:
    """Submit a test run and return run_id."""
    try:
        payload = {
            "kind": "workflow",
            "name": "test_integration_workflow",
            "params": {"test": "integration", "timestamp": time.time()}
        }
        resp = requests.post(f"{API_BASE}/api/v1/runs", json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        run_id = data.get("data", {}).get("run_id")
        print(f"✓ Run submitted: {run_id[:12]}...")
        return run_id
    except Exception as e:
        print(f"✗ Run submission failed: {e}")
        return None


def test_get_run(run_id: str) -> bool:
    """Retrieve run details."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/runs/{run_id}", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        run = data.get("data", {})
        print(f"✓ Run retrieved: status={run.get('status')}, pipeline={run.get('pipeline')}")
        return True
    except Exception as e:
        print(f"✗ Run retrieval failed: {e}")
        return False


def test_list_runs() -> bool:
    """List all runs."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/runs?limit=5", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        runs = data.get("data", [])
        print(f"✓ Runs listed: {len(runs)} runs found")
        return True
    except Exception as e:
        print(f"✗ List runs failed: {e}")
        return False


def test_workflows() -> bool:
    """List workflows."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/workflows", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        workflows = data.get("data", [])
        print(f"✓ Workflows: {len(workflows)} registered")
        return True
    except Exception as e:
        print(f"✗ Workflows failed: {e}")
        return False


def test_frontend() -> bool:
    """Test frontend is serving."""
    try:
        resp = requests.get(FRONTEND_BASE, timeout=5)
        resp.raise_for_status()
        print(f"✓ Frontend: serving (status={resp.status_code})")
        return True
    except Exception as e:
        print(f"✗ Frontend failed: {e}")
        return False


def run_integration_tests(tier_name: str) -> Dict[str, bool]:
    """Run all integration tests and return results."""
    print(f"\n{'='*60}")
    print(f"Testing {tier_name}")
    print(f"{'='*60}\n")
    
    results = {}
    
    # Core health tests
    results["health"] = test_health()
    results["capabilities"] = test_capabilities()
    results["database"] = test_database_health()
    results["frontend"] = test_frontend()
    
    # Workflow tests
    results["workflows_list"] = test_workflows()
    results["runs_list"] = test_list_runs()
    
    # End-to-end workflow test
    run_id = test_submit_run()
    if run_id:
        results["run_submit"] = True
        results["run_retrieve"] = test_get_run(run_id)
    else:
        results["run_submit"] = False
        results["run_retrieve"] = False
    
    # Summary
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'─'*60}")
    print(f"Results: {passed}/{total} tests passed ({passed*100//total}%)")
    print(f"{'─'*60}\n")
    
    return results


if __name__ == "__main__":
    """
    Usage:
        python integration_test.py [tier_name]
    
    Example:
        python integration_test.py "Tier 1: Minimal"
    """
    tier_name = sys.argv[1] if len(sys.argv) > 1 else "Unknown Tier"
    results = run_integration_tests(tier_name)
    
    # Exit with error code if any test failed
    if not all(results.values()):
        sys.exit(1)
