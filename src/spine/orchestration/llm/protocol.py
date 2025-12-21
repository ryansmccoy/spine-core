"""LLM Provider Protocol — unified interface for language model backends.

Manifesto:
Workflows that include LLM steps need a backend-agnostic interface.
This module defines the ``LLMProvider`` protocol, message types, and
response models so any backend (OpenAI, Bedrock, Ollama, mock) can
be swapped transparently.

ARCHITECTURE
────────────
::

    LLMProvider (Protocol)
      ├── .complete(messages, model, **kwargs) → LLMResponse
      └── .models() → list[str]

    Message(role, content)        — chat message
    Role                          — system | user | assistant
    TokenUsage(prompt, completion, total)
    LLMResponse(content, model, usage, metadata)

Related modules:
    mock.py     — MockLLMProvider for tests
    router.py   — route to provider by model name
    budget.py   — token budget enforcement

Example::

    class BedrockProvider:
        def complete(self, messages, model="anthropic.claude-v2", **kw):
            # call Bedrock API
            return LLMResponse(content="...", model=model, usage=...)

        def models(self):
            return ["anthropic.claude-v2", "amazon.titan-text"]

Tags:
    spine-core, orchestration, llm, protocol, provider-interface, messages

Doc-Types:
    api-reference
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Role(str, Enum):
    """Message role in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    """A single message in a conversation.

    Attributes:
        role: Who sent the message (system, user, assistant).
        content: The message text.
    """

    role: Role
    content: str

    @classmethod
    def system(cls, content: str) -> Message:
        """Create a system message."""
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        """Create a user message."""
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        """Create an assistant message."""
        return cls(role=Role.ASSISTANT, content=content)


@dataclass(frozen=True)
class TokenUsage:
    """Token usage statistics for an LLM call.

    Attributes:
        prompt_tokens: Tokens in the input.
        completion_tokens: Tokens in the output.
        total_tokens: Total tokens consumed.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        """Rough cost estimate at $0.01/1K tokens."""
        return self.total_tokens * 0.00001


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM provider.

    Attributes:
        content: Generated text.
        model: Model identifier used.
        usage: Token usage statistics.
        metadata: Provider-specific metadata.
        finish_reason: Why generation stopped.
    """

    content: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    metadata: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = "stop"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the response."""
        return {
            "content": self.content,
            "model": self.model,
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
        }


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM backends.

    Any object implementing ``complete()`` and ``models()`` can serve
    as an LLM provider for workflow steps.

    Implementors
    ------------
    * ``MockLLMProvider``  — for testing
    * User-defined backends (OpenAI, Bedrock, Ollama, etc.)
    """

    def complete(
        self,
        messages: list[Message],
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion from messages.

        Parameters
        ----------
        messages
            Conversation history.
        model
            Model identifier (provider-specific).
        temperature
            Sampling temperature.
        max_tokens
            Maximum tokens to generate.
        **kwargs
            Provider-specific parameters.

        Returns
        -------
        LLMResponse
            The generated response with usage stats.
        """
        ...

    def models(self) -> list[str]:
        """List available model identifiers."""
        ...
