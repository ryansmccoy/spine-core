#!/usr/bin/env python3
"""Retry Strategies — Configurable retry patterns for transient failures.

WHY RETRIES MATTER
─────────────────
Distributed systems fail transiently — network blips, rate limits, brief
outages.  A well-chosen retry strategy turns a 99 % reliable call into
99.9999 % effective reliability while keeping latency bounded.
Choosing the wrong strategy (or none) means either data loss or
thunder-herd cascades that amplify the original failure.

RETRY STRATEGY COMPARISON
─────────────────────────
    Strategy            Delay Pattern         Best For
    ─────────────────── ───────────────────── ────────────────────────
    NoRetry             n/a                   Idempotency-unsafe ops
    ConstantBackoff     d, d, d, d …          Internal service calls
    LinearBackoff       d, d+i, d+2i …        Gradually increasing load
    ExponentialBackoff  d, d*m, d*m² …        External API rate-limits

BACKOFF TIMING — EXPONENTIAL (base=1s, mult=2×)
────────────────────────────────────────────────
    Attempt  Delay   Cumulative
    ──────── ─────── ──────────
    0        1.0 s   1.0 s
    1        2.0 s   3.0 s
    2        4.0 s   7.0 s
    3        8.0 s   15.0 s
    4        16.0 s  31.0 s

    With jitter each delay is randomised by ±50 % to prevent
    synchronised retry storms across parallel workers.

ARCHITECTURE
────────────
    ┌─────────────┐    fail     ┌──────────────┐
    │  Operation   │──────────▶│ RetryContext  │
    └──────┬──────┘            │  .should_retry│
           │ success           │  .next_delay  │
           ▼                   └──────┬───────┘
    ┌─────────────┐                   │ yes
    │   Result     │◀──── wait(delay) ┘
    └─────────────┘

    @with_retry(strategy)
    async def fetch():
        ...              # decorator wraps the loop above

BEST PRACTICES
──────────────
• Always set max_delay to cap worst-case latency.
• Enable jitter for any strategy used by >1 concurrent caller.
• Use RetryContext for operations that need custom should_retry logic
  (e.g., skip retry on 4xx but retry on 5xx).
• Combine with CircuitBreaker (02_circuit_breaker) for full resilience.

Run: python examples/03_resilience/01_retry_strategies.py

See Also:
    02_circuit_breaker — fail-fast when retries can't help
    06_timeout_enforcement — bound total retry duration
"""
import asyncio
from spine.execution import (
    RetryStrategy,
    ExponentialBackoff,
    LinearBackoff,
    ConstantBackoff,
    NoRetry,
    RetryContext,
    with_retry,
)


async def main():
    print("=" * 60)
    print("Retry Strategy Examples")
    print("=" * 60)
    
    # === 1. Retry strategy types ===
    print("\n[1] Retry Strategy Types")
    
    strategies = [
        ("NoRetry", NoRetry()),
        ("ConstantBackoff(1s, max=3)", ConstantBackoff(delay=1.0, max_retries=3)),
        ("LinearBackoff(1s, max=3)", LinearBackoff(base_delay=1.0, max_retries=3)),
        ("ExponentialBackoff(1s, max=3)", ExponentialBackoff(base_delay=1.0, max_retries=3)),
    ]
    
    for name, strategy in strategies:
        print(f"  {name}")
        print(f"    Max retries: {strategy.max_retries if hasattr(strategy, 'max_retries') else 0}")
    
    # === 2. Exponential backoff delays ===
    print("\n[2] Exponential Backoff Delays")
    
    exp = ExponentialBackoff(base_delay=1.0, max_retries=5, multiplier=2.0, jitter=False)
    print(f"  Strategy: base=1s, multiplier=2x, max_retries=5")
    
    for attempt in range(5):
        delay = exp.next_delay(attempt)
        print(f"    Attempt {attempt}: wait {delay:.1f}s before retry")
    
    # === 3. Linear backoff delays ===
    print("\n[3] Linear Backoff Delays")
    
    linear = LinearBackoff(base_delay=1.0, increment=0.5, max_retries=5)
    print(f"  Strategy: base=1s, increment=0.5s, max_retries=5")
    
    for attempt in range(5):
        delay = linear.next_delay(attempt)
        print(f"    Attempt {attempt}: wait {delay:.1f}s before retry")
    
    # === 4. with_retry decorator ===
    print("\n[4] with_retry Decorator")
    
    call_count = 0
    
    @with_retry(ExponentialBackoff(base_delay=0.1, max_retries=3, jitter=False))
    async def flaky_operation():
        """Simulates an operation that fails twice then succeeds."""
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            print(f"    Attempt {call_count}: failing...")
            raise ConnectionError("Simulated failure")
        print(f"    Attempt {call_count}: success!")
        return "result"
    
    result = await flaky_operation()
    print(f"  Final result: {result}")
    print(f"  Total attempts: {call_count}")
    
    # === 5. RetryContext for manual control ===
    print("\n[5] RetryContext for Manual Control")
    
    strategy = ExponentialBackoff(base_delay=0.1, max_retries=3, jitter=False)
    ctx = RetryContext(strategy=strategy)
    
    attempt = 0
    while True:
        attempt += 1
        try:
            if attempt < 2:
                raise TimeoutError("Simulated timeout")
            print(f"    Attempt {attempt}: success!")
            break
        except Exception as e:
            print(f"    Attempt {attempt}: {e}")
            ctx.record_failure(e)
            if ctx.should_retry():
                delay = ctx.next_delay()
                print(f"    Waiting {delay:.2f}s before retry...")
                await asyncio.sleep(delay)
            else:
                print("    No more retries!")
                break
    
    # === 6. Real-world: API call with retry ===
    print("\n[6] Real-world: API Call with Retry")
    
    api_calls = 0
    
    @with_retry(ExponentialBackoff(base_delay=0.05, max_retries=5, max_delay=1.0, jitter=False))
    async def fetch_market_data(symbol: str) -> dict:
        """Simulates fetching market data with transient failures."""
        nonlocal api_calls
        api_calls += 1
        
        # Simulate rate limiting on first 2 calls
        if api_calls <= 2:
            raise ConnectionError(f"Rate limited (attempt {api_calls})")
        
        return {"symbol": symbol, "price": 150.0, "volume": 1000000}
    
    print("  Fetching AAPL data...")
    data = await fetch_market_data("AAPL")
    print(f"  Result: {data}")
    print(f"  API calls made: {api_calls}")
    
    print("\n" + "=" * 60)
    print("[OK] Retry Strategies Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
