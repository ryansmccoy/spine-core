"""
Shared pytest fixtures and configuration for spine-core tests.

This module provides:
- Registry cleanup fixtures for test isolation
- Sample workflow definitions
- Temporary directory utilities
- Deterministic ID/timestamp generators for golden tests

Usage:
    Fixtures are auto-discovered by pytest. Simply import them in your test files
    or use them as function arguments (pytest injects them automatically).

    @pytest.fixture
    def my_custom_fixture(simple_linear_workflow):
        ...
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
    Workflow,
    Step,
    WorkflowExecutionPolicy,
    ExecutionMode,
    FailurePolicy,
    clear_workflow_registry,
)
from spine.framework.registry import clear_registry as clear_operation_registry


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
def clean_workflow_registry_fixture() -> Generator[None, None, None]:
    """
    Clear workflow registry before and after each test.
    
    This ensures test isolation - no test can affect another by
    leaving workflows registered.
    """
    clear_workflow_registry()
    yield
    clear_workflow_registry()


@pytest.fixture
def clean_operation_registry_fixture() -> Generator[None, None, None]:
    """
    Clear operation registry before and after test.
    
    Not auto-applied because most tests don't modify the operation registry.
    Use explicitly when needed:
    
        def test_something(clean_operation_registry_fixture):
            ...
    """
    clear_operation_registry()
    yield
    clear_operation_registry()


# =============================================================================
# Sample Workflow Fixtures
# =============================================================================


@pytest.fixture
def simple_linear_workflow() -> Workflow:
    """
    Simple linear workflow: A -> B -> C.
    
    Useful for testing basic execution order.
    """
    return Workflow(
        name="test.simple_linear",
        domain="test",
        description="Simple linear workflow for testing",
        version=1,
        steps=[
            Step.operation("step_a", "operation.a"),
            Step.operation("step_b", "operation.b", depends_on=["step_a"]),
            Step.operation("step_c", "operation.c", depends_on=["step_b"]),
        ],
    )


@pytest.fixture
def diamond_dependency_workflow() -> Workflow:
    """
    Diamond dependency pattern:
        A
       / \\
      B   C
       \\ /
        D
    
    Useful for testing DAG resolution with multiple paths.
    """
    return Workflow(
        name="test.diamond",
        domain="test",
        description="Diamond dependency pattern",
        version=1,
        steps=[
            Step.operation("step_a", "operation.a"),
            Step.operation("step_b", "operation.b", depends_on=["step_a"]),
            Step.operation("step_c", "operation.c", depends_on=["step_a"]),
            Step.operation("step_d", "operation.d", depends_on=["step_b", "step_c"]),
        ],
    )


@pytest.fixture
def parallel_independent_workflow() -> Workflow:
    """
    Workflow with independent steps (no dependencies).
    
    All steps can run in parallel.
    """
    return Workflow(
        name="test.parallel",
        domain="test",
        description="Independent parallel steps",
        version=1,
        steps=[
            Step.operation("step_a", "operation.a"),
            Step.operation("step_b", "operation.b"),
            Step.operation("step_c", "operation.c"),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL, max_concurrency=3,
        ),
    )


@pytest.fixture
def workflow_with_defaults() -> Workflow:
    """
    Workflow with default parameters.
    
    Useful for testing parameter precedence.
    """
    return Workflow(
        name="test.defaults",
        domain="test",
        description="Workflow with default parameters",
        version=1,
        defaults={
            "tier": "NMS_TIER_1",
            "force": False,
            "week_ending": "2026-01-03",
        },
        steps=[
            Step.operation("ingest", "operation.ingest"),
            Step.operation(
                "normalize",
                "operation.normalize",
                depends_on=["ingest"],
            ),
        ],
    )


@pytest.fixture
def complex_workflow() -> Workflow:
    """
    Complex workflow mimicking real-world FINRA workflow.
    
    Useful for integration tests.
    """
    return Workflow(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        description="Weekly FINRA data refresh workflow",
        version=1,
        defaults={"tier": "NMS_TIER_1"},
        steps=[
            Step.operation("ingest", "finra.otc_transparency.ingest_week"),
            Step.operation(
                "normalize",
                "finra.otc_transparency.normalize_week",
                depends_on=["ingest"],
            ),
            Step.operation(
                "aggregate",
                "finra.otc_transparency.aggregate_week",
                depends_on=["normalize"],
            ),
            Step.operation(
                "rolling",
                "finra.otc_transparency.compute_rolling",
                depends_on=["aggregate"],
            ),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
            on_failure=FailurePolicy.STOP,
        ),
    )


# =============================================================================
# Temporary Directory Utilities
# =============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for test files.
    
    Automatically cleaned up after test.
    """
    with tempfile.TemporaryDirectory(prefix="spine_test_") as tmpdir:
        yield Path(tmpdir)


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
    Factory fixture for creating Step instances.
    
    Usage:
        def test_something(make_step):
            step = make_step("my_step", "my.workflow", depends_on=["other"])
    """
    def _make_step(
        name: str,
        operation_name: str,
        depends_on: list[str] | None = None,
    ) -> Step:
        return Step.operation(
            name=name,
            operation_name=operation_name,
            depends_on=depends_on or [],
        )
    
    return _make_step


@pytest.fixture
def make_workflow(make_step):
    """
    Factory fixture for creating Workflow instances.
    
    Usage:
        def test_something(make_workflow):
            workflow = make_workflow("test.workflow", steps=[...])
    """
    def _make_workflow(
        name: str,
        steps: list[Step] | None = None,
        domain: str = "test",
        defaults: dict[str, Any] | None = None,
        execution_policy: WorkflowExecutionPolicy | None = None,
    ) -> Workflow:
        if steps is None:
            steps = [make_step("default_step", "workflow.default")]
        
        return Workflow(
            name=name,
            domain=domain,
            steps=steps,
            defaults=defaults or {},
            execution_policy=execution_policy or WorkflowExecutionPolicy(),
        )
    
    return _make_workflow
