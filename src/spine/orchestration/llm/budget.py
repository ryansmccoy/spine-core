"""Token Budget — enforce token spending limits across workflows.

WHY
───
LLM calls cost money.  A runaway workflow could burn through an
entire budget in minutes.  ``TokenBudget`` tracks cumulative token
usage and raises ``BudgetExhaustedError`` before the limit is
exceeded.

ARCHITECTURE
────────────
::

    TokenBudget(max_tokens)
    ├── .record(usage: TokenUsage) → track spending
    ├── .check(estimated)          → raise if over budget
    ├── .remaining                 → tokens left
    ├── .used                      → tokens spent
    └── .utilization               → 0.0 – 1.0

    BudgetExhaustedError           → raised when budget exceeded

Example::

    budget = TokenBudget(max_tokens=10_000)
    budget.record(response.usage)
    budget.check(estimated_tokens=500)   # raises if over
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from spine.orchestration.llm.protocol import TokenUsage

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when a token budget is exceeded.

    Attributes:
        budget_max: Maximum allowed tokens.
        used: Tokens already consumed.
        requested: Tokens that would have been consumed.
    """

    def __init__(
        self,
        budget_max: int,
        used: int,
        requested: int,
    ) -> None:
        self.budget_max = budget_max
        self.used = used
        self.requested = requested
        super().__init__(
            f"Token budget exhausted: {used} used + {requested} requested "
            f"> {budget_max} max ({used + requested - budget_max} over)"
        )


@dataclass
class TokenBudget:
    """Tracks and enforces a token spending limit.

    Attributes:
        max_tokens: Maximum allowed token consumption.
        warn_at: Fraction (0.0–1.0) at which to warn. Default 0.8.
    """

    max_tokens: int
    warn_at: float = 0.8

    # Internal tracking
    _prompt_tokens: int = field(default=0, repr=False)
    _completion_tokens: int = field(default=0, repr=False)
    _call_count: int = field(default=0, repr=False)
    _history: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def used(self) -> int:
        """Total tokens consumed."""
        return self._prompt_tokens + self._completion_tokens

    @property
    def remaining(self) -> int:
        """Tokens still available."""
        return max(0, self.max_tokens - self.used)

    @property
    def utilization(self) -> float:
        """Budget utilization from 0.0 to 1.0."""
        if self.max_tokens <= 0:
            return 1.0
        return min(1.0, self.used / self.max_tokens)

    @property
    def call_count(self) -> int:
        """Number of LLM calls recorded."""
        return self._call_count

    def record(self, usage: TokenUsage, label: str = "") -> None:
        """Record token usage from an LLM call.

        Parameters
        ----------
        usage
            Token usage from the response.
        label
            Optional label for tracking (e.g. step name).
        """
        self._prompt_tokens += usage.prompt_tokens
        self._completion_tokens += usage.completion_tokens
        self._call_count += 1
        self._history.append({
            "label": label,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cumulative": self.used,
        })

        # Warn if approaching limit
        if self.utilization >= self.warn_at:
            logger.warning(
                "token_budget.warning  used=%d  max=%d  utilization=%s  remaining=%d",
                self.used,
                self.max_tokens,
                f"{self.utilization:.0%}",
                self.remaining,
            )

    def check(self, estimated_tokens: int = 0) -> None:
        """Check if the budget can accommodate more tokens.

        Parameters
        ----------
        estimated_tokens
            Estimated tokens for the next call.

        Raises
        ------
        BudgetExhaustedError
            If ``used + estimated_tokens > max_tokens``.
        """
        if self.used + estimated_tokens > self.max_tokens:
            raise BudgetExhaustedError(
                budget_max=self.max_tokens,
                used=self.used,
                requested=estimated_tokens,
            )

    def summary(self) -> str:
        """Human-readable budget summary."""
        lines = [
            f"Token Budget: {self.used:,} / {self.max_tokens:,} "
            f"({self.utilization:.0%} used)",
            f"  Prompt tokens:     {self._prompt_tokens:,}",
            f"  Completion tokens: {self._completion_tokens:,}",
            f"  Remaining:         {self.remaining:,}",
            f"  LLM calls:         {self._call_count}",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all tracking (keeps max_tokens)."""
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._call_count = 0
        self._history.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize budget state."""
        return {
            "max_tokens": self.max_tokens,
            "used": self.used,
            "remaining": self.remaining,
            "utilization": self.utilization,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "call_count": self._call_count,
        }
