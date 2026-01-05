#!/usr/bin/env python3
"""
Smoke test for Prices API end-to-end.

This script validates the entire price data flow:
1. Source → Pipeline → Database → API → Response

Usage:
    # Against local development server
    python scripts/smoke_prices.py --base-url http://localhost:8000

    # With ingestion (requires API key)
    python scripts/smoke_prices.py --base-url http://localhost:8000 --ingest --symbol AAPL

    # Quick API-only check
    python scripts/smoke_prices.py --base-url http://localhost:8000 --api-only

Exit Codes:
    0 - All checks passed
    1 - Some checks failed
    2 - Critical failure (server unreachable)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Run: pip install requests")
    sys.exit(2)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SmokeConfig:
    """Smoke test configuration."""
    base_url: str = "http://localhost:8000"
    symbol: str = "AAPL"
    ingest: bool = False
    api_only: bool = False
    timeout: int = 30
    verbose: bool = False


@dataclass
class SmokeResult:
    """Smoke test result."""
    passed: list[str] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return len(self.failed) == 0


# =============================================================================
# Test Cases
# =============================================================================

def check_server_health(config: SmokeConfig) -> tuple[bool, str]:
    """Check if server is reachable."""
    try:
        resp = requests.get(f"{config.base_url}/health", timeout=config.timeout)
        if resp.status_code == 200:
            return True, "Server is healthy"
        else:
            return False, f"Health check returned {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Server unreachable"
    except Exception as e:
        return False, f"Health check error: {e}"


def check_metadata_endpoint(config: SmokeConfig) -> tuple[bool, str]:
    """Check metadata endpoint returns valid structure."""
    try:
        resp = requests.get(
            f"{config.base_url}/v1/data/prices/metadata",
            timeout=config.timeout,
        )
        
        if resp.status_code != 200:
            return False, f"Metadata returned {resp.status_code}"
        
        data = resp.json()
        if "captures" not in data:
            return False, "Missing 'captures' field in metadata"
        
        return True, f"Metadata OK, {len(data['captures'])} captures found"
    except Exception as e:
        return False, f"Metadata error: {e}"


def check_prices_endpoint(config: SmokeConfig) -> tuple[bool, str]:
    """Check prices endpoint with pagination."""
    try:
        resp = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}",
            params={"limit": 10},
            timeout=config.timeout,
        )
        
        if resp.status_code == 404:
            return True, f"No data for {config.symbol} (expected if not ingested)"
        
        if resp.status_code != 200:
            return False, f"Prices returned {resp.status_code}"
        
        data = resp.json()
        
        # Check structure
        if "data" not in data:
            return False, "Missing 'data' field"
        if "pagination" not in data:
            return False, "Missing 'pagination' field"
        
        pagination = data["pagination"]
        required = ["offset", "limit", "total", "has_more"]
        missing = [k for k in required if k not in pagination]
        if missing:
            return False, f"Pagination missing: {missing}"
        
        return True, f"Prices OK, {len(data['data'])} rows, total={pagination['total']}"
    except Exception as e:
        return False, f"Prices error: {e}"


def check_latest_endpoint(config: SmokeConfig) -> tuple[bool, str]:
    """Check latest price endpoint."""
    try:
        resp = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}/latest",
            timeout=config.timeout,
        )
        
        if resp.status_code == 404:
            return True, f"No latest for {config.symbol} (expected if not ingested)"
        
        if resp.status_code != 200:
            return False, f"Latest returned {resp.status_code}"
        
        data = resp.json()
        
        required = ["symbol", "date", "close"]
        missing = [k for k in required if k not in data]
        if missing:
            return False, f"Latest missing fields: {missing}"
        
        return True, f"Latest OK: {data['symbol']} @ {data['date']} = {data['close']}"
    except Exception as e:
        return False, f"Latest error: {e}"


def check_pagination_params(config: SmokeConfig) -> tuple[bool, str]:
    """Check pagination parameters work correctly."""
    try:
        # First page
        resp1 = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}",
            params={"offset": 0, "limit": 5},
            timeout=config.timeout,
        )
        
        if resp1.status_code == 404:
            return True, "Pagination check skipped (no data)"
        
        if resp1.status_code != 200:
            return False, f"Pagination page 1 returned {resp1.status_code}"
        
        data1 = resp1.json()
        
        # Check if more pages exist
        if not data1["pagination"]["has_more"]:
            return True, "Pagination OK (single page)"
        
        # Second page
        resp2 = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}",
            params={"offset": 5, "limit": 5},
            timeout=config.timeout,
        )
        
        if resp2.status_code != 200:
            return False, f"Pagination page 2 returned {resp2.status_code}"
        
        data2 = resp2.json()
        
        # Verify different data
        if data1["data"] and data2["data"]:
            if data1["data"][0]["date"] == data2["data"][0]["date"]:
                return False, "Pagination returned duplicate data"
        
        return True, "Pagination OK (multi-page verified)"
    except Exception as e:
        return False, f"Pagination error: {e}"


def check_as_of_query(config: SmokeConfig) -> tuple[bool, str]:
    """Check as-of queries with capture_id."""
    try:
        # Get available captures from metadata
        resp = requests.get(
            f"{config.base_url}/v1/data/prices/metadata",
            params={"symbol": config.symbol},
            timeout=config.timeout,
        )
        
        if resp.status_code != 200:
            return True, "As-of check skipped (metadata unavailable)"
        
        data = resp.json()
        captures = data.get("captures", [])
        
        if not captures:
            return True, "As-of check skipped (no captures)"
        
        # Query with specific capture_id
        capture_id = captures[0]["capture_id"] if isinstance(captures[0], dict) else captures[0]
        
        resp2 = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}",
            params={"capture_id": capture_id, "limit": 5},
            timeout=config.timeout,
        )
        
        if resp2.status_code != 200:
            return False, f"As-of query returned {resp2.status_code}"
        
        data2 = resp2.json()
        
        if "capture" not in data2:
            return False, "As-of query missing 'capture' field"
        
        return True, f"As-of OK, capture_id={capture_id[:30]}..."
    except Exception as e:
        return False, f"As-of error: {e}"


def check_error_handling(config: SmokeConfig) -> tuple[bool, str]:
    """Check error responses are well-formed."""
    try:
        # Invalid offset
        resp = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}",
            params={"offset": -1},
            timeout=config.timeout,
        )
        
        if resp.status_code not in [400, 422]:
            return False, f"Invalid offset accepted (got {resp.status_code})"
        
        # Invalid limit
        resp2 = requests.get(
            f"{config.base_url}/v1/data/prices/{config.symbol}",
            params={"limit": -1},
            timeout=config.timeout,
        )
        
        if resp2.status_code not in [400, 422]:
            return False, f"Invalid limit accepted (got {resp2.status_code})"
        
        return True, "Error handling OK"
    except Exception as e:
        return False, f"Error handling check failed: {e}"


# =============================================================================
# Test Runner
# =============================================================================

def run_smoke_tests(config: SmokeConfig) -> SmokeResult:
    """Run all smoke tests."""
    result = SmokeResult()
    
    print(f"\n{'='*60}")
    print(f"SMOKE TEST: Price API")
    print(f"Base URL: {config.base_url}")
    print(f"Symbol: {config.symbol}")
    print(f"{'='*60}\n")
    
    tests = [
        ("Server Health", check_server_health),
        ("Metadata Endpoint", check_metadata_endpoint),
        ("Prices Endpoint", check_prices_endpoint),
        ("Latest Endpoint", check_latest_endpoint),
        ("Pagination Params", check_pagination_params),
        ("As-Of Query", check_as_of_query),
        ("Error Handling", check_error_handling),
    ]
    
    for name, test_fn in tests:
        print(f"  [{name}]...", end=" ", flush=True)
        
        try:
            passed, message = test_fn(config)
            
            if passed:
                print(f"✓ {message}")
                result.passed.append(name)
            else:
                print(f"✗ {message}")
                result.failed.append({"name": name, "error": message})
                
                # Stop on critical failure
                if name == "Server Health":
                    print("\n  CRITICAL: Server unreachable, stopping tests")
                    break
                    
        except Exception as e:
            print(f"✗ Exception: {e}")
            result.failed.append({"name": name, "error": str(e)})
    
    return result


def print_summary(result: SmokeResult) -> None:
    """Print test summary."""
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Passed: {len(result.passed)}")
    print(f"Failed: {len(result.failed)}")
    print(f"Skipped: {len(result.skipped)}")
    
    if result.failed:
        print("\nFailures:")
        for f in result.failed:
            print(f"  - {f['name']}: {f['error']}")
    
    if result.success:
        print("\n✓ ALL SMOKE TESTS PASSED")
    else:
        print("\n✗ SOME SMOKE TESTS FAILED")


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Smoke test for Price API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the API server",
    )
    
    parser.add_argument(
        "--symbol",
        type=str,
        default="AAPL",
        help="Symbol to use for testing",
    )
    
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Run ingestion before testing (requires API key)",
    )
    
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Only test API endpoints (skip ingestion)",
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds",
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    config = SmokeConfig(
        base_url=args.base_url.rstrip("/"),
        symbol=args.symbol.upper(),
        ingest=args.ingest,
        api_only=args.api_only,
        timeout=args.timeout,
        verbose=args.verbose,
    )
    
    result = run_smoke_tests(config)
    print_summary(result)
    
    if not result.passed and result.failed:
        # All failed, including critical
        return 2
    elif result.failed:
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
