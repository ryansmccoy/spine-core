#!/usr/bin/env python3
"""Circuit Breaker — Fail-fast protection for external services.

WHY CIRCUIT BREAKERS MATTER
───────────────────────────
Without a circuit breaker, a failing downstream service causes every
caller to block for the full timeout — consuming threads, exhausting
connection pools, and cascading the failure upstream.  A circuit
breaker detects repeated failures and immediately rejects new calls,
giving the downstream service time to recover while keeping the rest
of the system healthy.

STATE MACHINE
─────────────
    ┌────────┐  failure_threshold   ┌────────┐
    │ CLOSED │─────── exceeded ────▶│  OPEN  │
    │        │◀──── probe succeeds ─│        │
    └───┬────┘                      └───┬────┘
        │                               │
        │  success                      │ recovery_timeout
        ▼                               ▼
    ┌────────┐                      ┌──────────┐
    │ normal │                      │HALF_OPEN │
    │ traffic│                      │ (probe)  │
    └────────┘                      └──────────┘

    CLOSED    → all requests pass; failures counted
    OPEN      → all requests rejected immediately (CircuitOpenError)
    HALF_OPEN → limited probe requests; success closes, failure re-opens

CONFIGURATION PARAMETERS
────────────────────────
    Parameter             Default   Purpose
    ───────────────────── ───────── ────────────────────────────────
    failure_threshold     5         Failures to trip the breaker
    recovery_timeout      30.0 s    Wait before probing
    half_open_max_calls   1         Probes allowed in HALF_OPEN
    success_threshold     2         Successes to close from HALF_OPEN

USAGE PATTERNS
──────────────
    # Option A — manual
    cb = CircuitBreaker(name="api", failure_threshold=3)
    if cb.allow_request():
        try:
            result = call_api()
            cb.record_success()
        except Exception as e:
            cb.record_failure(e)

    # Option B — automatic
    result = cb.call(call_api)          # sync
    result = await cb.call_async(fn)    # async

BEST PRACTICES
──────────────
• Name every breaker ("market_data_api", "db_writer") for dashboards.
• Set failure_threshold ≥ 3 to avoid tripping on single glitches.
• Use CircuitBreakerRegistry to manage breakers across the process.
• Combine with RetryStrategy — retry inside the breaker, not outside.
• Monitor CircuitStats for alerting on frequent trips.

Run: python examples/03_resilience/02_circuit_breaker.py

See Also:
    01_retry_strategies — retry before tripping the breaker
    03_rate_limiting — prevent overloading downstream
"""
import asyncio
from spine.execution import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
    CircuitBreakerRegistry,
    get_circuit_breaker,
)
from spine.execution.circuit_breaker import CircuitOpenError


async def main():
    print("=" * 60)
    print("Circuit Breaker Examples")
    print("=" * 60)
    
    # === 1. Circuit states ===
    print("\n[1] Circuit States")
    
    for state in CircuitState:
        print(f"  {state.name}: {state.value}")
    
    print("\n  State transitions:")
    print("    CLOSED → OPEN: When failure threshold exceeded")
    print("    OPEN → HALF_OPEN: After recovery timeout")
    print("    HALF_OPEN → CLOSED: On successful probe")
    print("    HALF_OPEN → OPEN: On probe failure")
    
    # === 2. Create circuit breaker ===
    print("\n[2] Create Circuit Breaker")
    
    cb = CircuitBreaker(
        name="api_service",
        failure_threshold=3,
        recovery_timeout=5.0,
        half_open_max_calls=2,
    )
    
    print(f"  Name: {cb.name}")
    print(f"  State: {cb.state.name}")
    print(f"  Failure threshold: {cb.failure_threshold}")
    print(f"  Recovery timeout: {cb.recovery_timeout}s")
    
    # === 3. Successful calls ===
    print("\n[3] Successful Calls (Circuit Stays Closed)")
    
    cb = CircuitBreaker(name="healthy_service", failure_threshold=3)
    
    for i in range(3):
        if cb.allow_request():
            # Simulate successful call
            cb.record_success()
            print(f"    Call {i+1}: success")
    
    print(f"  Circuit state: {cb.state.name}")
    
    # === 4. Failures open circuit ===
    print("\n[4] Failures Open Circuit")
    
    cb = CircuitBreaker(name="failing_service", failure_threshold=3, recovery_timeout=0.5)
    
    for i in range(4):
        if cb.allow_request():
            # Simulate failure
            cb.record_failure(ConnectionError(f"Service unavailable (call {i+1})"))
            print(f"    Call {i+1}: failed, recorded")
        else:
            print(f"    Call {i+1}: rejected (circuit open)")
        
        print(f"      State: {cb.state.name}")
    
    # === 5. Circuit recovery ===
    print("\n[5] Circuit Recovery (HALF_OPEN)")
    
    cb = CircuitBreaker(name="recovering_service", failure_threshold=2, recovery_timeout=0.2)
    
    # Trip the circuit
    for i in range(3):
        if cb.allow_request():
            cb.record_failure(TimeoutError("Timeout"))
    
    print(f"  After failures: {cb.state.name}")
    
    # Wait for recovery
    print(f"  Waiting {cb.recovery_timeout}s for recovery...")
    await asyncio.sleep(cb.recovery_timeout + 0.1)
    
    # Check state (should transition to HALF_OPEN)
    print(f"  After timeout: {cb.state.name}")
    
    # Probe call
    if cb.allow_request():
        cb.record_success()
        print("  Probe call: success!")
    
    # Need another success to close (success_threshold=2)
    if cb.allow_request():
        cb.record_success()
        print("  Second probe: success!")
    
    print(f"  After probes: {cb.state.name}")
    
    # === 6. Using call() method ===
    print("\n[6] Using call() Method")
    
    cb = CircuitBreaker(name="call_demo", failure_threshold=3)
    
    def successful_operation():
        return "success"
    
    result = cb.call(successful_operation)
    print(f"  call() result: {result}")
    print(f"  Stats: {cb.stats.successful_requests} success, {cb.stats.failed_requests} failed")
    
    # === 7. Using call_async() method ===
    print("\n[7] Using call_async() Method")
    
    cb = CircuitBreaker(name="async_demo", failure_threshold=3)
    
    async def async_operation():
        await asyncio.sleep(0.01)
        return "async success"
    
    result = await cb.call_async(async_operation)
    print(f"  call_async() result: {result}")
    
    # === 8. Real-world: Protected API calls ===
    print("\n[8] Real-world: Protected API Calls")
    
    api_circuit = CircuitBreaker(
        name="market_data_api",
        failure_threshold=3,
        recovery_timeout=1.0,
    )
    
    async def fetch_price(symbol: str) -> float:
        """Fetch price with circuit breaker protection."""
        async def _fetch():
            if symbol == "INVALID":
                raise ValueError(f"Unknown symbol: {symbol}")
            return 150.0
        
        return await api_circuit.call_async(_fetch)
    
    # Successful calls
    for symbol in ["AAPL", "MSFT", "GOOGL"]:
        try:
            price = await fetch_price(symbol)
            print(f"    {symbol}: ${price}")
        except Exception as e:
            print(f"    {symbol}: Error - {e}")
    
    print(f"  Circuit state: {api_circuit.state.name}")
    print(f"  Stats: {api_circuit.stats.successful_requests} success, {api_circuit.stats.failed_requests} failed")
    
    print("\n" + "=" * 60)
    print("[OK] Circuit Breaker Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
