"""Tests for pipeline layer."""

from datetime import date
from decimal import Decimal

import pytest

from market_spine.pipelines.base import Pipeline, Step, StepResult, StepStatus, FunctionStep
from market_spine.pipelines.registry import PipelineRegistry
from market_spine.pipelines.runner import PipelineRunner
from market_spine.repositories.executions import ExecutionRepository
from market_spine.repositories.otc import OTCRepository


class TestStep:
    """Tests for Step base class."""

    def test_function_step_success(self):
        """Test FunctionStep with successful function."""

        def my_func(ctx):
            return {"result": ctx["params"]["value"] * 2}

        step = FunctionStep(my_func, name="doubler")
        result = step.execute({"params": {"value": 5}})

        assert result.status == StepStatus.COMPLETED
        assert result.output == {"result": 10}
        assert result.duration_ms >= 0  # Can be 0 on fast machines

    def test_function_step_failure(self):
        """Test FunctionStep with failing function."""

        def failing_func(ctx):
            raise ValueError("Intentional error")

        step = FunctionStep(failing_func)
        result = step.execute({})

        assert result.status == StepStatus.FAILED
        assert "Intentional error" in result.error


class TestPipelineRegistry:
    """Tests for PipelineRegistry."""

    def test_register_pipeline(self):
        """Test registering a pipeline."""
        initial_count = PipelineRegistry.count()

        @PipelineRegistry.register
        class TestPipeline(Pipeline):
            name = "test.register"
            description = "Test pipeline"

            def build_steps(self, params):
                return []

        assert PipelineRegistry.count() == initial_count + 1
        assert PipelineRegistry.get("test.register") is TestPipeline

    def test_get_or_raise(self):
        """Test get_or_raise raises for missing pipeline."""
        with pytest.raises(ValueError, match="not found"):
            PipelineRegistry.get_or_raise("nonexistent.pipeline")

    def test_list_pipelines(self):
        """Test listing pipelines."""
        pipelines = PipelineRegistry.list_pipelines()

        assert isinstance(pipelines, list)
        for p in pipelines:
            assert "name" in p
            assert "description" in p


class TestPipelineExecution:
    """Tests for pipeline execution."""

    def test_simple_pipeline_execution(self):
        """Test executing a simple pipeline."""

        class SimplePipeline(Pipeline):
            name = "test.simple"
            description = "Simple test pipeline"

            def build_steps(self, params):
                return [
                    FunctionStep(lambda ctx: {"step": 1}),
                    FunctionStep(lambda ctx: {"step": 2, "prev": ctx["outputs"]["<lambda>"]}),
                ]

        pipeline = SimplePipeline()
        result = pipeline.execute({"key": "value"})

        assert result.success is True
        assert len(result.steps) == 2
        assert result.total_duration_ms > 0

    def test_pipeline_with_failure(self):
        """Test pipeline stops on step failure."""

        class FailingPipeline(Pipeline):
            name = "test.failing"

            def build_steps(self, params):
                return [
                    FunctionStep(lambda ctx: "ok"),
                    FunctionStep(lambda ctx: 1 / 0),  # Division by zero
                    FunctionStep(lambda ctx: "never reached"),
                ]

        pipeline = FailingPipeline()
        result = pipeline.execute({})

        assert result.success is False
        assert len(result.steps) == 2  # Third step not executed
        assert "division" in result.error.lower()

    def test_pipeline_validation(self):
        """Test pipeline parameter validation."""

        class ValidatingPipeline(Pipeline):
            name = "test.validating"

            def build_steps(self, params):
                return []

            def validate_params(self, params):
                if "required_key" not in params:
                    return False, "required_key is missing"
                return True, None

        pipeline = ValidatingPipeline()

        result = pipeline.execute({})
        assert result.success is False
        assert "required_key" in result.error

        result = pipeline.execute({"required_key": "value"})
        assert result.success is True


class TestPipelineRunner:
    """Tests for PipelineRunner."""

    def test_run_with_execution_tracking(self, db_conn, clean_tables):
        """Test running pipeline with execution tracking."""
        # Create execution
        exec_id = ExecutionRepository.create("otc.normalize")

        # Run pipeline
        result = PipelineRunner.run(exec_id, "otc.normalize", {"limit": 100})

        assert result.success is True

        # Check execution was updated
        execution = ExecutionRepository.get(exec_id)
        assert execution["status"] == "completed"
        assert execution["started_at"] is not None
        assert execution["completed_at"] is not None

    def test_run_nonexistent_pipeline(self, db_conn, clean_tables):
        """Test running nonexistent pipeline."""
        exec_id = ExecutionRepository.create("does.not.exist")

        result = PipelineRunner.run(exec_id, "does.not.exist", {})

        assert result.success is False
        assert "not found" in result.error

    def test_run_direct(self, db_conn, clean_tables):
        """Test running pipeline directly without tracking."""
        result = PipelineRunner.run_direct("otc.normalize", {"limit": 100})

        assert result.success is True


class TestOTCPipelines:
    """Tests for OTC domain pipelines."""

    def test_otc_normalize_pipeline(self, db_conn, clean_tables, sample_raw_trades):
        """Test OTC normalize pipeline."""
        # Setup raw trades
        OTCRepository.bulk_upsert_raw_trades(sample_raw_trades, source="test")

        result = PipelineRunner.run_direct("otc.normalize", {})

        assert result.success is True
        assert result.output["inserted"] == 2

    def test_otc_metrics_pipeline(self, db_conn, clean_tables, sample_trades):
        """Test OTC metrics pipeline."""
        # Setup normalized trades
        OTCRepository.bulk_upsert_trades(sample_trades)

        result = PipelineRunner.run_direct("otc.metrics", {"date": "2024-01-15"})

        assert result.success is True
        assert result.output["symbols_computed"] == 2  # AAPL and GOOGL

    def test_otc_fetch_logical_key(self):
        """Test OTC fetch pipeline generates logical key."""
        from market_spine.pipelines.otc import OTCFetchPipeline

        pipeline = OTCFetchPipeline()

        key = pipeline.get_logical_key({"start_date": "2024-01-15", "end_date": "2024-01-15"})
        assert key == "otc.fetch:2024-01-15:2024-01-15"

        # Default to today if not provided
        key_default = pipeline.get_logical_key({})
        assert key_default.startswith("otc.fetch:")
