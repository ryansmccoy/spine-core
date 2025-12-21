"""Spine LLM — provider protocol and utilities for LLM integration.

Defines the ``LLMProvider`` protocol, result types, and mock
implementations for testing workflows with LLM steps.

Manifesto:
    LLM providers differ wildly in API shape and billing.  The LLM
    subpackage defines a single ``LLMProvider`` protocol so workflows
    can call any model through one interface, with budgets and mocks
    for safe development.

Tags:
    spine-core, orchestration, llm, provider-protocol, budget, mock

Doc-Types:
    api-reference
"""

from spine.orchestration.llm.budget import BudgetExhaustedError, TokenBudget
from spine.orchestration.llm.mock import MockLLMProvider
from spine.orchestration.llm.protocol import (
    LLMProvider,
    LLMResponse,
    Message,
    Role,
    TokenUsage,
)
from spine.orchestration.llm.router import LLMRouter

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
