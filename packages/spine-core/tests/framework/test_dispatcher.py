"""
Tests for spine.framework.dispatcher module.

Tests cover:
- Dispatcher initialization
- Pipeline submission
- Execution record creation
- Trigger source handling
- Lane assignment
"""

import pytest
from datetime import datetime

from spine.framework.dispatcher import (
    Dispatcher,
    Execution,
    TriggerSource,
    Lane,
)
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import register_pipeline, clear_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def dispatcher():
    """Create a fresh dispatcher instance."""
    return Dispatcher()


@pytest.fixture
def mock_pipeline():
    """Register a mock pipeline for testing."""
    @register_pipeline("test.mock")
    class MockPipeline(Pipeline):
        def run(self) -> PipelineResult:
            return PipelineResult(
                status=PipelineStatus.SUCCESS,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
    
    return MockPipeline


class TestTriggerSource:
    """Tests for TriggerSource enum."""

    def test_trigger_source_values(self):
        """Test that all trigger sources have correct values."""
        assert TriggerSource.CLI.value == "cli"
        assert TriggerSource.API.value == "api"
        assert TriggerSource.SCHEDULER.value == "scheduler"
        assert TriggerSource.RETRY.value == "retry"
        assert TriggerSource.MANUAL.value == "manual"


class TestLane:
    """Tests for Lane enum."""

    def test_lane_values(self):
        """Test that all lanes have correct values."""
        assert Lane.NORMAL.value == "normal"
        assert Lane.BACKFILL.value == "backfill"
        assert Lane.SLOW.value == "slow"


class TestExecution:
    """Tests for Execution dataclass."""

    def test_execution_creation(self):
        """Test creating an Execution record."""
        now = datetime.now()
        execution = Execution(
            id="exec-123",
            pipeline="test.pipeline",
            params={"key": "value"},
            lane=Lane.NORMAL,
            trigger_source=TriggerSource.CLI,
            logical_key="test-key",
            status=PipelineStatus.PENDING,
            created_at=now,
        )
        
        assert execution.id == "exec-123"
        assert execution.pipeline == "test.pipeline"
        assert execution.params == {"key": "value"}
        assert execution.lane == Lane.NORMAL
        assert execution.trigger_source == TriggerSource.CLI
        assert execution.logical_key == "test-key"
        assert execution.status == PipelineStatus.PENDING
        assert execution.created_at == now

    def test_execution_optional_fields(self):
        """Test Execution optional fields default to None."""
        execution = Execution(
            id="exec-456",
            pipeline="test.pipeline",
            params={},
            lane=Lane.NORMAL,
            trigger_source=TriggerSource.CLI,
            logical_key=None,
            status=PipelineStatus.PENDING,
            created_at=datetime.now(),
        )
        
        assert execution.started_at is None
        assert execution.completed_at is None
        assert execution.error is None
        assert execution.result is None


class TestDispatcherInit:
    """Tests for Dispatcher initialization."""

    def test_dispatcher_creation(self):
        """Test basic dispatcher creation."""
        dispatcher = Dispatcher()
        assert dispatcher is not None


class TestDispatcherSubmit:
    """Tests for Dispatcher.submit method."""

    def test_submit_pipeline(self, dispatcher, mock_pipeline):
        """Test submitting a pipeline for execution."""
        execution = dispatcher.submit(
            pipeline="test.mock",
            params={"week_ending": "2026-01-03"},
        )
        
        assert execution is not None
        assert execution.id is not None
        assert execution.pipeline == "test.mock"
        assert execution.params == {"week_ending": "2026-01-03"}

    def test_submit_with_lane(self, dispatcher, mock_pipeline):
        """Test submitting with specific lane."""
        execution = dispatcher.submit(
            pipeline="test.mock",
            lane=Lane.BACKFILL,
        )
        
        assert execution.lane == Lane.BACKFILL

    def test_submit_with_trigger_source(self, dispatcher, mock_pipeline):
        """Test submitting with specific trigger source."""
        execution = dispatcher.submit(
            pipeline="test.mock",
            trigger_source=TriggerSource.SCHEDULER,
        )
        
        assert execution.trigger_source == TriggerSource.SCHEDULER

    def test_submit_with_logical_key(self, dispatcher, mock_pipeline):
        """Test submitting with logical key."""
        execution = dispatcher.submit(
            pipeline="test.mock",
            logical_key="week_2026-01-03_tier_NMS",
        )
        
        assert execution.logical_key == "week_2026-01-03_tier_NMS"

    def test_submit_default_values(self, dispatcher, mock_pipeline):
        """Test that submit uses correct defaults."""
        execution = dispatcher.submit(pipeline="test.mock")
        
        assert execution.lane == Lane.NORMAL
        assert execution.trigger_source == TriggerSource.CLI
        assert execution.logical_key is None
        assert execution.params == {}

    def test_submit_generates_unique_id(self, dispatcher, mock_pipeline):
        """Test that each submission gets a unique ID."""
        exec1 = dispatcher.submit(pipeline="test.mock")
        exec2 = dispatcher.submit(pipeline="test.mock")
        
        assert exec1.id != exec2.id

    def test_submit_records_created_at(self, dispatcher, mock_pipeline):
        """Test that submission records creation time."""
        before = datetime.now()
        execution = dispatcher.submit(pipeline="test.mock")
        after = datetime.now()
        
        assert before <= execution.created_at <= after
