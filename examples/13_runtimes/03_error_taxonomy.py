#!/usr/bin/env python3
"""Error taxonomy — JobError, ErrorCategory, and retryable semantics.

================================================================================
WHY THIS DEEP DIVE?
================================================================================

Every runtime adapter error is wrapped in a ``JobError`` with a structured
``ErrorCategory`` enum.  This enables:

- Automatic retry decisions (``retryable`` flag)
- Provider-specific diagnostics (``provider_code``, ``exit_code``)
- Centralized error handling without string matching
- Runtime attribution (which adapter failed)

::

    ErrorCategory (10 values)
    ─────────────────────────
    AUTH                 Authentication/authorization failure
    QUOTA                Resource quota exceeded
    NOT_FOUND            Adapter/command/resource not found
    RUNTIME_UNAVAILABLE  Runtime daemon unreachable
    IMAGE_PULL           Container image pull failure
    OOM                  Out-of-memory kill
    TIMEOUT              Job exceeded deadline
    USER_CODE            User code raised an error
    VALIDATION           Spec validation failure
    UNKNOWN              Unclassified error

    JobError (frozen dataclass + Exception)
    ─────────────────────────────────────────
    category        ErrorCategory   Error classification
    message         str             Human-readable description
    retryable       bool            Whether retry makes sense
    provider_code   str|None        Provider-specific error code
    exit_code       int|None        Process exit code
    runtime         str|None        Which runtime adapter raised it


================================================================================
RUN IT
================================================================================

::

    python examples/13_runtimes/03_error_taxonomy.py

"""

from spine.execution.runtimes._types import ErrorCategory, JobError


def demo_error_categories():
    """All 10 error categories with retryability semantics."""
    print("=" * 70)
    print("SECTION 1 — Error Categories")
    print("=" * 70)

    # Category → default retryability mapping
    categories = [
        (ErrorCategory.AUTH, False, "Bad credentials, expired token"),
        (ErrorCategory.QUOTA, True, "Rate limit, quota exceeded — retry after cooldown"),
        (ErrorCategory.NOT_FOUND, False, "Command/adapter/resource doesn't exist"),
        (ErrorCategory.RUNTIME_UNAVAILABLE, True, "Docker daemon down — might come back"),
        (ErrorCategory.IMAGE_PULL, True, "Registry timeout — might resolve"),
        (ErrorCategory.OOM, False, "Need more memory — spec change required"),
        (ErrorCategory.TIMEOUT, False, "Job exceeded deadline — increase timeout"),
        (ErrorCategory.USER_CODE, False, "Bug in user code — fix required"),
        (ErrorCategory.VALIDATION, False, "Spec doesn't match capabilities"),
        (ErrorCategory.UNKNOWN, True, "Unknown — retry on general principle"),
    ]

    for cat, retryable, description in categories:
        print(f"  {cat.value:22s}  retryable={retryable!s:5s}  {description}")

    print(f"\n  Total categories: {len(ErrorCategory)}")
    print("  ✓ All categories documented\n")


def demo_job_error_construction():
    """Construct JobError with all fields."""
    print("=" * 70)
    print("SECTION 2 — JobError Construction")
    print("=" * 70)

    # Minimal
    err1 = JobError(
        category=ErrorCategory.TIMEOUT,
        message="Job exceeded 300s deadline",
        retryable=False,
    )
    print(f"  Minimal:      {err1}")
    print(f"  category:     {err1.category}")
    print(f"  message:      {err1.message}")
    print(f"  retryable:    {err1.retryable}")

    # Full
    err2 = JobError(
        category=ErrorCategory.OOM,
        message="Container killed by OOM (exit 137)",
        retryable=False,
        provider_code="ContainerOOMKilled",
        exit_code=137,
        runtime="docker",
    )
    print(f"\n  Full:         {err2}")
    print(f"  provider_code: {err2.provider_code}")
    print(f"  exit_code:     {err2.exit_code}")
    print(f"  runtime:       {err2.runtime}")
    print("  ✓ JobError constructed\n")


def demo_job_error_as_exception():
    """JobError is a proper Exception — can be raised and caught."""
    print("=" * 70)
    print("SECTION 3 — JobError as Exception")
    print("=" * 70)

    def simulate_submit():
        raise JobError(
            category=ErrorCategory.RUNTIME_UNAVAILABLE,
            message="Docker daemon not running",
            retryable=True,
            runtime="docker",
        )

    try:
        simulate_submit()
    except JobError as err:
        print(f"  Caught:       {type(err).__name__}")
        print(f"  Category:     {err.category}")
        print(f"  Message:      {err.message}")
        print(f"  Retryable:    {err.retryable}")
        print(f"  Is Exception: {isinstance(err, Exception)}")
        assert isinstance(err, Exception)
        print("  ✓ JobError caught as exception\n")


def demo_retry_decision():
    """Use retryable flag for automatic retry logic."""
    print("=" * 70)
    print("SECTION 4 — Retry Decision Logic")
    print("=" * 70)

    errors = [
        JobError(ErrorCategory.QUOTA, "Rate limited", retryable=True),
        JobError(ErrorCategory.AUTH, "Token expired", retryable=False),
        JobError(ErrorCategory.IMAGE_PULL, "Registry timeout", retryable=True),
        JobError(ErrorCategory.USER_CODE, "ImportError", retryable=False),
        JobError(ErrorCategory.UNKNOWN, "Mystery", retryable=True),
    ]

    for err in errors:
        action = "RETRY" if err.retryable else "ABORT"
        print(f"  {err.category.value:22s}  → {action:5s}  ({err.message})")

    retryable_count = sum(1 for e in errors if e.retryable)
    print(f"\n  Retryable: {retryable_count}/{len(errors)}")
    print("  ✓ Retry decisions made\n")


def demo_error_pattern_matching():
    """Pattern-match on error categories for handling logic."""
    print("=" * 70)
    print("SECTION 5 — Error Pattern Matching")
    print("=" * 70)

    def handle_error(err: JobError) -> str:
        """Route errors to appropriate handlers."""
        match err.category:
            case ErrorCategory.AUTH:
                return "Refresh credentials and retry"
            case ErrorCategory.QUOTA:
                return f"Wait for quota reset, then retry"
            case ErrorCategory.OOM:
                return f"Increase memory limit from {err.provider_code or 'unknown'}"
            case ErrorCategory.TIMEOUT:
                return "Increase timeout_seconds in spec"
            case ErrorCategory.VALIDATION:
                return "Fix spec to match adapter capabilities"
            case ErrorCategory.NOT_FOUND:
                return "Check that command/runtime exists"
            case _:
                return f"Unexpected: {err.category.value}"

    test_errors = [
        JobError(ErrorCategory.AUTH, "Token expired", False),
        JobError(ErrorCategory.OOM, "Killed", False, provider_code="2048MB"),
        JobError(ErrorCategory.TIMEOUT, "Exceeded 300s", False),
        JobError(ErrorCategory.VALIDATION, "GPU not supported", False),
    ]

    for err in test_errors:
        action = handle_error(err)
        print(f"  {err.category.value:15s} → {action}")

    print("  ✓ Pattern matching works\n")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_error_categories()
    demo_job_error_construction()
    demo_job_error_as_exception()
    demo_retry_decision()
    demo_error_pattern_matching()
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
