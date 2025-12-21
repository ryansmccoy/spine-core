"""Mock LLM Provider — deterministic provider for testing.

Manifesto:
Testing LLM-powered workflows requires a provider that returns
predictable results without network calls.  ``MockLLMProvider``
supports canned responses, response scripting, and call tracking.

ARCHITECTURE
────────────
::

    MockLLMProvider
      ├── .complete(messages) → LLMResponse (canned or scripted)
      ├── .models()           → list of fake model names
      ├── .calls              → list of all calls made
      └── .call_count         → total calls

    Configuration:
      default_response   — text returned for all calls
      responses          — mapping of prompt substrings → responses
      sequence           — list of responses returned in order

Example::

    provider = MockLLMProvider(default_response="42")
    resp = provider.complete([Message.user("What is 6*7?")])
    assert resp.content == "42"

    provider = MockLLMProvider(sequence=["first", "second"])
    assert provider.complete([Message.user("1")]).content == "first"
    assert provider.complete([Message.user("2")]).content == "second"

Tags:
    spine-core, orchestration, llm, mock, testing, deterministic

Doc-Types:
    api-reference
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spine.orchestration.llm.protocol import (
    LLMResponse,
    Message,
    TokenUsage,
)


@dataclass
class MockLLMProvider:
    """Deterministic LLM provider for testing.

    Supports three response modes (checked in order):
    1. ``responses``: match against the last user message content
    2. ``sequence``: return responses in order
    3. ``default_response``: fallback for all calls

    Attributes:
        default_response: Text returned when no match/sequence entry.
        responses: Map of substring matches → response text.
        sequence: Ordered list of responses (consumed on each call).
        model_name: Fake model name for responses.
        tokens_per_char: Approximate tokens per character (for usage).
    """

    default_response: str = "Mock LLM response"
    responses: dict[str, str] = field(default_factory=dict)
    sequence: list[str] = field(default_factory=list)
    model_name: str = "mock-model-v1"
    tokens_per_char: float = 0.25

    # Tracking
    calls: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _sequence_index: int = field(default=0, repr=False)

    def complete(
        self,
        messages: list[Message],
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return a mock completion.

        Resolution order:
        1. Check ``responses`` for substring match on last user message.
        2. Use next entry from ``sequence`` (if available).
        3. Fall back to ``default_response``.
        """
        effective_model = model or self.model_name

        # Track the call
        self.calls.append({
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "model": effective_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
        })

        # Determine response content
        content = self._resolve_content(messages)

        # Estimate token usage
        prompt_text = " ".join(m.content for m in messages)
        prompt_tokens = max(1, int(len(prompt_text) * self.tokens_per_char))
        completion_tokens = max(1, int(len(content) * self.tokens_per_char))

        return LLMResponse(
            content=content,
            model=effective_model,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            metadata={"provider": "mock"},
        )

    def models(self) -> list[str]:
        """Return a list of fake model names."""
        return [self.model_name]

    @property
    def call_count(self) -> int:
        """Total number of calls made."""
        return len(self.calls)

    def reset(self) -> None:
        """Reset call tracking and sequence index."""
        self.calls.clear()
        self._sequence_index = 0

    def _resolve_content(self, messages: list[Message]) -> str:
        """Determine response content from configured sources."""
        # 1. Check substring-matched responses
        if self.responses and messages:
            last_user = next(
                (m.content for m in reversed(messages) if m.role.value == "user"),
                "",
            )
            for key, response in self.responses.items():
                if key in last_user:
                    return response

        # 2. Use sequence
        if self.sequence and self._sequence_index < len(self.sequence):
            content = self.sequence[self._sequence_index]
            self._sequence_index += 1
            return content

        # 3. Default
        return self.default_response
