"""Tests for spine.orchestration.llm — LLM provider protocol and utilities."""

from __future__ import annotations

import pytest

from spine.orchestration.llm import (
    BudgetExhaustedError,
    LLMProvider,
    LLMResponse,
    LLMRouter,
    Message,
    MockLLMProvider,
    Role,
    TokenBudget,
    TokenUsage,
)


# ── Message ──────────────────────────────────────────────────────────


class TestMessage:
    """Tests for the Message data class."""

    def test_system_factory(self):
        m = Message.system("You are helpful.")
        assert m.role == Role.SYSTEM
        assert m.content == "You are helpful."

    def test_user_factory(self):
        m = Message.user("Hello")
        assert m.role == Role.USER
        assert m.content == "Hello"

    def test_assistant_factory(self):
        m = Message.assistant("Hi there")
        assert m.role == Role.ASSISTANT

    def test_frozen(self):
        m = Message.user("test")
        with pytest.raises(AttributeError):
            m.content = "changed"


# ── TokenUsage ───────────────────────────────────────────────────────


class TestTokenUsage:
    """Tests for TokenUsage."""

    def test_default_values(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.total_tokens == 0

    def test_estimated_cost(self):
        usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
        assert usage.estimated_cost_usd == pytest.approx(0.01)

    def test_frozen(self):
        usage = TokenUsage(total_tokens=100)
        with pytest.raises(AttributeError):
            usage.total_tokens = 200


# ── LLMResponse ──────────────────────────────────────────────────────


class TestLLMResponse:
    """Tests for LLMResponse."""

    def test_to_dict(self):
        resp = LLMResponse(
            content="Hello!",
            model="gpt-4",
            usage=TokenUsage(10, 5, 15),
        )
        d = resp.to_dict()
        assert d["content"] == "Hello!"
        assert d["model"] == "gpt-4"
        assert d["usage"]["total_tokens"] == 15

    def test_default_finish_reason(self):
        resp = LLMResponse(content="x", model="m")
        assert resp.finish_reason == "stop"


# ── MockLLMProvider ──────────────────────────────────────────────────


class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    def test_default_response(self):
        mock = MockLLMProvider()
        resp = mock.complete([Message.user("hi")])
        assert resp.content == "Mock LLM response"
        assert resp.model == "mock-model-v1"

    def test_custom_default(self):
        mock = MockLLMProvider(default_response="42")
        resp = mock.complete([Message.user("What?")])
        assert resp.content == "42"

    def test_substring_matching(self):
        mock = MockLLMProvider(responses={
            "weather": "It's sunny",
            "time": "It's 3pm",
        })
        r1 = mock.complete([Message.user("What's the weather?")])
        r2 = mock.complete([Message.user("What time is it?")])
        assert r1.content == "It's sunny"
        assert r2.content == "It's 3pm"

    def test_sequence_mode(self):
        mock = MockLLMProvider(sequence=["first", "second", "third"])
        assert mock.complete([Message.user("1")]).content == "first"
        assert mock.complete([Message.user("2")]).content == "second"
        assert mock.complete([Message.user("3")]).content == "third"
        # After sequence exhausted, falls back to default
        assert mock.complete([Message.user("4")]).content == "Mock LLM response"

    def test_call_tracking(self):
        mock = MockLLMProvider()
        mock.complete([Message.user("hi")])
        mock.complete([Message.user("bye")])
        assert mock.call_count == 2
        assert mock.calls[0]["messages"][0]["content"] == "hi"

    def test_token_usage_estimation(self):
        mock = MockLLMProvider()
        resp = mock.complete([Message.user("hello world")])
        assert resp.usage.prompt_tokens > 0
        assert resp.usage.completion_tokens > 0
        assert resp.usage.total_tokens == resp.usage.prompt_tokens + resp.usage.completion_tokens

    def test_reset(self):
        mock = MockLLMProvider(sequence=["a", "b"])
        mock.complete([Message.user("1")])
        mock.reset()
        assert mock.call_count == 0
        assert mock.complete([Message.user("1")]).content == "a"

    def test_custom_model(self):
        mock = MockLLMProvider()
        resp = mock.complete([Message.user("hi")], model="custom-model")
        assert resp.model == "custom-model"

    def test_models_list(self):
        mock = MockLLMProvider(model_name="test-v1")
        assert mock.models() == ["test-v1"]

    def test_implements_protocol(self):
        """MockLLMProvider should satisfy the LLMProvider protocol."""
        mock = MockLLMProvider()
        assert isinstance(mock, LLMProvider)


# ── LLMRouter ────────────────────────────────────────────────────────


class TestLLMRouter:
    """Tests for LLMRouter."""

    def test_route_by_prefix(self):
        mock_a = MockLLMProvider(default_response="A")
        mock_b = MockLLMProvider(default_response="B")
        router = LLMRouter()
        router.register("gpt-", mock_a)
        router.register("claude-", mock_b)

        r1 = router.complete([Message.user("hi")], model="gpt-4")
        r2 = router.complete([Message.user("hi")], model="claude-v2")
        assert r1.content == "A"
        assert r2.content == "B"

    def test_default_provider(self):
        default = MockLLMProvider(default_response="default")
        router = LLMRouter(default_provider=default)
        resp = router.complete([Message.user("hi")], model="unknown-model")
        assert resp.content == "default"

    def test_no_match_no_default_raises(self):
        router = LLMRouter()
        with pytest.raises(ValueError, match="No provider registered"):
            router.complete([Message.user("hi")], model="unknown")

    def test_models_aggregated(self):
        mock_a = MockLLMProvider(model_name="gpt-4")
        mock_b = MockLLMProvider(model_name="claude-v2")
        router = LLMRouter()
        router.register("gpt-", mock_a)
        router.register("claude-", mock_b)
        models = router.models()
        assert "gpt-4" in models
        assert "claude-v2" in models

    def test_provider_count(self):
        router = LLMRouter()
        assert router.provider_count == 0
        router.register("gpt-", MockLLMProvider())
        assert router.provider_count == 1

    def test_longest_prefix_wins(self):
        short = MockLLMProvider(default_response="short")
        long = MockLLMProvider(default_response="long")
        router = LLMRouter()
        router.register("gpt-", short)
        router.register("gpt-4-", long)

        resp = router.complete([Message.user("hi")], model="gpt-4-turbo")
        assert resp.content == "long"

    def test_none_model_uses_default(self):
        default = MockLLMProvider(default_response="ok")
        router = LLMRouter(default_provider=default)
        resp = router.complete([Message.user("hi")])
        assert resp.content == "ok"


# ── TokenBudget ──────────────────────────────────────────────────────


class TestTokenBudget:
    """Tests for TokenBudget."""

    def test_initial_state(self):
        budget = TokenBudget(max_tokens=10_000)
        assert budget.used == 0
        assert budget.remaining == 10_000
        assert budget.utilization == 0.0

    def test_record_usage(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        assert budget.used == 150
        assert budget.remaining == 9_850

    def test_check_within_budget(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(total_tokens=5_000, prompt_tokens=3_000, completion_tokens=2_000))
        budget.check(estimated_tokens=4_000)  # Should not raise

    def test_check_over_budget_raises(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(total_tokens=8_000, prompt_tokens=5_000, completion_tokens=3_000))
        with pytest.raises(BudgetExhaustedError, match="exhausted"):
            budget.check(estimated_tokens=3_000)

    def test_budget_exhausted_error_attributes(self):
        budget = TokenBudget(max_tokens=1_000)
        budget.record(TokenUsage(prompt_tokens=800, completion_tokens=100, total_tokens=900))
        try:
            budget.check(estimated_tokens=200)
        except BudgetExhaustedError as e:
            assert e.budget_max == 1_000
            assert e.used == 900
            assert e.requested == 200

    def test_utilization(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(prompt_tokens=5_000, completion_tokens=0, total_tokens=5_000))
        assert budget.utilization == pytest.approx(0.5)

    def test_call_count(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        budget.record(TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300))
        assert budget.call_count == 2

    def test_summary(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        s = budget.summary()
        assert "10,000" in s
        assert "150" in s

    def test_reset(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        budget.reset()
        assert budget.used == 0
        assert budget.call_count == 0

    def test_to_dict(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        d = budget.to_dict()
        assert d["max_tokens"] == 10_000
        assert d["used"] == 150
        assert d["remaining"] == 9_850
        assert d["call_count"] == 1

    def test_record_with_label(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.record(
            TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            label="step_1",
        )
        assert budget._history[0]["label"] == "step_1"
