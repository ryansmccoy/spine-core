#!/usr/bin/env python3
"""LLM Provider Protocol — backend-agnostic LLM integration.

Demonstrates the LLM provider protocol, mock provider for testing,
router for multi-model dispatch, and token budget enforcement.

Demonstrates:
    1. ``Message``          — chat message construction
    2. ``MockLLMProvider``  — deterministic testing provider
    3. ``LLMRouter``        — route by model prefix
    4. ``TokenBudget``      — enforce spending limits
    5. Substring matching   — contextual mock responses
    6. Sequence mode        — ordered response playback
    7. Protocol compliance  — isinstance check

Architecture::

    LLMProvider (Protocol)
      ├── .complete(messages, model) → LLMResponse
      └── .models()                  → list[str]

    MockLLMProvider → for testing
    LLMRouter       → route to provider by model prefix
    TokenBudget     → enforce token limits

Key Concepts:
    - Any backend implementing ``LLMProvider`` works transparently.
    - ``MockLLMProvider`` supports canned, substring, and sequence modes.
    - ``LLMRouter`` selects providers by model name prefix.
    - ``TokenBudget`` prevents runaway LLM spending.

See Also:
    - ``24_test_harness.py``          — workflow test utilities
    - :mod:`spine.orchestration.llm`

Run:
    python examples/04_orchestration/25_llm_provider.py

Expected Output:
    Demonstrations of mock LLM provider, router, budget tracking,
    and protocol compliance.
"""

from spine.orchestration.llm import (
    BudgetExhaustedError,
    LLMProvider,
    LLMRouter,
    Message,
    MockLLMProvider,
    TokenBudget,
    TokenUsage,
)


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Message construction
    # ------------------------------------------------------------------
    print("=" * 60)
    print("1. Message Construction")
    print("=" * 60)

    messages = [
        Message.system("You are a financial analyst."),
        Message.user("What is the P/E ratio of AAPL?"),
    ]
    for m in messages:
        print(f"  [{m.role.value}] {m.content}")
    print()

    # ------------------------------------------------------------------
    # 2. MockLLMProvider — default response
    # ------------------------------------------------------------------
    print("=" * 60)
    print("2. MockLLMProvider — Default Response")
    print("=" * 60)

    mock = MockLLMProvider(default_response="The P/E ratio is approximately 28.5")
    resp = mock.complete(messages)
    print(f"  Response: {resp.content}")
    print(f"  Model: {resp.model}")
    print(f"  Tokens: {resp.usage.total_tokens}")
    print(f"  Est. cost: ${resp.usage.estimated_cost_usd:.4f}")
    print()

    # ------------------------------------------------------------------
    # 3. Substring matching
    # ------------------------------------------------------------------
    print("=" * 60)
    print("3. MockLLMProvider — Substring Matching")
    print("=" * 60)

    smart_mock = MockLLMProvider(responses={
        "weather": "It's sunny and 72°F",
        "stock": "AAPL is trading at $185",
        "time": "It's 3:00 PM EST",
    })

    queries = ["What's the weather?", "Show me stock prices", "What time is it?"]
    for q in queries:
        resp = smart_mock.complete([Message.user(q)])
        print(f"  Q: {q}")
        print(f"  A: {resp.content}")
    print()

    # ------------------------------------------------------------------
    # 4. Sequence mode
    # ------------------------------------------------------------------
    print("=" * 60)
    print("4. MockLLMProvider — Sequence Mode")
    print("=" * 60)

    seq_mock = MockLLMProvider(sequence=[
        "Step 1: Acknowledge",
        "Step 2: Analyse data",
        "Step 3: Generate report",
    ])
    for i in range(4):
        resp = seq_mock.complete([Message.user(f"Turn {i + 1}")])
        print(f"  Turn {i + 1}: {resp.content}")
    print(f"  Call count: {seq_mock.call_count}")
    print()

    # ------------------------------------------------------------------
    # 5. LLMRouter — multi-model dispatch
    # ------------------------------------------------------------------
    print("=" * 60)
    print("5. LLMRouter — Multi-Model Dispatch")
    print("=" * 60)

    cheap_model = MockLLMProvider(default_response="Quick answer", model_name="gpt-3.5-turbo")
    expensive_model = MockLLMProvider(default_response="Detailed analysis", model_name="gpt-4")
    bedrock_model = MockLLMProvider(default_response="Claude says hello", model_name="claude-v2")

    router = LLMRouter()
    router.register("gpt-3", cheap_model)
    router.register("gpt-4", expensive_model)
    router.register("claude-", bedrock_model)

    models_to_test = ["gpt-3.5-turbo", "gpt-4-turbo", "claude-v2"]
    for model in models_to_test:
        resp = router.complete([Message.user("Test")], model=model)
        print(f"  Model {model}: {resp.content}")
    print(f"  Available models: {router.models()}")
    print()

    # ------------------------------------------------------------------
    # 6. TokenBudget — spending limits
    # ------------------------------------------------------------------
    print("=" * 60)
    print("6. TokenBudget — Spending Limits")
    print("=" * 60)

    budget = TokenBudget(max_tokens=1_000, warn_at=0.8)
    print(f"  Initial: {budget.summary()}")
    print()

    # Simulate several calls
    for i in range(5):
        usage = TokenUsage(prompt_tokens=80, completion_tokens=40, total_tokens=120)
        budget.record(usage, label=f"step_{i + 1}")
        print(f"  After call {i + 1}: {budget.used}/{budget.max_tokens} "
              f"({budget.utilization:.0%}), remaining={budget.remaining}")

    # Try to check budget for a large call
    print()
    try:
        budget.check(estimated_tokens=500)
    except BudgetExhaustedError as e:
        print(f"  Budget exhausted: {e}")
    print()

    # ------------------------------------------------------------------
    # 7. Protocol compliance
    # ------------------------------------------------------------------
    print("=" * 60)
    print("7. Protocol Compliance")
    print("=" * 60)

    assert isinstance(mock, LLMProvider), "MockLLMProvider should implement LLMProvider"
    print("  MockLLMProvider implements LLMProvider: True")
    print(f"  Router provider count: {router.provider_count}")
    print()

    print("All LLM provider examples completed successfully!")


if __name__ == "__main__":
    main()
