"""
Shared pytest fixtures and configuration for spine-core tests.

This module provides:
- Registry cleanup fixtures for test isolation
- Sample pipeline and group definitions
- Temporary directory utilities
- Deterministic ID/timestamp generators for golden tests

Usage:
    Fixtures are auto-discovered by pytest. Simply import them in your test files
    or use them as function arguments (pytest injects them automatically).

    @pytest.fixture
    def my_custom_fixture(sample_group):
        return sample_group.with_modification(...)
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch
from uuid import UUID

import pytest

# Ensure spine package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    FailurePolicy,
    clear_group_registry,
)
from spine.orchestration.models import ExecutionMode
from spine.framework.registry import clear_registry as clear_pipeline_registry


# =============================================================================
# Test Markers Configuration
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers and configure pytest."""
    # Markers are defined in pyproject.toml, this is for documentation
    pass


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark tests based on their location."""
    for item in items:
        # Get the test file path relative to tests directory
        test_path = Path(item.fspath).relative_to(Path(__file__).parent)
        
        # Auto-mark integration tests
        if "integration" in str(test_path):
            item.add_marker(pytest.mark.integration)
        
        # Auto-mark golden tests
        if "golden" in str(test_path) or "_golden" in item.name:
            item.add_marker(pytest.mark.golden)
        
        # Mark all tests without explicit markers as unit tests
        markers = {mark.name for mark in item.iter_markers()}
        if not markers.intersection({"unit", "integration", "slow", "golden"}):
            item.add_marker(pytest.mark.unit)


# =============================================================================
# Registry Cleanup Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_group_registry() -> Generator[None, None, None]:
    """
    Clear group registry before and after each test.
    
    This ensures test isolation - no test can affect another by
    leaving groups registered.
    """
    clear_group_registry()
    yield
    clear_group_registry()


@pytest.fixture
def clean_pipeline_registry_fixture() -> Generator[None, None, None]:
    """
    Clear pipeline registry before and after test.
    
    Not auto-applied because most tests don't modify the pipeline registry.
    Use explicitly when needed:
    
        def test_something(clean_pipeline_registry_fixture):
            ...
    """
    clear_pipeline_registry()
    yield
    clear_pipeline_registry()


# =============================================================================
# Sample Pipeline Group Fixtures
# =============================================================================


@pytest.fixture
def simple_linear_group() -> PipelineGroup:
    """
    Simple linear pipeline group: A -> B -> C.
    
    Useful for testing basic topological sort and execution order.
    """
    return PipelineGroup(
        name="test.simple_linear",
        domain="test",
        description="Simple linear pipeline for testing",
        version=1,
        steps=[
            PipelineStep("step_a", "pipeline.a"),
            PipelineStep("step_b", "pipeline.b", depends_on=["step_a"]),
            PipelineStep("step_c", "pipeline.c", depends_on=["step_b"]),
        ],
    )


@pytest.fixture
def diamond_dependency_group() -> PipelineGroup:
    """
    Diamond dependency pattern:
        A
       / \\
      B   C
       \\ /
        D
    
    Useful for testing DAG resolution with multiple paths.
    """
    return PipelineGroup(
        name="test.diamond",
        domain="test",
        description="Diamond dependency pattern",
        version=1,
        steps=[
            PipelineStep("step_a", "pipeline.a"),
            PipelineStep("step_b", "pipeline.b", depends_on=["step_a"]),
            PipelineStep("step_c", "pipeline.c", depends_on=["step_a"]),
            PipelineStep("step_d", "pipeline.d", depends_on=["step_b", "step_c"]),
        ],
    )


@pytest.fixture
def parallel_independent_group() -> PipelineGroup:
    """
    Group with independent steps (no dependencies).
    
    All steps can run in parallel.
    """
    return PipelineGroup(
        name="test.parallel",
        domain="test",
        description="Independent parallel steps",
        version=1,
        steps=[
            PipelineStep("step_a", "pipeline.a"),
            PipelineStep("step_b", "pipeline.b"),
            PipelineStep("step_c", "pipeline.c"),
        ],
        policy=ExecutionPolicy.parallel(max_concurrency=3),
    )


@pytest.fixture
def group_with_defaults() -> PipelineGroup:
    """
    Group with default parameters.
    
    Useful for testing parameter precedence.
    """
    return PipelineGroup(
        name="test.defaults",
        domain="test",
        description="Group with default parameters",
        version=1,
        defaults={
            "tier": "NMS_TIER_1",
            "force": False,
            "week_ending": "2026-01-03",
        },
        steps=[
            PipelineStep("ingest", "pipeline.ingest"),
            PipelineStep(
                "normalize",
                "pipeline.normalize",
                depends_on=["ingest"],
                params={"force": True},  # Override default
            ),
        ],
    )


@pytest.fixture
def complex_group() -> PipelineGroup:
    """
    Complex group mimicking real-world FINRA workflow.
    
    Useful for integration tests.
    """
    return PipelineGroup(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        description="Weekly FINRA data refresh workflow",
        version=1,
        defaults={"tier": "NMS_TIER_1"},
        steps=[
            PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
            PipelineStep(
                "normalize",
                "finra.otc_transparency.normalize_week",
                depends_on=["ingest"],
            ),
            PipelineStep(
                "aggregate",
                "finra.otc_transparency.aggregate_week",
                depends_on=["normalize"],
            ),
            PipelineStep(
                "rolling",
                "finra.otc_transparency.compute_rolling",
                depends_on=["aggregate"],
            ),
        ],
        policy=ExecutionPolicy.sequential(on_failure=FailurePolicy.STOP),
    )


# =============================================================================
# YAML Fixture Helpers
# =============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def yaml_fixtures_dir(fixtures_dir: Path) -> Path:
    """Path to YAML fixtures directory."""
    return fixtures_dir / "yaml"


@pytest.fixture
def golden_fixtures_dir(fixtures_dir: Path) -> Path:
    """Path to golden test fixtures directory."""
    return fixtures_dir / "golden"


@pytest.fixture
def sample_yaml_group_path(yaml_fixtures_dir: Path) -> Path:
    """Path to a sample YAML group definition."""
    return yaml_fixtures_dir / "sample_group.yaml"


# =============================================================================
# Temporary Directory Utilities
# =============================================================================


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for test files.
    
    Automatically cleaned up after test.
    """
    with tempfile.TemporaryDirectory(prefix="spine_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_yaml_file(temp_dir: Path) -> Generator[Path, None, None]:
    """
    Create a temporary YAML file path.
    
    Returns the path - caller must write content.
    """
    yaml_path = temp_dir / "test_group.yaml"
    yield yaml_path


# =============================================================================
# Deterministic Generators (for golden tests)
# =============================================================================


@pytest.fixture
def deterministic_uuid() -> Generator[str, None, None]:
    """
    Provide a deterministic UUID for tests.
    
    Patches uuid4 to return a predictable value.
    """
    fixed_uuid = "00000000-0000-0000-0000-000000000001"
    
    with patch("uuid.uuid4", return_value=UUID(fixed_uuid)):
        yield fixed_uuid


@pytest.fixture
def deterministic_datetime() -> Generator[datetime, None, None]:
    """
    Provide a deterministic datetime for tests.
    
    Useful for testing timestamp-dependent code.
    """
    fixed_dt = datetime(2026, 1, 9, 12, 0, 0)
    yield fixed_dt


@pytest.fixture
def frozen_time(deterministic_datetime: datetime) -> Generator[datetime, None, None]:
    """
    Freeze time at a specific moment.
    
    Patches datetime.now() and datetime.utcnow().
    """
    from unittest.mock import MagicMock
    
    mock_datetime = MagicMock(wraps=datetime)
    mock_datetime.now.return_value = deterministic_datetime
    mock_datetime.utcnow.return_value = deterministic_datetime
    mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
    
    with patch("datetime.datetime", mock_datetime):
        yield deterministic_datetime


# =============================================================================
# Test Data Factories
# =============================================================================


@pytest.fixture
def make_step():
    """
    Factory fixture for creating PipelineStep instances.
    
    Usage:
        def test_something(make_step):
            step = make_step("my_step", "my.pipeline", depends_on=["other"])
    """
    def _make_step(
        name: str,
        pipeline: str,
        depends_on: list[str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> PipelineStep:
        return PipelineStep(
            name=name,
            pipeline=pipeline,
            depends_on=depends_on or [],
            params=params or {},
        )
    
    return _make_step


@pytest.fixture
def make_group(make_step):
    """
    Factory fixture for creating PipelineGroup instances.
    
    Usage:
        def test_something(make_group):
            group = make_group("test.group", steps=[...])
    """
    def _make_group(
        name: str,
        steps: list[PipelineStep] | None = None,
        domain: str = "test",
        defaults: dict[str, Any] | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> PipelineGroup:
        if steps is None:
            steps = [make_step("default_step", "pipeline.default")]
        
        return PipelineGroup(
            name=name,
            domain=domain,
            steps=steps,
            defaults=defaults or {},
            policy=policy or ExecutionPolicy(),
        )
    
    return _make_group


# =============================================================================
# Assertion Helpers
# =============================================================================


class PlanAssertions:
    """Helper class for plan assertions."""
    
    @staticmethod
    def assert_step_order(plan, expected_order: list[str]) -> None:
        """Assert that plan steps are in the expected order."""
        actual_order = [s.step_name for s in plan.steps]
        assert actual_order == expected_order, (
            f"Step order mismatch:\n"
            f"  Expected: {expected_order}\n"
            f"  Actual:   {actual_order}"
        )
    
    @staticmethod
    def assert_step_before(plan, step_a: str, step_b: str) -> None:
        """Assert that step_a comes before step_b in the plan."""
        order = [s.step_name for s in plan.steps]
        assert order.index(step_a) < order.index(step_b), (
            f"Expected '{step_a}' before '{step_b}', "
            f"but order is: {order}"
        )
    
    @staticmethod
    def assert_params_contain(step, expected: dict[str, Any]) -> None:
        """Assert that step params contain expected key-value pairs."""
        for key, value in expected.items():
            assert key in step.params, f"Missing param: {key}"
            assert step.params[key] == value, (
                f"Param '{key}' mismatch: expected {value}, got {step.params[key]}"
            )


@pytest.fixture
def plan_assertions() -> PlanAssertions:
    """Provide plan assertion helpers."""
    return PlanAssertions()
