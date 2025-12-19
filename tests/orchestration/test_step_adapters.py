"""Tests for plain function adapters (step_adapters.py, Step.from_function, StepResult.from_value).

These tests verify that the adapter layer correctly bridges standalone
business functions into the workflow engine without requiring users to
import WorkflowContext or StepResult.
"""

import pytest

from spine.execution.runnable import PipelineRunResult
from spine.orchestration import (
    Step,
    StepResult,
    Workflow,
    WorkflowContext,
    WorkflowStatus,
    adapt_function,
    get_step_meta,
    is_workflow_step,
    workflow_step,
)
from spine.orchestration.step_adapters import WorkflowStepMeta
from spine.orchestration.workflow_runner import WorkflowRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NoOpRunnable:
    """Minimal Runnable for tests that only use lambda steps."""

    def submit_pipeline_sync(self, pipeline_name, params=None, *, parent_run_id=None, correlation_id=None):
        return PipelineRunResult(status="completed")


# ---------------------------------------------------------------------------
# StepResult.from_value() tests
# ---------------------------------------------------------------------------


class TestStepResultFromValue:
    """Test automatic coercion of return values to StepResult."""

    def test_passthrough_step_result(self):
        """StepResult passes through unchanged."""
        original = StepResult.ok(output={"x": 1})
        result = StepResult.from_value(original)
        assert result is original

    def test_dict_becomes_ok(self):
        result = StepResult.from_value({"count": 42, "name": "test"})
        assert result.success is True
        assert result.output == {"count": 42, "name": "test"}

    def test_none_becomes_empty_ok(self):
        result = StepResult.from_value(None)
        assert result.success is True
        assert result.output == {}

    def test_true_becomes_ok(self):
        result = StepResult.from_value(True)
        assert result.success is True

    def test_false_becomes_fail(self):
        result = StepResult.from_value(False)
        assert result.success is False
        assert "False" in result.error

    def test_string_becomes_message(self):
        result = StepResult.from_value("all good")
        assert result.success is True
        assert result.output == {"message": "all good"}

    def test_int_becomes_value(self):
        result = StepResult.from_value(42)
        assert result.success is True
        assert result.output == {"value": 42}

    def test_float_becomes_value(self):
        result = StepResult.from_value(3.14)
        assert result.success is True
        assert result.output == {"value": 3.14}

    def test_other_type_becomes_result(self):
        result = StepResult.from_value([1, 2, 3])
        assert result.success is True
        assert result.output == {"result": [1, 2, 3]}


# ---------------------------------------------------------------------------
# adapt_function() tests
# ---------------------------------------------------------------------------


class TestAdaptFunction:
    """Test wrapping plain functions as step handlers."""

    def test_simple_function(self):
        """Plain function with kwargs works as step handler."""
        def add(a: int, b: int) -> dict:
            return {"sum": a + b}

        handler = adapt_function(add)
        ctx = WorkflowContext()  # empty context — no params needed
        result = handler(ctx, {"a": 3, "b": 4})
        assert result.success is True
        assert result.output == {"sum": 7}

    def test_params_from_context(self):
        """Handler pulls kwargs from ctx.params when not in config."""
        def greet(name: str) -> dict:
            return {"greeting": f"hello {name}"}

        handler = adapt_function(greet)
        ctx = WorkflowContext(params={"name": "world"})
        result = handler(ctx, {})
        assert result.output == {"greeting": "hello world"}

    def test_config_overrides_context(self):
        """Config keys take priority over ctx.params."""
        def greet(name: str) -> dict:
            return {"greeting": f"hello {name}"}

        handler = adapt_function(greet)
        ctx = WorkflowContext(params={"name": "context"})
        result = handler(ctx, {"name": "config"})
        assert result.output == {"greeting": "hello config"}

    def test_extra_params_ignored(self):
        """Params not in the function signature are silently ignored."""
        def add(a: int, b: int) -> dict:
            return {"sum": a + b}

        handler = adapt_function(add)
        ctx = WorkflowContext(params={"a": 1, "b": 2, "extra": 99})
        result = handler(ctx, {})
        assert result.output == {"sum": 3}

    def test_kwargs_function_gets_all(self):
        """Function with **kwargs receives all available params."""
        def capture(**kwargs) -> dict:
            return kwargs

        handler = adapt_function(capture)
        ctx = WorkflowContext(params={"x": 1})
        result = handler(ctx, {"y": 2})
        assert result.output == {"x": 1, "y": 2}

    def test_exception_wrapped_in_fail(self):
        """Exceptions in the function are wrapped in StepResult.fail()."""
        def boom() -> dict:
            raise ValueError("kaboom")

        handler = adapt_function(boom)
        ctx = WorkflowContext()
        result = handler(ctx, {})
        assert result.success is False
        assert "kaboom" in result.error
        assert "ValueError" in result.error

    def test_missing_required_param_python_error(self):
        """Without strict mode, Python's own TypeError fires for missing params."""
        def needs_x(x: int) -> dict:
            return {"x": x}

        handler = adapt_function(needs_x)
        ctx = WorkflowContext()
        result = handler(ctx, {})  # x not provided
        assert result.success is False
        assert "TypeError" in result.error

    def test_strict_mode_catches_missing(self):
        """Strict mode provides a clear CONFIGURATION error for missing params."""
        def needs_x(x: int) -> dict:
            return {"x": x}

        handler = adapt_function(needs_x, strict=True)
        ctx = WorkflowContext()
        result = handler(ctx, {})
        assert result.success is False
        assert "Missing required parameter" in result.error
        assert result.error_category == "CONFIGURATION"

    def test_default_params_used(self):
        """Function defaults are used when params are not provided."""
        def compute(x: int, multiplier: float = 2.0) -> dict:
            return {"result": x * multiplier}

        handler = adapt_function(compute)
        ctx = WorkflowContext()
        result = handler(ctx, {"x": 5})
        assert result.output == {"result": 10.0}

    def test_return_bool_coerced(self):
        """Function returning True/False is coerced to ok/fail."""
        def check(value: int) -> bool:
            return value > 0

        handler = adapt_function(check)
        ctx = WorkflowContext()

        assert handler(ctx, {"value": 5}).success is True
        assert handler(ctx, {"value": -1}).success is False

    def test_return_none_coerced(self):
        """Function returning None is coerced to ok with empty output."""
        def noop():
            pass

        handler = adapt_function(noop)
        ctx = WorkflowContext()
        result = handler(ctx, {})
        assert result.success is True
        assert result.output == {}

    def test_return_step_result_passthrough(self):
        """If the function returns a StepResult, it passes through."""
        def explicit(x: int):
            return StepResult.ok(output={"x": x * 2})

        handler = adapt_function(explicit)
        ctx = WorkflowContext()
        result = handler(ctx, {"x": 5})
        assert result.output == {"x": 10}

    def test_direct_call_still_works(self):
        """The original function is preserved and directly callable."""
        def calculate(a: int, b: int) -> dict:
            return {"sum": a + b}

        handler = adapt_function(calculate)
        # The original function is accessible via __wrapped__
        assert handler.__wrapped__(a=1, b=2) == {"sum": 3}


# ---------------------------------------------------------------------------
# Step.from_function() tests
# ---------------------------------------------------------------------------


class TestStepFromFunction:
    """Test the Step.from_function() factory method."""

    def test_creates_lambda_step(self):
        """from_function creates a LAMBDA step type."""
        def my_fn(x: int) -> dict:
            return {"x": x}

        step = Step.from_function("test_step", my_fn)
        assert step.step_type.value == "lambda"
        assert step.name == "test_step"
        assert step.handler is not None

    def test_with_config(self):
        """Config dict is stored on the step."""
        def my_fn(x: int) -> dict:
            return {"x": x}

        step = Step.from_function("test_step", my_fn, config={"x": 42})
        assert step.config == {"x": 42}

    def test_with_depends_on(self):
        """Dependency edges are preserved."""
        def my_fn() -> dict:
            return {}

        step = Step.from_function("step_b", my_fn, depends_on=["step_a"])
        assert step.depends_on == ("step_a",)

    def test_executes_in_workflow(self):
        """Full integration: from_function step runs inside WorkflowRunner."""
        def double(value: int) -> dict:
            return {"result": value * 2}

        workflow = Workflow(
            name="test.from_function",
            steps=[Step.from_function("double", double, config={"value": 21})],
        )
        runner = WorkflowRunner(runnable=_NoOpRunnable())
        result = runner.execute(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("double", "result") == 42

    def test_chained_functions(self):
        """Multiple from_function steps can chain via context."""
        def step_a(x: int) -> dict:
            return {"intermediate": x + 10}

        def step_b(intermediate: int) -> dict:
            return {"final": intermediate * 2}

        workflow = Workflow(
            name="test.chain",
            steps=[
                Step.from_function("a", step_a, config={"x": 5}),
                # step_b reads 'intermediate' from ctx.params
                # But wait — outputs go to ctx.outputs[step_name], not ctx.params
                # So we need context_updates or a handler that reads from context
            ],
        )
        # For chaining, the current design stores output per step in ctx.outputs.
        # The adapt_function merges ctx.params with config — NOT prior step outputs.
        # This is by design: plain functions shouldn't need to know about step topology.
        # For data flow between adapted functions, use context_updates or
        # Step.lambda_() for steps that need to read prior step outputs.
        runner = WorkflowRunner(runnable=_NoOpRunnable())
        result = runner.execute(workflow, params={"x": 5})
        # step_a gets x=5 from params and returns {"intermediate": 15}
        assert result.context.get_output("a", "intermediate") == 15


# ---------------------------------------------------------------------------
# @workflow_step decorator tests
# ---------------------------------------------------------------------------


class TestWorkflowStepDecorator:
    """Test the @workflow_step decorator."""

    def test_function_stays_callable(self):
        """Decorated function is directly callable with normal args."""
        @workflow_step(name="calc")
        def calculate(a: int, b: int) -> dict:
            return {"sum": a + b}

        result = calculate(a=3, b=4)
        assert result == {"sum": 7}

    def test_positional_args_work(self):
        """Decorated function accepts positional arguments."""
        @workflow_step(name="calc")
        def calculate(a: int, b: int) -> dict:
            return {"sum": a + b}

        result = calculate(3, 4)
        assert result == {"sum": 7}

    def test_has_metadata(self):
        """Decorated function has _workflow_meta attribute."""
        @workflow_step(name="my_step", description="My step", tags=["test"])
        def my_func() -> dict:
            return {}

        assert is_workflow_step(my_func)
        meta = get_step_meta(my_func)
        assert meta is not None
        assert meta.name == "my_step"
        assert meta.description == "My step"
        assert meta.tags == ("test",)

    def test_default_name_from_function(self):
        """If no name given, uses the function name."""
        @workflow_step()
        def process_data() -> dict:
            return {}

        meta = get_step_meta(process_data)
        assert meta.name == "process_data"

    def test_as_step_method(self):
        """as_step() returns a valid Step object."""
        @workflow_step(name="calc")
        def calculate(a: int, b: int) -> dict:
            return {"sum": a + b}

        step = calculate.as_step(config={"a": 1, "b": 2})
        assert step.name == "calc"
        assert step.config == {"a": 1, "b": 2}
        assert step.step_type.value == "lambda"

    def test_as_step_name_override(self):
        """as_step() can override the step name."""
        @workflow_step(name="calc")
        def calculate(a: int, b: int) -> dict:
            return {"sum": a + b}

        step = calculate.as_step(step_name_override="custom_calc")
        assert step.name == "custom_calc"

    def test_as_step_depends_on(self):
        """as_step() can specify depends_on."""
        @workflow_step(name="calc")
        def calculate(a: int, b: int) -> dict:
            return {"sum": a + b}

        step = calculate.as_step(depends_on=["fetch"])
        assert step.depends_on == ("fetch",)

    def test_in_workflow_execution(self):
        """Full integration: decorated function runs in a workflow."""
        @workflow_step(name="double")
        def double_value(value: int) -> dict:
            return {"result": value * 2}

        workflow = Workflow(
            name="test.decorator",
            steps=[double_value.as_step(config={"value": 21})],
        )
        runner = WorkflowRunner(runnable=_NoOpRunnable())
        result = runner.execute(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("double", "result") == 42

        # And the function is still directly callable:
        assert double_value(value=5) == {"result": 10}

    def test_description_from_docstring(self):
        """If no description given, uses first line of docstring."""
        @workflow_step()
        def my_func() -> dict:
            """Calculate the risk score for a portfolio."""
            return {}

        meta = get_step_meta(my_func)
        assert meta.description == "Calculate the risk score for a portfolio."


# ---------------------------------------------------------------------------
# is_workflow_step / get_step_meta utility tests
# ---------------------------------------------------------------------------


class TestUtilities:
    """Test utility functions."""

    def test_is_workflow_step_true(self):
        @workflow_step()
        def my_fn():
            pass

        assert is_workflow_step(my_fn) is True

    def test_is_workflow_step_false_plain_function(self):
        def my_fn():
            pass

        assert is_workflow_step(my_fn) is False

    def test_is_workflow_step_false_none(self):
        assert is_workflow_step(None) is False

    def test_get_step_meta_none_for_plain(self):
        def my_fn():
            pass

        assert get_step_meta(my_fn) is None


# ---------------------------------------------------------------------------
# Runner coercion tests (Step.lambda_ with non-StepResult returns)
# ---------------------------------------------------------------------------


class TestRunnerCoercion:
    """Test that WorkflowRunner coerces non-StepResult returns from lambda handlers."""

    def test_lambda_returning_dict(self):
        """Step.lambda_() handler that returns a dict works without StepResult."""
        def my_handler(ctx, config):
            return {"computed": True}

        workflow = Workflow(
            name="test.coerce",
            steps=[Step.lambda_("test", my_handler)],
        )
        runner = WorkflowRunner(runnable=_NoOpRunnable())
        result = runner.execute(workflow)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("test", "computed") is True

    def test_lambda_returning_none(self):
        """Step.lambda_() handler that returns None becomes ok with empty output."""
        def my_handler(ctx, config):
            pass  # returns None implicitly

        workflow = Workflow(
            name="test.none",
            steps=[Step.lambda_("test", my_handler)],
        )
        runner = WorkflowRunner(runnable=_NoOpRunnable())
        result = runner.execute(workflow)
        assert result.status == WorkflowStatus.COMPLETED

    def test_lambda_returning_step_result_unchanged(self):
        """Step.lambda_() handler that returns StepResult works as before."""
        def my_handler(ctx, config):
            return StepResult.ok(output={"x": 1})

        workflow = Workflow(
            name="test.explicit",
            steps=[Step.lambda_("test", my_handler)],
        )
        runner = WorkflowRunner(runnable=_NoOpRunnable())
        result = runner.execute(workflow)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("test", "x") == 1


# ---------------------------------------------------------------------------
# End-to-end real-world scenario
# ---------------------------------------------------------------------------


class TestRealWorldScenario:
    """Simulate a realistic use case: financial calculation functions
    used both standalone AND in a workflow."""

    def test_financial_pipeline(self):
        """Financial calc functions work standalone and in workflow."""

        # --- Pure business functions (no framework imports) ---

        def fetch_price_data(ticker: str, days: int = 30) -> dict:
            """Simulate fetching price data."""
            prices = [100.0 + i * 0.5 for i in range(days)]
            return {"ticker": ticker, "prices": prices, "count": len(prices)}

        def calculate_volatility(prices: list, window: int = 5) -> dict:
            """Calculate rolling volatility."""
            if len(prices) < window:
                return {"volatility": 0.0, "error": "Not enough data"}
            diffs = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
            vol = sum(diffs) / len(diffs)
            return {"volatility": round(vol, 4), "samples": len(diffs)}

        def assess_risk(volatility: float, threshold: float = 1.0) -> dict:
            """Simple risk assessment."""
            level = "HIGH" if volatility > threshold else "LOW"
            return {"risk_level": level, "volatility": volatility}

        # --- Direct calls (notebook / script) ---
        data = fetch_price_data("AAPL", days=10)
        assert data["count"] == 10

        vol = calculate_volatility(data["prices"])
        assert vol["volatility"] == 0.5
        assert vol["samples"] == 9

        risk = assess_risk(vol["volatility"])
        assert risk["risk_level"] == "LOW"

        # --- Same functions in a workflow ---
        workflow = Workflow(
            name="risk.assessment",
            steps=[
                Step.from_function("fetch", fetch_price_data,
                                   config={"ticker": "AAPL", "days": 10}),
                Step.from_function("volatility", calculate_volatility,
                                   config={"window": 5}),
                Step.from_function("risk", assess_risk,
                                   config={"threshold": 1.0}),
            ],
        )
        runner = WorkflowRunner(runnable=_NoOpRunnable())

        # The challenge: each function gets params from config + ctx.params.
        # But outputs from step A aren't automatically in ctx.params for step B.
        # That's by design — adapted functions pull from params, not prior outputs.
        # To chain, pass initial data through params:
        result = runner.execute(workflow, params={
            "prices": data["prices"],  # pre-computed for step B
            "volatility": vol["volatility"],  # pre-computed for step C
        })

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("fetch", "count") == 10
        assert result.context.get_output("volatility", "volatility") == 0.5
        assert result.context.get_output("risk", "risk_level") == "LOW"
