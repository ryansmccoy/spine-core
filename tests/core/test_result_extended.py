"""Extended tests for spine.core.result — utility functions and Err paths.

Covers try_result_with, collect_all_errors, partition_results,
from_optional, from_bool, and Err transformation methods.
"""

from __future__ import annotations

import pytest

from spine.core.errors import ErrorCategory, SpineError
from spine.core.result import (
    Err,
    Ok,
    collect_all_errors,
    collect_results,
    from_bool,
    from_optional,
    partition_results,
    try_result,
    try_result_with,
)


# ── try_result ───────────────────────────────────────────────────────

class TestTryResult:
    def test_success(self):
        r = try_result(lambda: 42)
        assert r.is_ok()
        assert r.unwrap() == 42

    def test_failure(self):
        r = try_result(lambda: 1 / 0)
        assert r.is_err()
        assert isinstance(r.error, ZeroDivisionError)

    def test_returns_none_ok(self):
        r = try_result(lambda: None)
        assert r.is_ok()
        assert r.unwrap() is None


# ── try_result_with ──────────────────────────────────────────────────

class TestTryResultWith:
    def test_success_no_mapper(self):
        r = try_result_with(lambda: "hello")
        assert r.unwrap() == "hello"

    def test_failure_no_mapper(self):
        r = try_result_with(lambda: 1 / 0)
        assert isinstance(r.error, ZeroDivisionError)

    def test_failure_with_mapper(self):
        r = try_result_with(
            lambda: 1 / 0,
            error_mapper=lambda e: SpineError(f"Wrapped: {e}"),
        )
        assert r.is_err()
        assert isinstance(r.error, SpineError)
        assert "Wrapped" in str(r.error)

    def test_success_ignores_mapper(self):
        mapper = lambda e: SpineError("should not be called")
        r = try_result_with(lambda: 99, error_mapper=mapper)
        assert r.unwrap() == 99


# ── collect_results ──────────────────────────────────────────────────

class TestCollectResults:
    def test_all_ok(self):
        results = [Ok(1), Ok(2), Ok(3)]
        assert collect_results(results).unwrap() == [1, 2, 3]

    def test_empty(self):
        assert collect_results([]).unwrap() == []

    def test_first_error_wins(self):
        results = [Ok(1), Err(ValueError("a")), Err(ValueError("b"))]
        r = collect_results(results)
        assert r.is_err()
        assert str(r.error) == "a"


# ── collect_all_errors ───────────────────────────────────────────────

class TestCollectAllErrors:
    def test_all_ok(self):
        results = [Ok(1), Ok(2)]
        assert collect_all_errors(results).unwrap() == [1, 2]

    def test_single_error(self):
        results = [Ok(1), Err(ValueError("x"))]
        r = collect_all_errors(results)
        assert r.is_err()
        assert isinstance(r.error, ValueError)

    def test_multiple_errors_aggregated(self):
        results = [
            Ok(1),
            Err(ValueError("err1")),
            Err(ValueError("err2")),
            Err(ValueError("err3")),
        ]
        r = collect_all_errors(results)
        assert r.is_err()
        assert isinstance(r.error, SpineError)
        assert "Multiple errors (3)" in str(r.error)
        assert r.error.context.metadata["error_count"] == 3

    def test_empty(self):
        assert collect_all_errors([]).unwrap() == []


# ── partition_results ────────────────────────────────────────────────

class TestPartitionResults:
    def test_all_ok(self):
        vals, errs = partition_results([Ok(1), Ok(2)])
        assert vals == [1, 2]
        assert errs == []

    def test_all_err(self):
        e1, e2 = ValueError("a"), ValueError("b")
        vals, errs = partition_results([Err(e1), Err(e2)])
        assert vals == []
        assert errs == [e1, e2]

    def test_mixed(self):
        vals, errs = partition_results([Ok(1), Err(ValueError("x")), Ok(3)])
        assert vals == [1, 3]
        assert len(errs) == 1

    def test_empty(self):
        vals, errs = partition_results([])
        assert vals == []
        assert errs == []


# ── from_optional ────────────────────────────────────────────────────

class TestFromOptional:
    def test_some_value(self):
        r = from_optional("hello", ValueError("no"))
        assert r.is_ok()
        assert r.unwrap() == "hello"

    def test_none_value(self):
        r = from_optional(None, ValueError("missing"))
        assert r.is_err()
        assert str(r.error) == "missing"

    def test_zero_is_not_none(self):
        r = from_optional(0, ValueError("x"))
        assert r.is_ok()
        assert r.unwrap() == 0

    def test_empty_string_is_not_none(self):
        r = from_optional("", ValueError("x"))
        assert r.is_ok()


# ── from_bool ────────────────────────────────────────────────────────

class TestFromBool:
    def test_true_returns_ok(self):
        r = from_bool(True, 42, ValueError("no"))
        assert r.is_ok()
        assert r.unwrap() == 42

    def test_false_returns_err(self):
        r = from_bool(False, 42, ValueError("failed"))
        assert r.is_err()
        assert str(r.error) == "failed"


# ── Err methods ──────────────────────────────────────────────────────

class TestErrMethods:
    def test_unwrap_raises(self):
        with pytest.raises(ValueError, match="boom"):
            Err(ValueError("boom")).unwrap()

    def test_unwrap_or(self):
        assert Err(ValueError("x")).unwrap_or(99) == 99

    def test_unwrap_or_else(self):
        r = Err(ValueError("x")).unwrap_or_else(lambda e: str(e).upper())
        assert r == "X"

    def test_map_noop(self):
        r = Err(ValueError("x")).map(lambda v: v * 2)
        assert r.is_err()

    def test_flat_map_noop(self):
        r = Err(ValueError("x")).flat_map(lambda v: Ok(v * 2))
        assert r.is_err()

    def test_map_err(self):
        r = Err(ValueError("raw")).map_err(lambda e: SpineError(f"Wrapped: {e}"))
        assert isinstance(r.error, SpineError)
        assert "Wrapped" in str(r.error)

    def test_or_else_recovery(self):
        r = Err(ValueError("x")).or_else(lambda e: Ok("recovered"))
        assert r.is_ok()
        assert r.unwrap() == "recovered"

    def test_and_then_noop(self):
        r = Err(ValueError("x")).and_then(lambda v: Ok(v * 2))
        assert r.is_err()

    def test_inspect_noop(self):
        called = []
        Err(ValueError("x")).inspect(lambda v: called.append(v))
        assert called == []

    def test_inspect_err_called(self):
        errors = []
        r = Err(ValueError("x")).inspect_err(lambda e: errors.append(e))
        assert len(errors) == 1
        assert r.is_err()

    def test_to_dict_plain_exception(self):
        d = Err(ValueError("oops")).to_dict()
        assert d["ok"] is False
        assert d["error"]["error_type"] == "ValueError"

    def test_to_dict_spine_error(self):
        e = SpineError("bad", category=ErrorCategory.VALIDATION)
        d = Err(e).to_dict()
        assert d["ok"] is False
        assert "message" in d["error"]

    def test_repr(self):
        assert "Err" in repr(Err(ValueError("x")))


# ── Ok methods (additional coverage) ────────────────────────────────

class TestOkMethods:
    def test_map(self):
        assert Ok(5).map(lambda x: x * 3).unwrap() == 15

    def test_flat_map(self):
        assert Ok(5).flat_map(lambda x: Ok(x + 1)).unwrap() == 6

    def test_map_err_noop(self):
        r = Ok(10).map_err(lambda e: SpineError("x"))
        assert r.is_ok()
        assert r.unwrap() == 10

    def test_or_else_noop(self):
        r = Ok(10).or_else(lambda e: Ok(99))
        assert r.unwrap() == 10

    def test_and_then(self):
        assert Ok(5).and_then(lambda x: Ok(x * 2)).unwrap() == 10

    def test_inspect(self):
        seen = []
        r = Ok(42).inspect(lambda x: seen.append(x))
        assert seen == [42]
        assert r.unwrap() == 42

    def test_inspect_err_noop(self):
        called = []
        Ok(1).inspect_err(lambda e: called.append(e))
        assert called == []

    def test_to_dict(self):
        d = Ok(42).to_dict()
        assert d == {"ok": True, "value": 42}

    def test_unwrap_or_returns_value(self):
        assert Ok(10).unwrap_or(99) == 10

    def test_unwrap_or_else_returns_value(self):
        assert Ok(10).unwrap_or_else(lambda e: 99) == 10

    def test_repr(self):
        assert "Ok(42)" == repr(Ok(42))
