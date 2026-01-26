#!/usr/bin/env python3
"""
Error Handling Example - SpineError and Result[T] Pattern

This example demonstrates spine-core's structured error handling:
1. SpineError hierarchy with categories
2. Result[T] envelope pattern (Ok/Err)
3. Functional composition with map/flat_map
4. The try_result decorator for exception conversion

Run:
    cd market-spine-intermediate
    uv run python -m examples.error_handling
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

# Spine core imports
from spine.core.errors import (
    SpineError,
    SourceError,
    ValidationError,
    TransientError,
    ConfigError,
    ErrorCategory,
    ErrorContext,
    is_retryable,
)
from spine.core.result import Result, Ok, Err, try_result


# =============================================================================
# Example 1: SpineError Hierarchy
# =============================================================================


def demo_spine_errors():
    """Demonstrate SpineError types and their properties."""
    print("=" * 70)
    print("EXAMPLE 1: SpineError Hierarchy")
    print("=" * 70)
    print()
    
    # Source error - data not found
    source_err = SourceError(
        "FINRA OTC file not found: week_2025-07-04.psv",
        context=ErrorContext(
            source_name="finra.otc_transparency",
            url="https://api.finra.org/data/group/otcMarket/name/weeklyAts"
        ),
    )
    print(f"[SourceError]")
    print(f"  Message: {source_err.message}")
    print(f"  Category: {source_err.category}")
    print(f"  Retryable: {source_err.retryable}")
    print(f"  Context: pipeline={source_err.context.source_name}")
    print()
    
    # Validation error - schema violation
    validation_err = ValidationError(
        "shares_or_principal must be positive",
        context=ErrorContext(
            pipeline="finra.otc_transparency.normalize_week",
            metadata={"field": "shares_or_principal", "value": -100}
        ),
    )
    print(f"[ValidationError]")
    print(f"  Message: {validation_err.message}")
    print(f"  Category: {validation_err.category}")
    print(f"  Retryable: {validation_err.retryable}")
    print()
    
    # Transient error - network timeout (retryable)
    transient_err = TransientError(
        "API timeout after 30s",
        retry_after=60,
        context=ErrorContext(
            source_name="finra.api",
            http_status=504,
        ),
    )
    print(f"[TransientError]")
    print(f"  Message: {transient_err.message}")
    print(f"  Category: {transient_err.category}")
    print(f"  Retryable: {transient_err.retryable}")
    print(f"  Retry After: {transient_err.retry_after}s")
    print()
    
    # Config error - never retryable
    config_err = ConfigError(
        "Missing DATABASE_URL environment variable",
    )
    print(f"[ConfigError]")
    print(f"  Message: {config_err.message}")
    print(f"  Category: {config_err.category}")
    print(f"  Retryable: {config_err.retryable}")
    print()


# =============================================================================
# Example 2: Result[T] Pattern
# =============================================================================


@dataclass
class FinraRecord:
    """Example FINRA OTC record."""
    week_ending: str
    symbol: str
    tier: str
    shares: int
    trades: int


def parse_record(row: dict) -> Result[FinraRecord]:
    """Parse a raw row into a FinraRecord, returning Result."""
    try:
        # Validate required fields
        if not row.get("symbol"):
            return Err(ValidationError("Missing required field: symbol"))
        
        shares = int(row.get("shares", 0))
        if shares < 0:
            return Err(ValidationError(
                f"Invalid shares value: {shares}",
                context=ErrorContext(metadata={"symbol": row.get("symbol")})
            ))
        
        return Ok(FinraRecord(
            week_ending=row["week_ending"],
            symbol=row["symbol"],
            tier=row.get("tier", "unknown"),
            shares=shares,
            trades=int(row.get("trades", 0)),
        ))
    except (ValueError, KeyError) as e:
        return Err(ValidationError(f"Parse error: {e}"))


def enrich_record(record: FinraRecord) -> Result[dict]:
    """Enrich a record with additional computed fields."""
    if record.trades == 0:
        return Err(ValidationError("Cannot compute average: zero trades"))
    
    return Ok({
        "week_ending": record.week_ending,
        "symbol": record.symbol,
        "tier": record.tier,
        "shares": record.shares,
        "trades": record.trades,
        "avg_shares_per_trade": record.shares / record.trades,
    })


def demo_result_pattern():
    """Demonstrate Result[T] pattern with Ok/Err."""
    print("=" * 70)
    print("EXAMPLE 2: Result[T] Pattern")
    print("=" * 70)
    print()
    
    # Good data
    good_row = {
        "week_ending": "2025-07-04",
        "symbol": "AAPL",
        "tier": "NMS_TIER_1",
        "shares": "10000",
        "trades": "50",
    }
    
    result = parse_record(good_row)
    print(f"Parsing good data:")
    print(f"  is_ok: {result.is_ok()}")
    
    match result:
        case Ok(record):
            print(f"  Record: {record.symbol} - {record.shares} shares")
        case Err(error):
            print(f"  Error: {error}")
    print()
    
    # Bad data - negative shares
    bad_row = {
        "week_ending": "2025-07-04",
        "symbol": "BADCO",
        "shares": "-100",
        "trades": "5",
    }
    
    result = parse_record(bad_row)
    print(f"Parsing bad data:")
    print(f"  is_ok: {result.is_ok()}")
    
    match result:
        case Ok(record):
            print(f"  Record: {record}")
        case Err(error):
            print(f"  Error: {error.message}")
    print()
    
    # Chaining with map and flat_map
    print("Chaining with map/flat_map:")
    
    chain_result = (
        parse_record(good_row)
        .flat_map(enrich_record)
        .map(lambda d: {**d, "processed": True})
    )
    
    match chain_result:
        case Ok(data):
            print(f"  Enriched: avg_shares_per_trade = {data['avg_shares_per_trade']}")
        case Err(error):
            print(f"  Error: {error}")
    print()


# =============================================================================
# Example 3: try_result Function
# =============================================================================


def fetch_finra_data_impl(week: str) -> list[dict]:
    """
    Fetch FINRA data (simulated) - raises exceptions.
    """
    if week == "2025-01-01":
        raise SourceError("No data available for holiday week")
    
    if week == "2025-99-99":
        raise TransientError("API rate limited", retry_after=60)
    
    # Simulated success
    return [
        {"symbol": "AAPL", "shares": 10000},
        {"symbol": "MSFT", "shares": 8000},
    ]


def fetch_finra_data(week: str) -> Result[list[dict]]:
    """
    Fetch FINRA data wrapped in Result.
    
    Uses try_result to convert exceptions to Result.
    """
    return try_result(lambda: fetch_finra_data_impl(week))


def demo_try_result_function():
    """Demonstrate the try_result wrapper function."""
    print("=" * 70)
    print("EXAMPLE 3: try_result Wrapper")
    print("=" * 70)
    print()
    
    # Successful call - returns Ok
    result = fetch_finra_data("2025-07-04")
    print(f"Fetching 2025-07-04:")
    print(f"  is_ok: {result.is_ok()}")
    if result.is_ok():
        print(f"  Data: {len(result.unwrap())} records")
    print()
    
    # Source error - returns Err
    result = fetch_finra_data("2025-01-01")
    print(f"Fetching 2025-01-01 (holiday):")
    print(f"  is_ok: {result.is_ok()}")
    if result.is_err():
        err = result.error  # Access .error attribute for Err
        print(f"  Error: {err.message}")
        print(f"  Retryable: {err.retryable}")
    print()
    
    # Transient error - returns Err with retry_after
    result = fetch_finra_data("2025-99-99")
    print(f"Fetching 2025-99-99 (triggers rate limit):")
    print(f"  is_ok: {result.is_ok()}")
    if result.is_err():
        err = result.error  # Access .error attribute for Err
        print(f"  Error: {err.message}")
        print(f"  Retryable: {err.retryable}")
        print(f"  Retry After: {err.retry_after}s")
    print()


# =============================================================================
# Example 4: Error Classification with is_retryable
# =============================================================================


def demo_error_classification():
    """Demonstrate error classification for retry decisions."""
    print("=" * 70)
    print("EXAMPLE 4: Error Classification")
    print("=" * 70)
    print()
    
    errors = [
        SourceError("File not found"),
        ValidationError("Invalid schema"),
        TransientError("Connection timeout", retryable=True),
        ConfigError("Missing API key"),
        TransientError("Rate limited", retry_after=30),
    ]
    
    for error in errors:
        retryable = is_retryable(error)
        print(f"{error.__class__.__name__}:")
        print(f"  Message: {error.message}")
        print(f"  Category: {error.category.value}")
        print(f"  is_retryable: {retryable}")
        if error.retry_after:
            print(f"  Retry After: {error.retry_after}s")
        print()


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    # Windows console encoding fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    demo_spine_errors()
    print()
    demo_result_pattern()
    print()
    demo_try_result_function()
    print()
    demo_error_classification()
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("Key spine-core error handling patterns:")
    print("  1. SpineError hierarchy: SourceError, ValidationError, TransientError, ConfigError")
    print("  2. Result[T] pattern: Ok(value) | Err(error)")
    print("  3. Functional chaining: map(), flat_map(), and_then()")
    print("  4. try_result(): Convert exceptions to Result")
    print("  5. is_retryable(): Classify errors for retry decisions")
    print()
