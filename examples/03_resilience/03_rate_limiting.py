#!/usr/bin/env python3
"""Rate Limiting — Control request throughput to external services.

WHY RATE LIMITING MATTERS
─────────────────────────
External APIs (SEC EDGAR, FINRA, market data vendors) enforce strict
request quotas.  Exceeding them results in 429 errors, temporary bans,
or silent data corruption.  Client-side rate limiting ensures your
operation stays within published limits and plays nicely with shared
API keys across teams.

ALGORITHM COMPARISON
────────────────────
    Algorithm        Behaviour              Best For
    ──────────────── ────────────────────── ────────────────────────
    Token Bucket     Smooth avg + burst     APIs with burst allowance
    Sliding Window   Strict count / window  APIs with hard per-second caps
    Keyed Limiter    Per-key token buckets  Multi-tenant / per-user limits
    Composite        AND-combine limiters   Layered limits (5/s AND 200/min)

TOKEN BUCKET — HOW IT WORKS
───────────────────────────
    ┌───────────────────────────────┐
    │  Bucket  (capacity = 10)      │
    │  ● ● ● ● ● ● ● ● ● ●        │ ← tokens
    └──────────────┬────────────────┘
                   │ acquire()
                   ▼
    ┌──────────────────────────────┐
    │  Refill rate: 5 tokens/sec   │
    │  If tokens ≥ 1 → allow       │
    │  Else → deny or block        │
    └──────────────────────────────┘

    Burst: all 10 tokens can be consumed instantly.
    After burst: limited to 5 req/s sustained rate.

SLIDING WINDOW
──────────────
    time ──▶  [──────── window_seconds ────────]
               req req req req req  │ NEW req?
               1   2   3   4   5    │ max=5 → DENY

    No burst — strict count within a rolling window.

COMPOSITE LIMITER EXAMPLE
─────────────────────────
    # FINRA API: 10/sec burst AND 500/minute sustained
    per_sec  = TokenBucketLimiter(rate=10, capacity=10)
    per_min  = SlidingWindowLimiter(max_requests=500, window_seconds=60)
    limiter  = CompositeRateLimiter([per_sec, per_min])
    limiter.acquire()   # both must allow

BEST PRACTICES
──────────────
• Use TokenBucket when the API allows short bursts.
• Use SlidingWindow when the API has hard per-second caps.
• Use KeyedRateLimiter for per-user or per-symbol limits.
• Call get_wait_time() to implement backpressure instead of busy-polling.
• Combine with CircuitBreaker for full downstream protection.

Run: python examples/03_resilience/03_rate_limiting.py

See Also:
    02_circuit_breaker — stop calling when limits are breached
    01_retry_strategies — retry after rate-limit 429 responses
"""
import time
from spine.execution import (
    RateLimiter,
    TokenBucketLimiter,
    SlidingWindowLimiter,
    KeyedRateLimiter,
    CompositeRateLimiter,
)


def main():
    print("=" * 60)
    print("Rate Limiting Examples")
    print("=" * 60)
    
    # === 1. Token bucket limiter ===
    print("\n[1] Token Bucket Limiter")
    print("  Allows burst traffic up to bucket capacity")
    
    limiter = TokenBucketLimiter(
        rate=5.0,      # 5 tokens per second
        capacity=10,   # Max 10 tokens in bucket
    )
    
    print(f"  Rate: {limiter.rate}/sec, Capacity: {limiter.capacity}")
    
    # Burst of requests
    print("  Burst test (10 rapid requests):")
    for i in range(10):
        allowed = limiter.acquire()
        status = "✓" if allowed else "✗"
        print(f"    Request {i+1}: {status}")
    
    # === 2. Sliding window limiter ===
    print("\n[2] Sliding Window Limiter")
    print("  Strict limit over rolling time window")
    
    limiter = SlidingWindowLimiter(
        max_requests=5,
        window_seconds=1.0,
    )
    
    print(f"  Max: {limiter.max_requests} requests per {limiter.window_seconds}s")
    
    # Try requests
    print("  Request test:")
    for i in range(7):
        allowed = limiter.acquire()
        status = "✓ allowed" if allowed else "✗ limited"
        print(f"    Request {i+1}: {status}")
    
    # === 3. Get wait time ===
    print("\n[3] Get Wait Time")
    
    limiter = TokenBucketLimiter(rate=10.0, capacity=2)
    
    # Exhaust tokens
    limiter.acquire()
    limiter.acquire()
    
    wait_time = limiter.get_wait_time()
    print(f"  Tokens exhausted, wait time: {wait_time:.3f}s")
    print(f"  Available tokens: {limiter.available_tokens:.2f}")
    
    # Wait and try again
    time.sleep(wait_time + 0.01)
    allowed = limiter.acquire()
    print(f"  After waiting: {'✓ acquired' if allowed else '✗ denied'}")
    
    # === 4. Keyed rate limiter ===
    print("\n[4] Keyed Rate Limiter (per-key limits)")
    
    limiter = KeyedRateLimiter(
        rate=3.0,
        capacity=3,
    )
    
    print("  Separate limits per key:")
    
    # User A gets 3 requests
    for i in range(4):
        allowed = limiter.acquire("user_a")
        status = "✓" if allowed else "✗"
        print(f"    user_a request {i+1}: {status}")
    
    # User B also gets 3 requests (independent)
    for i in range(4):
        allowed = limiter.acquire("user_b")
        status = "✓" if allowed else "✗"
        print(f"    user_b request {i+1}: {status}")
    
    # === 5. Composite rate limiter ===
    print("\n[5] Composite Rate Limiter")
    print("  Multiple limiters combined (all must allow)")
    
    # Per-second and per-minute limits
    per_second = TokenBucketLimiter(rate=5.0, capacity=5)
    per_minute = SlidingWindowLimiter(max_requests=20, window_seconds=60.0)
    
    composite = CompositeRateLimiter([per_second, per_minute])
    
    print("  Combined: 5/sec AND 20/min")
    
    for i in range(7):
        allowed = composite.acquire()
        status = "✓" if allowed else "✗"
        print(f"    Request {i+1}: {status}")
    
    # === 6. Check wait time ===
    print("\n[6] Check Wait Time")
    
    limiter = TokenBucketLimiter(rate=2.0, capacity=2)
    
    # Exhaust bucket
    limiter.acquire()
    limiter.acquire()
    
    wait_time = limiter.get_wait_time()
    print(f"  Tokens exhausted, wait time: {wait_time:.2f}s")
    print(f"  Available tokens: {limiter.available_tokens:.2f}")
    
    # === 7. Real-world: API rate limiting ===
    print("\n[7] Real-world: API Rate Limiting")
    
    # FINRA API limits: 10 requests/second
    api_limiter = TokenBucketLimiter(rate=10.0, capacity=10)
    
    def fetch_otc_data(symbol: str) -> dict:
        """Fetch OTC data with rate limiting."""
        api_limiter.acquire(block=True)
        # Simulate API call
        return {"symbol": symbol, "volume": 1000000}
    
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    
    print(f"  Fetching {len(symbols)} symbols with rate limit...")
    start = time.time()
    
    for symbol in symbols:
        data = fetch_otc_data(symbol)
        print(f"    {symbol}: {data['volume']:,} volume")
    
    elapsed = time.time() - start
    print(f"  Completed in {elapsed:.3f}s")
    
    print("\n" + "=" * 60)
    print("[OK] Rate Limiting Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
