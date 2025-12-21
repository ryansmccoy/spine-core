#!/usr/bin/env python3
"""Error Handling — Structured Error Types with Automatic Retry Decisions.

================================================================================
WHY CATEGORIZED ERRORS?
================================================================================

Not all errors are equal. Consider a data operation that fails:

    TransientError("Network timeout")      → Retry in 30 seconds
    ValidationError("Invalid date format") → Don't retry, fix the data
    ConfigError("Missing API key")         → Don't retry, fix config
    SourceError("API returned 404")        → Retry with backoff

Without error categorization, your retry logic becomes a mess::

    # BAD: String matching on error messages
    try:
        fetch_data()
    except Exception as e:
        if "timeout" in str(e).lower():  # Fragile!
            retry()
        elif "rate limit" in str(e):     # What if wording changes?
            wait_and_retry()
        else:
            raise                          # Hope we didn't miss anything

With spine-core's categorized errors::

    # GOOD: Type-based retry decisions
    try:
        fetch_data()
    except Exception as e:
        if is_retryable(e):
            schedule_retry()
        else:
            send_to_dead_letter()


================================================================================
ERROR CATEGORY HIERARCHY
================================================================================

::

    SpineError (base)
    │
    ├── TransientError        [TRANSIENT]   ← Retry with backoff
    │   └── Network issues, rate limits, temporary unavailability
    │
    ├── SourceError           [SOURCE]      ← Retry with longer backoff
    │   └── API errors, 4xx/5xx responses, parse failures from source
    │
    ├── ValidationError       [VALIDATION]  ← NO retry, fix data
    │   └── Schema violations, constraint failures, business rule violations
    │
    ├── ConfigError           [CONFIG]      ← NO retry, fix configuration
    │   └── Missing env vars, invalid settings, auth failures
    │
    └── InternalError         [INTERNAL]    ← NO retry, bug in code
        └── Assertion failures, impossible states


    ┌─────────────────────────────────────────────────────────────────────────┐
    │  RETRY DECISION MATRIX                                                  │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Category    │ Retryable │ Action                                      │
    ├──────────────┼───────────┼─────────────────────────────────────────────┤
    │  TRANSIENT   │    ✓      │ Retry with exponential backoff              │
    │  SOURCE      │    ✓      │ Retry with longer backoff + alert           │
    │  VALIDATION  │    ✗      │ Dead letter queue + fix data                │
    │  CONFIG      │    ✗      │ Halt operation + notify ops                  │
    │  INTERNAL    │    ✗      │ Halt operation + page developer             │
    └──────────────┴───────────┴─────────────────────────────────────────────┘


================================================================================
INTEGRATION WITH RETRY STRATEGIES
================================================================================

spine-core's retry decorators automatically respect error categories::

    from spine.resilience import retry_with_backoff

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    def fetch_filings(cik: str) -> list[Filing]:
        response = httpx.get(f"{EDGAR_URL}/{cik}")
        if response.status_code == 429:
            raise TransientError("Rate limited")  # Will retry
        if response.status_code == 400:
            raise ValidationError("Invalid CIK")  # Won't retry
        return parse_filings(response.json())

    # The decorator checks is_retryable() internally:
    # - TransientError → retry after 1s, 2s, 4s
    # - ValidationError → immediate failure, no retry


================================================================================
DEAD LETTER QUEUE INTEGRATION
================================================================================

Non-retryable errors are routed to the dead letter queue for investigation::

    ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐
    │  Operation   │────►│  Executor   │────►│  is_retryable()?    │
    └─────────────┘     └─────────────┘     └──────────┬──────────┘
                                                       │
                                            ┌──────────┴──────────┐
                                            │                     │
                                         Yes│                     │No
                                            ▼                     ▼
                                    ┌─────────────┐     ┌─────────────────┐
                                    │ Retry Queue │     │ Dead Letter Q   │
                                    │ (backoff)   │     │ (investigation) │
                                    └─────────────┘     └─────────────────┘


================================================================================
CUSTOM ERROR TYPES
================================================================================

Extend the base errors for domain-specific categorization::

    class EdgarRateLimitError(TransientError):
        '''SEC EDGAR rate limit hit (10 requests/second).'''
        def __init__(self, retry_after: int = 60):
            super().__init__(f"EDGAR rate limit, retry in {retry_after}s")
            self.retry_after = retry_after

    class InvalidCIKError(ValidationError):
        '''CIK number format is invalid.'''
        def __init__(self, cik: str):
            super().__init__(f"Invalid CIK format: {cik!r}")
            self.cik = cik

    # is_retryable() still works on subclasses:
    is_retryable(EdgarRateLimitError())  # True (TransientError subclass)
    is_retryable(InvalidCIKError("abc"))  # False (ValidationError subclass)


================================================================================
BEST PRACTICES
================================================================================

1. **Use the most specific error type**::

       # BAD
       raise SpineError("Something went wrong")

       # GOOD
       raise TransientError("EDGAR API timeout after 30s")

2. **Include context in error messages**::

       # BAD
       raise ValidationError("Invalid data")

       # GOOD
       raise ValidationError(
           f"Filing {accession_number} has invalid date: {raw_date!r}"
       )

3. **Use is_retryable() for retry decisions**::

       if is_retryable(exception):
           schedule_retry(job_id, delay=backoff_delay())
       else:
           move_to_dlq(job_id, exception)

4. **Wrap standard exceptions at boundaries**::

       try:
           httpx.get(url)
       except httpx.TimeoutException as e:
           raise TransientError(f"Timeout fetching {url}") from e
       except httpx.HTTPStatusError as e:
           if e.response.status_code >= 500:
               raise SourceError(f"Server error: {e}") from e
           raise ValidationError(f"Client error: {e}") from e


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/02_error_handling.py

See Also:
    - :mod:`spine.core.errors` — Error classes and is_retryable()
    - :mod:`spine.resilience.retry` — Retry decorators
    - :mod:`spine.execution.dlq` — Dead letter queue
"""
from spine.core import (
    SpineError,
    TransientError,
    SourceError,
    ValidationError,
    ConfigError,
    ErrorCategory,
    is_retryable,
)


def main():
    print("=" * 60)
    print("Error Handling Examples")
    print("=" * 60)
    
    # === 1. Error categories ===
    print("\n[1] Error Categories")
    
    for category in ErrorCategory:
        print(f"  {category.name}: {category.value}")
    
    # === 2. Typed exceptions ===
    print("\n[2] Typed Exceptions")
    
    errors = [
        TransientError("Network timeout"),
        SourceError("API returned 404"),
        ValidationError("Invalid date format"),
        ConfigError("Missing API key"),
    ]
    
    for err in errors:
        print(f"  {type(err).__name__}: {err}")
        print(f"    Category: {err.category}")
        print(f"    Retryable: {err.retryable}")
    
    # === 3. is_retryable helper ===
    print("\n[3] is_retryable() helper")
    
    test_errors = [
        TransientError("Timeout"),
        ValidationError("Bad data"),
        ValueError("Generic error"),
        ConnectionError("Network down"),
    ]
    
    for err in test_errors:
        retryable = is_retryable(err)
        print(f"  {type(err).__name__}: retryable={retryable}")
    
    # === 4. Real-world: Retry decision ===
    print("\n[4] Real-world: Retry Decision")
    
    def fetch_data(url: str, attempt: int = 1) -> dict:
        """Simulate fetching data with retry logic."""
        # Simulate different failures
        if attempt == 1:
            raise TransientError("Connection timeout")
        elif attempt == 2:
            raise TransientError("Rate limited")
        else:
            return {"data": "success"}
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            result = fetch_data("https://api.example.com", attempt)
            print(f"  Attempt {attempt}: Success! {result}")
            break
        except Exception as e:
            if is_retryable(e) and attempt < max_retries:
                print(f"  Attempt {attempt}: {e} - will retry")
            else:
                print(f"  Attempt {attempt}: {e} - giving up")
                break
    
    # === 5. Error context ===
    print("\n[5] Error with Context")
    
    try:
        raise SourceError(
            "Failed to fetch FINRA data",
        ).with_context(source_name="finra_otc", url="https://otce.finra.org/...")
    except SourceError as e:
        print(f"  Error: {e}")
        print(f"  Context: {e.context.to_dict()}")
    
    # === 6. Handling unknown errors ===
    print("\n[6] Handling Unknown Errors")
    
    def safe_operation(should_fail: bool) -> str:
        """Demonstrate error handling."""
        try:
            if should_fail:
                raise RuntimeError("Unexpected error")
            return "success"
        except Exception as e:
            if is_retryable(e):
                return f"retry: {e}"
            else:
                return f"fail: {e}"
    
    print(f"  safe_operation(False): {safe_operation(False)}")
    print(f"  safe_operation(True): {safe_operation(True)}")
    
    print("\n" + "=" * 60)
    print("[OK] Error Handling Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
