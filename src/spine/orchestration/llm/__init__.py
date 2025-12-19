"""Spine LLM — provider protocol and utilities for LLM integration.

Defines the ``LLMProvider`` protocol, result types, and mock
implementations for testing workflows with LLM steps.
"""

from spine.orchestration.llm.protocol import (
    LLMProvider,
    LLMResponse,
    Message,
    Role,
    TokenUsage,
)
from spine.orchestration.llm.mock import MockLLMProvider
from spine.orchestration.llm.router import LLMRouter
from spine.orchestration.llm.budget import TokenBudget, BudgetExhaustedError

__all__ = [
    # Protocol
    "LLMProvider",
    "LLMResponse",
    "Message",
    "Role",
    "TokenUsage",
    # Mock
    "MockLLMProvider",
    # Router
    "LLMRouter",
    # Budget
    "TokenBudget",
    "BudgetExhaustedError",
]
