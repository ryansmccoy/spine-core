"""LLM Router — route requests to the right provider by model name.

Manifesto:
Workflows may use different models for different steps (e.g. a cheap
model for classification, an expensive one for generation).  The router
selects the appropriate ``LLMProvider`` based on the model name.

ARCHITECTURE
────────────
::

    LLMRouter
      ├── register(prefix, provider)     → add a provider
      ├── complete(messages, model)      → route to matching provider
      ├── models()                       → aggregate all models
      └── default_provider               → fallback

Example::

    router = LLMRouter()
    router.register("gpt-", openai_provider)
    router.register("claude-", bedrock_provider)
    router.default_provider = mock_provider

    # Routes to openai_provider:
    router.complete([Message.user("hi")], model="gpt-4")

    # Routes to bedrock_provider:
    router.complete([Message.user("hi")], model="claude-v2")

Tags:
    spine-core, orchestration, llm, router, model-selection, fallback

Doc-Types:
    api-reference
"""

from __future__ import annotations

import logging
from typing import Any

from spine.orchestration.llm.protocol import (
    LLMProvider,
    LLMResponse,
    Message,
)

logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM requests to the appropriate provider.

    Providers are registered with a prefix.  When ``complete()`` is
    called with a model name, the router finds the provider whose
    prefix matches the model name.  If no match, the
    ``default_provider`` is used.

    Attributes:
        default_provider: Fallback provider when no prefix matches.
    """

    def __init__(self, default_provider: LLMProvider | None = None) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self.default_provider = default_provider

    def register(self, prefix: str, provider: LLMProvider) -> None:
        """Register a provider for models matching a prefix.

        Parameters
        ----------
        prefix
            Model name prefix (e.g. ``"gpt-"``, ``"claude-"``).
        provider
            The LLM provider to use for matching models.
        """
        self._providers[prefix] = provider
        logger.debug("llm_router.registered  prefix=%s", prefix)

    def complete(
        self,
        messages: list[Message],
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        """Route a completion request to the appropriate provider.

        Parameters
        ----------
        messages
            Conversation history.
        model
            Model identifier.  Used to select the provider.
        temperature
            Sampling temperature.
        max_tokens
            Maximum tokens.
        **kwargs
            Passed through to the provider.

        Returns
        -------
        LLMResponse
            Response from the selected provider.

        Raises
        ------
        ValueError
            If no provider matches and no default is set.
        """
        provider = self._resolve_provider(model)
        return provider.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def models(self) -> list[str]:
        """Aggregate all available models from all providers."""
        all_models: list[str] = []
        seen: set[str] = set()
        for provider in self._providers.values():
            for m in provider.models():
                if m not in seen:
                    all_models.append(m)
                    seen.add(m)
        if self.default_provider:
            for m in self.default_provider.models():
                if m not in seen:
                    all_models.append(m)
                    seen.add(m)
        return all_models

    @property
    def provider_count(self) -> int:
        """Number of registered providers (excluding default)."""
        return len(self._providers)

    def _resolve_provider(self, model: str | None) -> LLMProvider:
        """Find the provider for a given model name."""
        if model:
            # Check prefixes (longest match first for specificity)
            for prefix in sorted(self._providers, key=len, reverse=True):
                if model.startswith(prefix):
                    return self._providers[prefix]

        if self.default_provider:
            return self.default_provider

        raise ValueError(
            f"No provider registered for model {model!r} and no default set. "
            f"Registered prefixes: {sorted(self._providers.keys())}"
        )
