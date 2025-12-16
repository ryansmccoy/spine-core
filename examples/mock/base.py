"""Base mock API classes for spine-core examples.

These classes provide common functionality for mock APIs:
- Simulated network latency
- Call counting for testing
- Success/failure simulation
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockResponse:
    """Simulates an API response.
    
    Attributes:
        data: The response payload
        success: Whether the request succeeded
        error: Error message if failed
        latency_ms: Simulated response time
    """
    data: Any
    success: bool = True
    error: str | None = None
    latency_ms: float = 10


class MockAPIBase:
    """Base class for mock APIs that mimic real behavior.
    
    Features:
    - Configurable latency simulation
    - Optional random failures
    - Call counting for verification
    
    Example:
        >>> api = MockAPIBase(latency_ms=50, failure_rate=0.1)
        >>> await api._simulate_latency()  # Waits ~50ms
        >>> api._call_count  # 1
    """
    
    def __init__(
        self, 
        latency_ms: float = 10, 
        failure_rate: float = 0.0,
        seed: int | None = None,
    ):
        """Initialize mock API.
        
        Args:
            latency_ms: Simulated response latency in milliseconds
            failure_rate: Probability of random failure (0.0 to 1.0)
            seed: Random seed for reproducible failures
        """
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate
        self._call_count = 0
        self._rng = random.Random(seed)
    
    async def _simulate_latency(self) -> None:
        """Simulate network latency."""
        await asyncio.sleep(self.latency_ms / 1000)
        self._call_count += 1
    
    def _should_fail(self) -> bool:
        """Determine if this call should simulate a failure."""
        if self.failure_rate <= 0:
            return False
        return self._rng.random() < self.failure_rate
    
    def reset(self) -> None:
        """Reset call counter and state."""
        self._call_count = 0
