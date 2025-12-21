"""Tests for CeleryExecutor.

Tests cover:
- Initialization (with and without celery installed)
- Submit with priority/lane routing
- Cancel, get_status, get_result
- Queue routing logic
- Priority value mapping
"""

from unittest.mock import MagicMock, patch

import pytest

from spine.execution.spec import WorkSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_spec(**overrides) -> WorkSpec:
    defaults = dict(kind="task", name="test_handler", params={"x": 1})
    defaults.update(overrides)
    return WorkSpec(**defaults)


@pytest.fixture
def mock_celery_app():
    """Create a mock Celery app with all required methods."""
    app = MagicMock()
    app.signature.return_value = MagicMock()
    app.signature.return_value.set.return_value = app.signature.return_value
    app.signature.return_value.apply_async.return_value = MagicMock(id="celery-task-id-123")
    app.control = MagicMock()
    return app


@pytest.fixture
def mock_async_result():
    """Create a mock AsyncResult."""
    result = MagicMock()
    result.state = "SUCCESS"
    result.ready.return_value = True
    result.result = {"output": "done"}
    result.id = "celery-task-id-123"
    return result


# ---------------------------------------------------------------------------
# Test: Initialization
# ---------------------------------------------------------------------------


class TestCeleryExecutorInit:
    """Tests for CeleryExecutor initialization."""

    def test_init_with_celery_available(self, mock_celery_app):
        """CeleryExecutor initializes when celery is installed."""
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                executor = CeleryExecutor(mock_celery_app)

        assert executor.name == "celery"
        assert executor.celery_app is mock_celery_app

    def test_init_without_celery_raises(self, mock_celery_app):
        """CeleryExecutor raises RuntimeError when celery not installed."""
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", False):
            from spine.execution.executors.celery import CeleryExecutor

            with pytest.raises(RuntimeError, match="Celery not installed"):
                CeleryExecutor(mock_celery_app)

    def test_name_property(self, mock_celery_app):
        """name property returns 'celery'."""
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                executor = CeleryExecutor(mock_celery_app)

        assert executor.name == "celery"


# ---------------------------------------------------------------------------
# Test: Submit
# ---------------------------------------------------------------------------


class TestCeleryExecutorSubmit:
    """Tests for CeleryExecutor.submit()."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, mock_celery_app):
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                self.executor = CeleryExecutor(mock_celery_app)
        self.app = mock_celery_app

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self):
        """submit() returns the Celery task_id."""
        spec = _make_spec()
        result = await self.executor.submit(spec)
        assert result == "celery-task-id-123"

    @pytest.mark.asyncio
    async def test_submit_creates_correct_task_name(self):
        """submit() uses spine.execute.{kind} naming convention."""
        spec = _make_spec(kind="operation")
        await self.executor.submit(spec)

        self.app.signature.assert_called_once()
        call_args = self.app.signature.call_args
        assert call_args[0][0] == "spine.execute.operation"

    @pytest.mark.asyncio
    async def test_submit_passes_params(self):
        """submit() passes spec params to Celery signature."""
        spec = _make_spec(params={"to": "user@test.com"})
        await self.executor.submit(spec)

        call_args = self.app.signature.call_args
        # signature(task_name, args=[name, params], ...)
        assert call_args[1]["args"] == ["test_handler", {"to": "user@test.com"}]

    @pytest.mark.asyncio
    async def test_submit_passes_metadata_kwargs(self):
        """submit() passes idempotency_key, correlation_id, etc."""
        spec = _make_spec(
            idempotency_key="idem-123",
            correlation_id="corr-456",
            parent_run_id="parent-789",
        )
        await self.executor.submit(spec)

        call_kwargs = self.app.signature.call_args[1]
        assert call_kwargs["kwargs"]["idempotency_key"] == "idem-123"
        assert call_kwargs["kwargs"]["correlation_id"] == "corr-456"
        assert call_kwargs["kwargs"]["parent_run_id"] == "parent-789"

    @pytest.mark.asyncio
    async def test_submit_with_lane_routing(self):
        """submit() routes to lane queue when lane != 'default'."""
        spec = _make_spec(lane="gpu")
        await self.executor.submit(spec)

        call_kwargs = self.app.signature.call_args[1]
        assert call_kwargs["queue"] == "gpu"

    @pytest.mark.asyncio
    async def test_submit_with_priority_routing(self):
        """submit() routes to priority queue when lane is default."""
        spec = _make_spec(priority="high")
        await self.executor.submit(spec)

        call_kwargs = self.app.signature.call_args[1]
        assert call_kwargs["queue"] == "high"
        assert call_kwargs["priority"] == 7

    @pytest.mark.asyncio
    async def test_submit_with_retries(self):
        """submit() applies retry policy when max_retries > 0."""
        spec = _make_spec(max_retries=3, retry_delay_seconds=5)
        await self.executor.submit(spec)

        sig = self.app.signature.return_value
        sig.set.assert_called_once()
        retry_args = sig.set.call_args[1]
        assert retry_args["retry"] is True
        assert retry_args["retry_policy"]["max_retries"] == 3
        assert retry_args["retry_policy"]["interval_start"] == 5

    @pytest.mark.asyncio
    async def test_submit_without_retries_skips_set(self):
        """submit() does not call .set() when max_retries is 0."""
        spec = _make_spec(max_retries=0)
        await self.executor.submit(spec)

        sig = self.app.signature.return_value
        sig.set.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Cancel
# ---------------------------------------------------------------------------


class TestCeleryExecutorCancel:
    """Tests for CeleryExecutor.cancel()."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, mock_celery_app):
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                self.executor = CeleryExecutor(mock_celery_app)
        self.app = mock_celery_app

    @pytest.mark.asyncio
    async def test_cancel_revokes_task(self):
        """cancel() calls control.revoke with terminate=True."""
        result = await self.executor.cancel("task-id-123")
        assert result is True
        self.app.control.revoke.assert_called_once_with("task-id-123", terminate=True)

    @pytest.mark.asyncio
    async def test_cancel_returns_false_on_error(self):
        """cancel() returns False if revoke raises."""
        self.app.control.revoke.side_effect = Exception("connection lost")
        result = await self.executor.cancel("task-id-123")
        assert result is False


# ---------------------------------------------------------------------------
# Test: Status
# ---------------------------------------------------------------------------


class TestCeleryExecutorStatus:
    """Tests for CeleryExecutor.get_status()."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, mock_celery_app):
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                self.executor = CeleryExecutor(mock_celery_app)
        self.app = mock_celery_app

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "celery_state,expected",
        [
            ("PENDING", "queued"),
            ("RECEIVED", "queued"),
            ("STARTED", "running"),
            ("SUCCESS", "completed"),
            ("FAILURE", "failed"),
            ("REVOKED", "cancelled"),
            ("REJECTED", "failed"),
            ("RETRY", "queued"),
        ],
    )
    async def test_status_mapping(self, celery_state, expected):
        """get_status() maps Celery states correctly."""
        with patch("spine.execution.executors.celery.AsyncResult") as MockResult:
            mock_result = MagicMock()
            mock_result.state = celery_state
            MockResult.return_value = mock_result

            status = await self.executor.get_status("ref-123")
            assert status == expected

    @pytest.mark.asyncio
    async def test_status_unknown_state_lowercased(self):
        """get_status() lowercases unknown Celery states."""
        with patch("spine.execution.executors.celery.AsyncResult") as MockResult:
            mock_result = MagicMock()
            mock_result.state = "CUSTOM_STATE"
            MockResult.return_value = mock_result

            status = await self.executor.get_status("ref-123")
            assert status == "custom_state"

    @pytest.mark.asyncio
    async def test_status_none_state(self):
        """get_status() returns None if state is None."""
        with patch("spine.execution.executors.celery.AsyncResult") as MockResult:
            mock_result = MagicMock()
            mock_result.state = None
            MockResult.return_value = mock_result

            status = await self.executor.get_status("ref-123")
            assert status is None


# ---------------------------------------------------------------------------
# Test: Get Result
# ---------------------------------------------------------------------------


class TestCeleryExecutorResult:
    """Tests for CeleryExecutor.get_result()."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, mock_celery_app):
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                self.executor = CeleryExecutor(mock_celery_app)
        self.app = mock_celery_app

    @pytest.mark.asyncio
    async def test_get_result_when_ready(self):
        """get_result() returns result when task is ready."""
        with patch("spine.execution.executors.celery.AsyncResult") as MockResult:
            mock_result = MagicMock()
            mock_result.ready.return_value = True
            mock_result.result = {"data": "success"}
            MockResult.return_value = mock_result

            result = await self.executor.get_result("ref-123")
            assert result == {"data": "success"}

    @pytest.mark.asyncio
    async def test_get_result_when_not_ready(self):
        """get_result() returns None when task is not ready."""
        with patch("spine.execution.executors.celery.AsyncResult") as MockResult:
            mock_result = MagicMock()
            mock_result.ready.return_value = False
            MockResult.return_value = mock_result

            result = await self.executor.get_result("ref-123")
            assert result is None


# ---------------------------------------------------------------------------
# Test: Queue Routing
# ---------------------------------------------------------------------------


class TestQueueRouting:
    """Tests for _get_queue and _get_priority_value."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, mock_celery_app):
        with patch("spine.execution.executors.celery.CELERY_AVAILABLE", True):
            with pytest.warns(match="EXPERIMENTAL"):
                from spine.execution.executors.celery import CeleryExecutor

                self.executor = CeleryExecutor(mock_celery_app)

    @pytest.mark.parametrize(
        "lane,priority,expected_queue",
        [
            ("gpu", "normal", "gpu"),
            ("cpu", "high", "cpu"),
            ("io-bound", "low", "io-bound"),
            ("default", "realtime", "realtime"),
            ("default", "high", "high"),
            ("default", "normal", "default"),
            ("default", "low", "low"),
            ("default", "slow", "slow"),
        ],
    )
    def test_queue_routing(self, lane, priority, expected_queue):
        """_get_queue routes correctly based on lane and priority."""
        spec = _make_spec(lane=lane, priority=priority)
        assert self.executor._get_queue(spec) == expected_queue

    def test_unknown_priority_defaults_to_default_queue(self):
        """_get_queue returns 'default' for unknown priorities."""
        spec = _make_spec(priority="unknown")
        assert self.executor._get_queue(spec) == "default"

    @pytest.mark.parametrize(
        "priority,expected_value",
        [
            ("realtime", 9),
            ("high", 7),
            ("normal", 5),
            ("low", 3),
            ("slow", 1),
        ],
    )
    def test_priority_values(self, priority, expected_value):
        """_get_priority_value maps correctly."""
        assert self.executor._get_priority_value(priority) == expected_value

    def test_unknown_priority_defaults_to_5(self):
        """_get_priority_value returns 5 for unknown priorities."""
        assert self.executor._get_priority_value("unknown") == 5
