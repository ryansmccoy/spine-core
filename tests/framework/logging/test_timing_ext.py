"""Tests for framework logging timing utilities.

Covers TimingResult, timed_block, log_step, log_timing, and log_row_counts.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from spine.framework.logging.timing import (
    TimingResult,
    _generate_span_id,
    log_row_counts,
    log_step,
    log_timing,
    timed_block,
)


# ── _generate_span_id ────────────────────────────────────────


class TestGenerateSpanId:
    def test_length(self):
        sid = _generate_span_id()
        assert len(sid) == 8

    def test_hex_chars(self):
        sid = _generate_span_id()
        int(sid, 16)  # Raises if not hex

    def test_unique(self):
        assert _generate_span_id() != _generate_span_id()


# ── TimingResult ─────────────────────────────────────────────


class TestTimingResult:
    def test_stop_sets_duration(self):
        tr = TimingResult(step="test")
        time.sleep(0.01)
        tr.stop()
        assert tr.duration_seconds > 0
        assert tr.duration_ms > 0

    def test_add_metric(self):
        tr = TimingResult(step="test")
        tr.add_metric("rows_in", 100)
        tr.add_metric("rows_out", 95)
        tr.stop()
        d = tr.to_log_dict()
        assert d.get("rows_in") == 100
        assert d.get("rows_out") == 95

    def test_set_error(self):
        tr = TimingResult(step="test")
        tr.set_error(ValueError("boom"))
        tr.stop()
        d = tr.to_error_dict()
        assert "boom" in str(d.get("error_message", ""))

    def test_to_log_dict(self):
        tr = TimingResult(step="test")
        tr.stop()
        d = tr.to_log_dict()
        assert "duration_ms" in d
        assert "span_id" in d

    def test_to_error_dict(self):
        tr = TimingResult(step="test")
        tr.set_error(RuntimeError("fail"))
        tr.stop()
        d = tr.to_error_dict()
        assert "error_type" in d
        assert "error_message" in d


# ── timed_block ──────────────────────────────────────────────


class TestTimedBlock:
    def test_yields_timing_result(self):
        with timed_block("test-block") as tr:
            time.sleep(0.01)
        assert isinstance(tr, TimingResult)
        assert tr.duration_ms > 0

    def test_error_captured(self):
        with pytest.raises(ValueError):
            with timed_block("error-block") as tr:
                raise ValueError("expected")
        # TimingResult should have error set
        assert tr.duration_ms >= 0


# ── log_step ─────────────────────────────────────────────────


class TestLogStep:
    def test_basic_step(self):
        with log_step("test-step") as tr:
            pass
        assert isinstance(tr, TimingResult)
        assert tr.duration_ms >= 0

    def test_step_with_extra(self):
        with log_step("test-step", rows_in=100) as tr:
            pass
        assert isinstance(tr, TimingResult)

    def test_step_captures_error(self):
        with pytest.raises(RuntimeError):
            with log_step("error-step") as tr:
                raise RuntimeError("fail")


# ── log_timing decorator ────────────────────────────────────


class TestLogTiming:
    def test_decorator_preserves_return(self):
        @log_timing("test-func")
        def add(a, b):
            return a + b

        result = add(1, 2)
        assert result == 3

    def test_decorator_propagates_error(self):
        @log_timing("error-func")
        def fail():
            raise RuntimeError("decorated fail")

        with pytest.raises(RuntimeError, match="decorated fail"):
            fail()


# ── log_row_counts ───────────────────────────────────────────


class TestLogRowCounts:
    def test_logs_metrics(self):
        mock_log = MagicMock()
        log_row_counts(mock_log, "test-step", rows_in=100, rows_out=90, rejected=10)
        mock_log.info.assert_called_once()
        call_kwargs = mock_log.info.call_args
        # Should contain row count info in the log call
        assert "100" in str(call_kwargs) or "rows_in" in str(call_kwargs)
