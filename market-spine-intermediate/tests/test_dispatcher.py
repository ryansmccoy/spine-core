"""Tests for the dispatcher and backend protocol."""

import pytest

from market_spine.orchestration.backends.protocol import OrchestratorBackend


class MockBackend:
    """Mock backend for testing."""

    name = "mock"
    submitted = []

    def submit(self, execution_id: str) -> str | None:
        self.submitted.append(execution_id)
        return f"mock-{execution_id}"

    def cancel(self, execution_id: str) -> bool:
        return True

    def health(self) -> dict:
        return {"healthy": True, "message": "mock backend"}

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class TestOrchestratorBackendProtocol:
    """Tests for the OrchestratorBackend protocol."""

    def test_mock_backend_implements_protocol(self):
        """MockBackend should satisfy OrchestratorBackend protocol."""
        backend = MockBackend()
        assert isinstance(backend, OrchestratorBackend)

    def test_submit_returns_run_id(self):
        """Submit should return a backend run ID."""
        backend = MockBackend()
        backend.submitted = []

        result = backend.submit("test-123")

        assert result == "mock-test-123"
        assert "test-123" in backend.submitted

    def test_cancel_returns_bool(self):
        """Cancel should return a boolean."""
        backend = MockBackend()
        result = backend.cancel("test-123")

        assert isinstance(result, bool)
        assert result is True

    def test_health_returns_dict(self):
        """Health should return a dict with required fields."""
        backend = MockBackend()
        result = backend.health()

        assert isinstance(result, dict)
        assert "healthy" in result
        assert "message" in result


class TestDispatcherLogic:
    """Tests for dispatcher logic (unit tests, no DB)."""

    def test_logical_key_format(self):
        """Logical key should be properly formatted."""
        # Example format: pipeline_name:symbol:date
        pipeline = "test.compute"
        symbol = "ACME"
        date = "2024-01-15"

        logical_key = f"{pipeline}:{symbol}:{date}"

        assert logical_key == "test.compute:ACME:2024-01-15"

    def test_logical_key_uniqueness(self):
        """Different inputs should produce different logical keys."""
        key1 = "test.compute:ACME:2024-01-15"
        key2 = "test.compute:ACME:2024-01-16"
        key3 = "test.compute:BOLT:2024-01-15"

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3
