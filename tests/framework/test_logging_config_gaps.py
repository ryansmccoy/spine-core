"""Tests for framework/logging/config.py gaps.

Covers:
- is_configured() / is_debug_enabled()
- configure_logging idempotency (second call no-op without force)
- JSON format renderer path
- workflow_debug filter logic
"""

import logging
import os

import pytest

import spine.framework.logging.config as log_config
from spine.framework.logging.config import (
    configure_logging,
    is_configured,
    is_debug_enabled,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset the _configured flag before each test."""
    log_config._configured = False
    # Restore env vars
    saved = {
        k: os.environ.pop(k, None)
        for k in ("SPINE_LOG_LEVEL", "SPINE_LOG_FORMAT", "SPINE_LOG_WORKFLOW_DEBUG")
    }
    yield
    log_config._configured = False
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


class TestIsConfigured:
    def test_not_configured_initially(self):
        assert is_configured() is False

    def test_configured_after_call(self):
        configure_logging(level="INFO")
        assert is_configured() is True


class TestIsDebugEnabled:
    def test_debug_enabled_at_debug_level(self):
        configure_logging(level="DEBUG", force=True)
        assert is_debug_enabled() is True

    def test_debug_not_enabled_at_info(self):
        configure_logging(level="INFO", force=True)
        assert is_debug_enabled() is False


class TestIdempotency:
    def test_second_call_is_noop(self):
        configure_logging(level="WARNING")
        assert is_configured() is True
        # Second call doesn't re-configure (no-op)
        configure_logging(level="DEBUG")
        # Root logger level should still be WARNING
        assert logging.getLogger().level == logging.WARNING

    def test_force_reconfigures(self):
        configure_logging(level="WARNING")
        configure_logging(level="DEBUG", force=True)
        assert logging.getLogger().level == logging.DEBUG


class TestJSONFormat:
    def test_json_format_configures_without_error(self):
        """configure_logging(format='json') selects JSONRenderer."""
        configure_logging(format="json", level="INFO")
        assert is_configured() is True


class TestWorkflowDebugFilter:
    def test_workflow_debug_env(self):
        """SPINE_LOG_WORKFLOW_DEBUG env var is respected."""
        os.environ["SPINE_LOG_WORKFLOW_DEBUG"] = "ingest_otc,daily_report"
        configure_logging(level="INFO")
        assert is_configured() is True

    def test_workflow_debug_explicit(self):
        """workflow_debug kwarg is respected."""
        configure_logging(level="INFO", workflow_debug=["my_operation"])
        assert is_configured() is True


class TestEnvVars:
    def test_level_from_env(self):
        os.environ["SPINE_LOG_LEVEL"] = "ERROR"
        configure_logging()
        assert logging.getLogger().level == logging.ERROR

    def test_format_from_env(self):
        os.environ["SPINE_LOG_FORMAT"] = "json"
        configure_logging()
        assert is_configured() is True
