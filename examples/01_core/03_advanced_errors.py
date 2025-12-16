#!/usr/bin/env python3
"""Advanced Error Handling — SpineError Hierarchy with Result[T] Integration.

================================================================================
WHY A CUSTOM ERROR HIERARCHY?
================================================================================

Generic ``Exception`` tells you *something* went wrong but not *what kind*::

    except Exception as e:
        # Is this retryable?  Should we alert?  Is it our fault?
        # We have to parse the message string to find out.  Fragile.

SpineError solves this with a *categorized* error hierarchy::

    SpineError
    ├── TransientError      → Retry (network blip, lock contention)
    │   ├── NetworkError    → Retry with backoff
    │   └── RateLimitError  → Retry after delay (429 status)
    ├── ValidationError     → Don't retry, fix the input
    ├── ConfigError         → Don't retry, fix the configuration
    └── SourceError         → Don't retry, upstream is broken

Each error carries:
    - **category** (ErrorCategory enum) — machine-readable classification
    - **is_retryable** — should we automatically retry?
    - **cause** — the original exception (chained for debugging)
    - **context** — arbitrary metadata dict


================================================================================
INTEGRATION: ERRORS + RESULT[T] PATTERN
================================================================================

Spine errors integrate with the Result pattern for explicit error handling::

    def fetch_filing(cik: str) -> Result[Filing]:
        try:
            response = requests.get(f"https://efts.sec.gov/{cik}")
            response.raise_for_status()
            return Ok(parse_filing(response.json()))
        except requests.Timeout:
            return Err(NetworkError("EDGAR timeout", retryable=True))
        except requests.HTTPError as e:
            if e.response.status_code == 429:
                return Err(RateLimitError("EDGAR rate limit"))
            return Err(SourceError(f"EDGAR returned {e.response.status_code}"))

    # Caller decides how to handle each case
    match fetch_filing("0001318605"):
        case Ok(filing):
            process(filing)
        case Err(RateLimitError()):
            time.sleep(60)
            retry()
        case Err(NetworkError()):
            retry_with_backoff()
        case Err(error):
            alert_team(error)


================================================================================
RETRY DECISION MATRIX
================================================================================

::

    ┌─────────────────────┬───────────┬────────────┬─────────────────────────┐
    │ Error Type          │ Retryable │ Strategy   │ Example                 │
    ├─────────────────────┼───────────┼────────────┼─────────────────────────┤
    │ NetworkError        │ YES       │ Exp backoff│ Connection timeout      │
    │ RateLimitError      │ YES       │ Fixed wait │ HTTP 429 from API       │
    │ TransientError      │ YES       │ Immediate  │ DB lock contention      │
    │ ValidationError     │ NO        │ Fix input  │ Invalid CIK format      │
    │ ConfigError         │ NO        │ Fix config │ Missing API key         │
    │ SourceError         │ NO        │ Escalate   │ API returns 404         │
    └─────────────────────┴───────────┴────────────┴─────────────────────────┘

    The ``is_retryable()`` helper makes this a one-line check::

        if is_retryable(error):
            retry()
        else:
            dead_letter(error)


================================================================================
BEST PRACTICES
================================================================================

1. **Wrap external exceptions** at the boundary::

       try:
           response = requests.get(url, timeout=30)
       except requests.Timeout as e:
           raise NetworkError("API timeout") from e  # Preserves cause chain

2. **Use Result[T] for expected failures**::

       # Use Result when failure is a normal outcome
       def validate(data) -> Result[CleanData]:
           if not data.get("cik"):
               return Err(ValidationError("Missing CIK"))
           return Ok(CleanData(**data))

3. **Use ``is_retryable()``** instead of isinstance checks::

       # Good — single function for retry decisions
       if is_retryable(error):
           retry()

       # Bad — fragile, misses new error types
       if isinstance(error, (NetworkError, RateLimitError, TransientError)):
           retry()

4. **Add context for debugging**::

       NetworkError("Timeout", context={"url": url, "timeout": 30, "attempt": 3})


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/03_advanced_errors.py

See Also:
    - :mod:`spine.core.errors` — SpineError hierarchy, is_retryable()
    - :mod:`spine.core.result` — Ok, Err, Result[T]
    - ``examples/01_core/01_result_pattern.py`` — Result pattern basics
    - ``examples/01_core/02_error_handling.py`` — Error categorization
"""

import random
from spine.core.errors import (
    ConfigError,
    ErrorCategory,
    NetworkError,
    RateLimitError,
    SourceError,
    TransientError,
    ValidationError,
    is_retryable,
)
from spine.core.result import Err, Ok, Result


# ============================================================================
# Example 1: Network Errors with Retry Semantics
# ============================================================================


def fetch_data_from_api(url: str) -> Result[dict]:
    """Fetch data from API, handling various error scenarios.

    Returns:
        Ok(data) on success
        Err(NetworkError) for connection issues (retryable)
        Err(RateLimitError) for rate limits (retryable with delay)
        Err(SourceError) for 404/permanent failures (not retryable)
    """
    # Simulate different failure scenarios
    scenario = random.choice(["success", "timeout", "rate_limit", "not_found"])

    if scenario == "success":
        return Ok({"records": [1, 2, 3], "count": 3})

    elif scenario == "timeout":
        # Transient network error - retryable
        return Err(
            NetworkError(
                "Connection timeout",
                retryable=True,
                retry_after=30,
            ).with_context(url=url, timeout_seconds=30)
        )

    elif scenario == "rate_limit":
        # Rate limit - retryable after specific delay
        return Err(
            RateLimitError(
                "API rate limit exceeded",
                retryable=True,
                retry_after=60,
            ).with_context(url=url, limit="100/hour", remaining=0)
        )

    elif scenario == "not_found":
        # Permanent error - not retryable
        return Err(
            SourceError(
                "Resource not found",
                retryable=False,
            ).with_context(url=url, http_status=404)
        )


def process_with_retry(url: str) -> Result[dict]:
    """Process API call with retry logic based on error semantics.

    Demonstrates:
    - Using Result[T] pattern matching
    - Checking error.retryable for retry decisions
    - Using error.retry_after for backoff delays
    """
    max_retries = 3
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        result = fetch_data_from_api(url)

        match result:
            case Ok(data):
                print(f"  ✓ Success on attempt {attempt}: {data['count']} records")
                return result

            case Err(error):
                print(f"  ✗ Attempt {attempt} failed: {error}")
                print(f"    Category: {error.category.value}")
                print(f"    Retryable: {error.retryable}")

                if not error.retryable:
                    print("    Not retryable - giving up")
                    return result

                if attempt < max_retries:
                    delay = error.retry_after or 10
                    print(f"    Retrying after {delay}s...")
                    # In real code: await asyncio.sleep(delay)

    return result


# ============================================================================
# Example 2: Validation Errors (Never Retryable)
# ============================================================================


def validate_record(record: dict) -> Result[dict]:
    """Validate record schema and constraints.

    Validation errors are never retryable - bad data won't fix itself.
    """
    # Required fields
    if "ticker" not in record:
        return Err(
            ValidationError(
                "Missing required field: ticker",
                retryable=False,
            ).with_context(record=record, missing_field="ticker")
        )

    # Format validation
    ticker = record["ticker"]
    if not isinstance(ticker, str) or len(ticker) < 1:
        return Err(
            ValidationError(
                "Invalid ticker format",
                retryable=False,
            ).with_context(record=record, ticker=ticker, expected="non-empty string")
        )

    # Business rule validation
    if "price" in record and record["price"] < 0:
        return Err(
            ValidationError(
                "Price cannot be negative",
                retryable=False,
            ).with_context(record=record, price=record["price"])
        )

    return Ok(record)


# ============================================================================
# Example 3: Configuration Errors (Never Retryable)
# ============================================================================


def load_config(env: str) -> Result[dict]:
    """Load configuration for environment.

    Config errors are never retryable - missing config won't appear.
    """
    configs = {
        "dev": {"api_url": "http://localhost:8000", "timeout": 30},
        "prod": {"api_url": "https://api.example.com", "timeout": 60},
    }

    if env not in configs:
        return Err(
            ConfigError(
                f"Unknown environment: {env}",
                retryable=False,
            ).with_context(environment=env, available=list(configs.keys()))
        )

    return Ok(configs[env])


# ============================================================================
# Example 4: Error Chaining (Preserving Root Cause)
# ============================================================================


def process_pipeline(record: dict, config: dict) -> Result[dict]:
    """Multi-step pipeline with error chaining.

    Demonstrates:
    - Using Result[T].flat_map() for chaining operations
    - Preserving root cause with error chaining
    """

    def enrich_with_api(validated_record):
        # Simulate API call
        api_result = fetch_data_from_api(config["api_url"])

        match api_result:
            case Ok(api_data):
                return Ok({**validated_record, "enrichment": api_data})

            case Err(error):
                # Chain the error to add context
                return Err(
                    TransientError(
                        "Pipeline enrichment failed",
                        retryable=error.retryable,
                        retry_after=error.retry_after,
                        cause=error,  # Preserve root cause
                    ).with_context(
                        step="enrichment", ticker=validated_record.get("ticker")
                    )
                )

    # Chain operations: validate -> enrich
    return validate_record(record).flat_map(enrich_with_api)


# ============================================================================
# Example 5: Error Categorization for Alerting
# ============================================================================


def route_error_to_team(error):
    """Route errors to appropriate team based on category.

    Demonstrates using ErrorCategory for operational routing.
    """
    if error.category in (ErrorCategory.NETWORK, ErrorCategory.DATABASE):
        return "ops-team"
    elif error.category in (ErrorCategory.VALIDATION, ErrorCategory.PIPELINE):
        return "app-team"
    elif error.category == ErrorCategory.CONFIG:
        return "platform-team"
    else:
        return "on-call"


# ============================================================================
# Main Demo
# ============================================================================


def main():
    print("=" * 70)
    print("Error Handling with SpineError and Result[T]")
    print("=" * 70)

    # Example 1: Network errors with retry
    print("\n1. Network Errors with Retry Logic")
    print("-" * 70)
    print("  Processing API call (may fail and retry)...")
    process_with_retry("https://api.example.com/data")

    # Example 2: Validation errors (never retry)
    print("\n2. Validation Errors (Never Retryable)")
    print("-" * 70)

    test_records = [
        {"ticker": "AAPL", "price": 150.0},
        {"price": 100.0},  # Missing ticker
        {"ticker": "MSFT", "price": -50.0},  # Invalid price
    ]

    for record in test_records:
        result = validate_record(record)
        match result:
            case Ok(_):
                print(f"  ✓ Valid: {record}")
            case Err(error):
                print(f"  ✗ Invalid: {error}")
                print(f"    Category: {error.category.value}")
                print(f"    Retryable: {error.retryable}")

    # Example 3: Config errors
    print("\n3. Configuration Errors")
    print("-" * 70)

    for env in ["dev", "staging", "prod"]:
        result = load_config(env)
        match result:
            case Ok(config):
                print(f"  ✓ Loaded {env}: {config['api_url']}")
            case Err(error):
                print(f"  ✗ Failed to load {env}: {error}")
                print(f"    Retryable: {error.retryable}")

    # Example 4: Error chaining
    print("\n4. Error Chaining in Pipelines")
    print("-" * 70)

    record = {"ticker": "GOOG", "price": 2800.0}
    config_result = load_config("dev")

    if isinstance(config_result, Ok):
        pipeline_result = process_pipeline(record, config_result.value)

        match pipeline_result:
            case Ok(enriched):
                print(f"  ✓ Pipeline success: {enriched['ticker']}")
            case Err(error):
                print(f"  ✗ Pipeline failed: {error}")
                if error.cause:
                    print(f"    Root cause: {error.cause}")

    # Example 5: Error routing for alerting
    print("\n5. Error Categorization for Alerting")
    print("-" * 70)

    sample_errors = [
        NetworkError("Connection failed"),
        ValidationError("Bad schema"),
        ConfigError("Missing API key"),
        TransientError("Service unavailable"),
    ]

    for error in sample_errors:
        team = route_error_to_team(error)
        retryable = "retryable" if is_retryable(error) else "non-retryable"
        print(f"  {error.category.value:12} -> {team:15} ({retryable})")

    print("\n" + "=" * 70)
    print("Key Takeaways:")
    print("  - Use SpineError hierarchy instead of generic exceptions")
    print("  - Return Err(SpineError) in Result[T] for explicit handling")
    print("  - Error.retryable guides retry decisions")
    print("  - ErrorCategory enables routing to appropriate teams")
    print("  - Error chaining preserves root cause for debugging")
    print("=" * 70)


if __name__ == "__main__":
    main()
