"""
Hashing — Deterministic Record Hashing for Deduplication.

================================================================================
WHY DETERMINISTIC HASHING?
================================================================================

Data pipelines need to answer:
- "Have I seen this record before?"
- "Did this record's content change?"
- "Is this a duplicate from another source?"

**Deterministic hashing** creates fingerprints of records that are:
- **Stable**: Same input always produces same hash
- **Unique**: Different inputs produce different hashes
- **Fast**: Computed in microseconds
- **Compact**: Fixed-size output regardless of input size

Without deterministic hashing::

    # Using Python's hash() - WRONG!
    hash(("AAPL", "2024-01-19"))  # Different value every Python session!

    # Using random UUIDs - WRONG!
    uuid.uuid4()  # Different every time, can't detect duplicates

With deterministic hashing::

    compute_hash("AAPL", "2024-01-19")  # Always "abc123..." 
    # Same across runs, machines, and time


================================================================================
HASHING STRATEGIES
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  NATURAL KEY HASH (Business Key)                                        │
    │  ────────────────────────────────                                        │
    │  Hash only the fields that uniquely identify a record.                  │
    │                                                                         │
    │  natural_key_hash = compute_hash(symbol, date)                          │
    │                                                                         │
    │  Use for: L2 idempotency (skip if key exists)                          │
    │  Example: "Is there already a price for AAPL on 2024-01-19?"            │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  CONTENT HASH (Change Detection)                                        │
    │  ───────────────────────────────                                         │
    │  Hash business key + data fields.                                       │
    │                                                                         │
    │  content_hash = compute_hash(symbol, date, price, volume)               │
    │                                                                         │
    │  Use for: Change detection (did this record's content change?)          │
    │  Example: "Is the price different from last time we saw it?"            │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  COMPARISON TABLE                                                       │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Record A      symbol=AAPL  date=2024-01-19  price=150                  │
    │  Record B      symbol=AAPL  date=2024-01-19  price=151                  │
    │                                                                         │
    │  natural_key_hash(A) == natural_key_hash(B)  → True (same key)         │
    │  content_hash(A) == content_hash(B)          → False (price changed)   │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
IMPLEMENTATION DETAILS
================================================================================

spine-core uses **SHA-256** (truncated) for hashing::

    def compute_hash(*values, length: int = 16) -> str:
        # Concatenate values with separator
        data = "|".join(str(v) for v in values)
        # SHA-256 for cryptographic stability
        digest = hashlib.sha256(data.encode()).hexdigest()
        # Truncate for storage efficiency (16 chars = 64 bits = 10^19 space)
        return digest[:length]

Why SHA-256?:
    - Deterministic across Python versions and machines
    - Cryptographically uniform distribution
    - No seed dependency (unlike Python's hash())

Why truncate?:
    - Full SHA-256 is 64 hex chars (256 bits)
    - 16 chars (64 bits) has collision probability ~10^-19 for 10^9 records
    - 8 chars (32 bits) may have collisions with >100M records


================================================================================
DATABASE PATTERNS
================================================================================

**Deduplication table with hash**::

    CREATE TABLE bronze_prices (
        record_hash  VARCHAR(16) PRIMARY KEY,  -- Truncated SHA-256
        symbol       VARCHAR(10) NOT NULL,
        date         DATE NOT NULL,
        price        DECIMAL(12,4) NOT NULL,
        ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Index on hash enables fast lookups
    -- Primary key constraint prevents duplicates

**Change detection with two hashes**::

    CREATE TABLE silver_prices (
        natural_key_hash  VARCHAR(16) PRIMARY KEY,  -- symbol + date
        content_hash      VARCHAR(16) NOT NULL,     -- symbol + date + price
        symbol            VARCHAR(10) NOT NULL,
        date              DATE NOT NULL,
        price             DECIMAL(12,4) NOT NULL,
        updated_at        TIMESTAMP
    );

    -- Update only if content changed
    INSERT INTO silver_prices (...) VALUES (...)
    ON CONFLICT (natural_key_hash) DO UPDATE
    SET price = EXCLUDED.price, updated_at = NOW()
    WHERE silver_prices.content_hash != EXCLUDED.content_hash;


================================================================================
BEST PRACTICES
================================================================================

1. **Order matters** - hash(A, B) != hash(B, A)::

       # Define a canonical field order and stick to it
       record_hash = compute_hash(
           row["symbol"],
           row["date"],
           row["mpid"],
       )  # Always this order!

2. **Normalize values before hashing**::

       # BAD - whitespace differences create different hashes
       compute_hash(" AAPL")  # != compute_hash("AAPL")

       # GOOD - normalize first
       compute_hash(symbol.strip().upper(), date.isoformat())

3. **Use appropriate hash length**::

       # Small dataset (<1M records): 8 chars OK
       compute_hash(..., length=8)

       # Large dataset (>100M records): 16+ chars
       compute_hash(..., length=16)

4. **Document which fields are hashed**::

       # In table DDL or data dictionary:
       # record_hash: SHA-256(symbol, date, source) truncated to 16 chars

5. **Include hash in every INSERT**::

       cursor.execute(
           "INSERT INTO bronze (record_hash, ...) VALUES (?, ...)",
           [compute_hash(symbol, date), ...]
       )


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/12_content_hashing.py

See Also:
    - :mod:`spine.core.hashing` — compute_hash, compute_record_hash
    - :mod:`spine.core.idempotency` — IdempotencyHelper uses hashes
    - :mod:`spine.core.versioning` — Content versioning with hashes
"""

from spine.core import compute_hash, compute_record_hash


def main():
    """Demonstrate hashing utilities for deduplication."""
    print("=" * 60)
    print("Hashing - Deterministic Record Hashing")
    print("=" * 60)
    
    # Basic hashing
    print("\n1. Basic hash computation...")
    
    hash1 = compute_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
    print(f"   Hash of (2025-12-26, NMS_TIER_1, AAPL, NITE):")
    print(f"   {hash1}")
    
    # Same inputs = same hash (deterministic)
    hash2 = compute_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
    print(f"\n   Same inputs again: {hash2}")
    print(f"   Hashes match: {hash1 == hash2}")
    
    # Different inputs = different hash
    hash3 = compute_hash("2025-12-26", "NMS_TIER_1", "MSFT", "NITE")
    print(f"\n   Different symbol (MSFT): {hash3}")
    print(f"   Hashes match: {hash1 == hash3}")
    
    # Order matters
    print("\n2. Order dependency...")
    
    hash_ab = compute_hash("A", "B")
    hash_ba = compute_hash("B", "A")
    print(f"   Hash of ('A', 'B'): {hash_ab}")
    print(f"   Hash of ('B', 'A'): {hash_ba}")
    print(f"   Order matters: {hash_ab != hash_ba}")
    
    # Custom hash length
    print("\n3. Custom hash length...")
    
    hash_short = compute_hash("test", length=8)
    hash_medium = compute_hash("test", length=16)
    hash_long = compute_hash("test", length=64)
    
    print(f"   8 chars:  {hash_short}")
    print(f"   16 chars: {hash_medium}")
    print(f"   64 chars: {hash_long}")
    
    # Content-based deduplication pattern
    print("\n4. Content-based deduplication pattern...")
    
    # Natural key hash (for L2 idempotency)
    def natural_key_hash(week: str, tier: str, symbol: str, mpid: str) -> str:
        """Hash just the business key fields."""
        return compute_hash(week, tier, symbol, mpid)
    
    # Content hash (for change detection)
    def content_hash(week: str, tier: str, symbol: str, mpid: str, shares: int) -> str:
        """Hash business key + data fields."""
        return compute_hash(week, tier, symbol, mpid, shares)
    
    # Same record, same data
    record1 = ("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 10000)
    nk1 = natural_key_hash(*record1[:4])
    ck1 = content_hash(*record1)
    
    # Same record, different data (volume changed)
    record2 = ("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 15000)
    nk2 = natural_key_hash(*record2[:4])
    ck2 = content_hash(*record2)
    
    print(f"   Record 1: {record1}")
    print(f"   Record 2: {record2}")
    print(f"\n   Natural key hashes match: {nk1 == nk2} (same business key)")
    print(f"   Content hashes match: {ck1 == ck2} (data changed!)")
    
    # Use case: detect updates
    if nk1 == nk2 and ck1 != ck2:
        print("\n   → This is an UPDATE (same key, different content)")
    
    # Record hash for OTC data
    print("\n5. OTC-specific record hash...")
    
    # compute_record_hash is specialized for OTC transparency data
    otc_hash = compute_record_hash(
        week_ending="2025-12-26",
        tier="NMS_TIER_1",
        symbol="AAPL",
        mpid="NITE",
    )
    print(f"   OTC record hash: {otc_hash}")
    
    # Collision resistance demo
    print("\n6. Collision resistance...")
    
    # Generate many hashes, check for collisions
    hashes = set()
    for i in range(1000):
        h = compute_hash(f"record_{i}", "2025-12-26")
        hashes.add(h)
    
    print(f"   Generated 1000 hashes")
    print(f"   Unique hashes: {len(hashes)}")
    print(f"   Collisions: {1000 - len(hashes)}")
    
    print("\n" + "=" * 60)
    print("Hashing demo complete!")


if __name__ == "__main__":
    main()
