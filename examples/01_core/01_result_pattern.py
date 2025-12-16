#!/usr/bin/env python3
"""Result Pattern — Explicit Success/Failure Handling Without Exceptions.

================================================================================
WHAT IS THE RESULT PATTERN?
================================================================================

The **Result pattern** (also called Either monad) replaces exception-based
error handling with explicit return types. Instead of throwing and catching
exceptions, functions return either:

    Ok(value)   — Success with a value
    Err(error)  — Failure with an error

This pattern originated in functional languages (Rust, Haskell, Scala) and
solves fundamental problems with exception-based error handling.


================================================================================
WHY USE RESULT INSTEAD OF EXCEPTIONS?
================================================================================

PROBLEM 1: Hidden Control Flow
──────────────────────────────
Exceptions create invisible "goto" statements::

    def process_order(order):           # Can this throw? Who knows!
        validate(order)                  # ← Might throw ValidationError
        customer = get_customer(order)   # ← Might throw NotFoundError
        charge(customer, order.total)    # ← Might throw PaymentError
        return ship(order)               # ← Might throw ShippingError

With Result, all failure paths are visible in the return type::

    def process_order(order) -> Result[ShipmentId]:
        return (validate(order)
                .and_then(lambda _: get_customer(order))
                .and_then(lambda c: charge(c, order.total))
                .and_then(lambda _: ship(order)))


PROBLEM 2: Swallowed Exceptions
───────────────────────────────
Exceptions are easy to accidentally ignore::

    try:
        risky_operation()
    except Exception:  # Catches EVERYTHING including bugs
        pass           # Silently swallowed

With Result, you MUST handle the error case::

    result = risky_operation()
    if result.is_err():
        # Explicitly decide what to do
        log_error(result.error)


PROBLEM 3: Composition Difficulty
─────────────────────────────────
Chaining fallible operations with try/except is verbose::

    try:
        a = step_one()
        try:
            b = step_two(a)
            try:
                c = step_three(b)
            except StepThreeError:
                ...
        except StepTwoError:
            ...
    except StepOneError:
        ...

With Result.map() and Result.and_then()::

    result = (step_one()
              .and_then(step_two)
              .and_then(step_three))
    # All errors bubble up automatically


================================================================================
RESULT TYPE ARCHITECTURE
================================================================================

::

    Result[T]
    ├── Ok[T]
    │   ├── value: T           # The success value
    │   ├── is_ok() → True
    │   ├── is_err() → False
    │   ├── unwrap() → T
    │   ├── unwrap_or(default) → T
    │   ├── map(fn) → Ok[U]    # Transform value
    │   └── and_then(fn) → Result[U]
    │
    └── Err[E]
        ├── error: E           # The error value
        ├── is_ok() → False
        ├── is_err() → True
        ├── unwrap() → raises!
        ├── unwrap_or(default) → default
        ├── map(fn) → Err[E]   # No-op, passes error through
        └── and_then(fn) → Err[E]


    Railway-Oriented Flow:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                         │
    │   Success Track:  Ok(a) ──map(f)──► Ok(f(a)) ──map(g)──► Ok(g(f(a)))   │
    │                     ↓                                                   │
    │   Failure Track:  Err(e) ─────────────────────────────► Err(e)         │
    │                                                                         │
    │   Once on the failure track, all subsequent maps are skipped.          │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
WHEN TO USE RESULT VS EXCEPTIONS
================================================================================

+----------------------+------------------+-----------------------------------+
| Scenario             | Use Result       | Use Exceptions                    |
+======================+==================+===================================+
| Expected failures    | ✓ Validation,    | ✗                                 |
| (business logic)     |   not found,     |                                   |
|                      |   parse errors   |                                   |
+----------------------+------------------+-----------------------------------+
| Unexpected failures  | ✗                | ✓ Bugs, programming errors        |
| (bugs)               |                  |                                   |
+----------------------+------------------+-----------------------------------+
| Recoverable errors   | ✓                | ✗                                 |
+----------------------+------------------+-----------------------------------+
| Boundary code        | ✗                | ✓ try_result() at boundary        |
| (calling libraries)  |                  |                                   |
+----------------------+------------------+-----------------------------------+


================================================================================
BEST PRACTICES
================================================================================

1. **Use try_result() at library boundaries**::

       # Wrap exception-throwing library code
       result = try_result(lambda: requests.get(url))

2. **Pattern match for exhaustive handling**::

       match fetch_user(user_id):
           case Ok(user):
               return render_profile(user)
           case Err(NotFoundError()):
               return render_404()
           case Err(error):
               return render_500(error)

3. **Use map() for transformations that can't fail**::

       Ok(42).map(lambda x: x * 2)  # Ok(84)

4. **Use and_then() for transformations that might fail**::

       Ok(42).and_then(lambda x: validate(x))  # Result from validate()

5. **Prefer unwrap_or() over unwrap()**::

       # Safe: provides default
       value = result.unwrap_or(default_value)

       # Dangerous: raises on Err
       value = result.unwrap()  # Only use when you KNOW it's Ok


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/01_result_pattern.py

See Also:
    - :mod:`spine.core.result` — Result, Ok, Err, try_result
    - :mod:`spine.core.errors` — Typed exceptions for Err values
    - :mod:`spine.execution.runs` — RunRecord uses Result internally
"""
from spine.core import Result, Ok, Err, try_result


def main():
    print("=" * 60)
    print("Result Pattern Examples")
    print("=" * 60)
    
    # === 1. Basic Ok and Err ===
    print("\n[1] Basic Ok and Err")
    
    success: Result[int] = Ok(42)
    failure: Result[int] = Err(ValueError("Something went wrong"))
    
    print(f"  Success: {success}")
    print(f"  Success.is_ok(): {success.is_ok()}")
    print(f"  Success.value: {success.value}")
    
    print(f"  Failure: {failure}")
    print(f"  Failure.is_err(): {failure.is_err()}")
    print(f"  Failure.error: {failure.error}")
    
    # === 2. Safe value access ===
    print("\n[2] Safe Value Access")
    
    # unwrap_or provides default on error
    print(f"  failure.unwrap_or(0): {failure.unwrap_or(0)}")
    print(f"  success.unwrap(): {success.unwrap()}")
    
    # === 3. Chaining with map ===
    print("\n[3] Chaining with map")
    
    result = Ok(10)
    doubled = result.map(lambda x: x * 2)
    print(f"  Ok(10).map(x * 2): {doubled}")
    
    err_result = Err(ValueError("error"))
    err_doubled = err_result.map(lambda x: x * 2)
    print(f"  Err('error').map(x * 2): {err_doubled}")
    
    # === 4. try_result function ===
    print("\n[4] try_result Function")
    
    def divide(a: int, b: int) -> float:
        """Regular function that might raise."""
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return a / b
    
    # Wrap exception-throwing code
    result1 = try_result(lambda: divide(10, 2))
    result2 = try_result(lambda: divide(10, 0))
    
    print(f"  try_result(divide(10, 2)): {result1}")
    print(f"  try_result(divide(10, 0)): {result2}")
    
    # === 5. Pattern matching ===
    print("\n[5] Pattern Matching")
    
    def process(result: Result[int]) -> str:
        """Process a result with pattern matching."""
        match result:
            case Ok(value):
                return f"Got value: {value}"
            case Err(error):
                return f"Got error: {error}"
    
    print(f"  process(Ok(42)): {process(Ok(42))}")
    print(f"  process(Err(...)): {process(Err(ValueError('bad')))}")
    
    # === 6. Real-world: Data processing ===
    print("\n[6] Real-world: Data Processing")
    
    def parse_price(s: str) -> Result[float]:
        """Parse a price string to float."""
        try:
            return Ok(float(s.replace("$", "").replace(",", "")))
        except ValueError as e:
            return Err(e)
    
    prices = ["$150.50", "invalid", "$1,234.00", "N/A"]
    
    for price in prices:
        result = parse_price(price)
        if result.is_ok():
            print(f"  '{price}' -> {result.value:.2f}")
        else:
            print(f"  '{price}' -> ERROR: {result.error}")
    
    # === 7. Collecting results ===
    print("\n[7] Collecting Results")
    
    results = [parse_price(p) for p in prices]
    
    successes = [r.value for r in results if r.is_ok()]
    failures = [r.error for r in results if r.is_err()]
    
    print(f"  Successes: {successes}")
    print(f"  Failures: {len(failures)}")
    
    print("\n" + "=" * 60)
    print("[OK] Result Pattern Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
