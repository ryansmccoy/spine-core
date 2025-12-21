#!/usr/bin/env python3
"""Cache Backends — Tiered Caching with Protocol-Based Swappability.

================================================================================
WHY CACHING IN DATA operations?
================================================================================

Data operations repeatedly fetch the same data:

    - SEC EDGAR index pages (same index, many filings to parse)
    - Ticker-to-CIK mappings (changes rarely, queried thousands of times)
    - API rate-limited responses (don't waste quota re-fetching)
    - Intermediate computation results (expensive transforms)

Without caching::

    # Each of 10,000 filings looks up the same CIK mapping
    for filing in filings:
        cik = fetch_from_api(filing.ticker)  # 10,000 API calls!
        process(filing, cik)

With caching::

    cache = InMemoryCache(max_size=1000, default_ttl_seconds=3600)
    for filing in filings:
        cik = cache.get(f"cik:{filing.ticker}") or fetch_and_cache(filing.ticker)
        process(filing, cik)  # 50 unique tickers = 50 API calls


================================================================================
ARCHITECTURE: TIERED CACHE STRATEGY
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TIER 1: InMemoryCache (Single Process)                                │
    │  ─────────────────────────────────────                                 │
    │  - LRU eviction with configurable max_size                            │
    │  - TTL-based expiry per key                                           │
    │  - Zero external dependencies                                         │
    │  - ~1μs read latency                                                   │
    │  - Use for: hot lookups, single-worker operations, development         │
    └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ cache miss
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TIER 2: RedisCache (Distributed)                                      │
    │  ─────────────────────────────────                                     │
    │  - Shared across workers/containers                                   │
    │  - TTL via Redis EXPIRE                                               │
    │  - ~100μs read latency (localhost), ~1ms (network)                     │
    │  - Use for: multi-worker, Celery tasks, rate limit sharing            │
    └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ cache miss
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TIER 3: Origin (Database / API / Filesystem)                          │
    │  ────────────────────────────────────────────                          │
    │  - The actual data source                                             │
    │  - Highest latency, rate limits, cost                                 │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
KEY DESIGN: CacheBackend PROTOCOL
================================================================================

All cache implementations share the same interface::

    class CacheBackend(Protocol):
        def get(self, key: str) -> Any | None: ...
        def set(self, key: str, value: Any, ttl_seconds: int | None = None): ...
        def exists(self, key: str) -> bool: ...
        def delete(self, key: str) -> None: ...

This means your operation code is cache-backend agnostic::

    def ingest_filings(cache: CacheBackend):  # Works with any backend
        cik = cache.get("cik:AAPL") or fetch_cik("AAPL")

    # Development: InMemoryCache()
    # Production:  RedisCache("redis://redis:6379/0")
    # Testing:     InMemoryCache() (no external deps)


================================================================================
BEST PRACTICES
================================================================================

1. **Use namespaced keys** to avoid collisions::

       cache.set("cik:AAPL", "0000320193")        # Good
       cache.set("AAPL", "0000320193")              # Bad — collides easily

2. **Set TTLs based on data volatility**::

       cache.set("cik:AAPL", cik, ttl_seconds=86400)     # CIK rarely changes
       cache.set("price:AAPL", price, ttl_seconds=60)     # Price changes fast

3. **Size LRU caches to your working set**::

       # If you process 500 unique tickers, max_size=1000 gives headroom
       cache = InMemoryCache(max_size=1000)

4. **Use protocol type hints** for swappability::

       def my_operation(cache: CacheBackend):  # Not InMemoryCache!
           ...


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/16_cache_backends.py

See Also:
    - :mod:`spine.core.cache` — CacheBackend protocol, InMemoryCache, RedisCache
    - :mod:`spine.core.config` — Tier configuration (minimal/standard/full)
"""


def example_inmemory_cache():
    """Single-process caching with LRU eviction."""
    from spine.core.cache import InMemoryCache

    print("=== InMemoryCache Example ===\n")

    cache = InMemoryCache(max_size=100, default_ttl_seconds=3600)

    # Store API response
    cache.set("api:products:123", {"name": "Widget", "price": 9.99})
    product = cache.get("api:products:123")
    print(f"Cached product: {product}")

    # Check existence
    print(f"Exists: {cache.exists('api:products:123')}")  # → True

    # TTL-based expiry (fast for demo)
    cache.set("session:abc", {"user_id": 42}, ttl_seconds=2)
    print(f"Session exists: {cache.exists('session:abc')}")  # → True
    
    import time
    time.sleep(2.1)
    print(f"Session after 2s: {cache.exists('session:abc')}")  # → False (expired)

    # LRU eviction
    small_cache = InMemoryCache(max_size=3, default_ttl_seconds=None)
    small_cache.set("k1", 1)
    small_cache.set("k2", 2)
    small_cache.set("k3", 3)
    print(f"\nCache size: {small_cache.size()}")  # → 3

    small_cache.set("k4", 4)  # Evicts k1 (LRU)
    print(f"After adding k4: exists(k1)={small_cache.exists('k1')}, size={small_cache.size()}")


def example_redis_cache():
    """Distributed caching with Redis (requires Tier 3 Docker)."""
    from spine.core.cache import RedisCache

    print("\n=== RedisCache Example ===\n")

    try:
        cache = RedisCache("redis://localhost:6379/0", default_ttl_seconds=300)

        # Store feed item
        cache.set("feed:item:999", {
            "title": "Breaking News",
            "published": "2026-02-14T12:00:00Z",
            "content": "..."
        })

        item = cache.get("feed:item:999")
        print(f"Cached feed item: {item}")

        # TTL support
        cache.set("temp:token", "abc123xyz", ttl_seconds=60)
        print(f"Token exists: {cache.exists('temp:token')}")  # → True

        # Cleanup
        cache.delete("feed:item:999")
        cache.delete("temp:token")
        print("\nRedis cache working! ✓")

    except Exception as exc:
        print(f"⚠️  Redis not available: {exc}")
        print("Start Redis with: docker compose --profile full up -d redis")


def example_protocol_swapping():
    """Use CacheBackend protocol for swappable implementations."""
    from spine.core.cache import CacheBackend, InMemoryCache

    print("\n=== Protocol-Based Swapping ===\n")

    def fetch_with_cache(cache: CacheBackend, key: str) -> dict:
        """Generic function that works with any CacheBackend."""
        cached = cache.get(key)
        if cached:
            print(f"Cache HIT for {key}")
            return cached

        print(f"Cache MISS for {key} — fetching...")
        # Simulate expensive operation
        result = {"data": f"computed_{key}", "expensive": True}
        cache.set(key, result, ttl_seconds=3600)
        return result

    # Swap backends transparently
    cache: CacheBackend = InMemoryCache()

    result1 = fetch_with_cache(cache, "api:data:123")  # MISS
    result2 = fetch_with_cache(cache, "api:data:123")  # HIT

    print(f"\nFirst call:  {result1}")
    print(f"Second call: {result2}")


if __name__ == "__main__":
    example_inmemory_cache()
    example_redis_cache()
    example_protocol_swapping()
