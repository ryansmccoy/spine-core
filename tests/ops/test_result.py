"""Tests for spine.ops.result — OperationResult and PagedResult."""

from spine.ops.result import OperationError, OperationResult, PagedResult, start_timer
from spine.core.errors import ErrorCategory


# =====================================================================
# OperationResult.ok
# =====================================================================


class TestOperationResultOk:
    def test_ok_basic(self):
        r = OperationResult.ok("hello")
        assert r.success is True
        assert r.data == "hello"
        assert r.error is None
        assert r.warnings == []

    def test_ok_with_warnings(self):
        r = OperationResult.ok(42, warnings=["heads up"])
        assert r.success is True
        assert r.data == 42
        assert r.warnings == ["heads up"]

    def test_ok_with_metadata(self):
        r = OperationResult.ok([], metadata={"source": "test"})
        assert r.metadata == {"source": "test"}

    def test_ok_with_elapsed(self):
        r = OperationResult.ok(None, elapsed_ms=12.5)
        assert r.elapsed_ms == 12.5


# =====================================================================
# OperationResult.fail
# =====================================================================


class TestOperationResultFail:
    def test_fail_basic(self):
        r = OperationResult.fail("NOT_FOUND", "Item not found")
        assert r.success is False
        assert r.data is None
        assert r.error is not None
        assert r.error.code == "NOT_FOUND"
        assert r.error.message == "Item not found"
        assert r.error.retryable is False

    def test_fail_with_category(self):
        r = OperationResult.fail(
            "TRANSIENT", "Retry later", category=ErrorCategory.NETWORK, retryable=True
        )
        assert r.error.category == ErrorCategory.NETWORK
        assert r.error.retryable is True

    def test_fail_with_details(self):
        r = OperationResult.fail("VALIDATION_FAILED", "Bad input", details={"field": "name"})
        assert r.error.details == {"field": "name"}

    def test_fail_with_warnings(self):
        r = OperationResult.fail("INTERNAL", "oops", warnings=["also this"])
        assert r.warnings == ["also this"]


# =====================================================================
# OperationResult.to_dict
# =====================================================================


class TestOperationResultToDict:
    def test_ok_to_dict(self):
        d = OperationResult.ok("v").to_dict()
        assert d["success"] is True
        assert d["data"] == "v"
        assert "error" not in d

    def test_fail_to_dict(self):
        d = OperationResult.fail("X", "msg").to_dict()
        assert d["success"] is False
        assert d["error"]["code"] == "X"
        assert d["error"]["message"] == "msg"
        assert "data" not in d

    def test_to_dict_includes_warnings(self):
        d = OperationResult.ok(1, warnings=["w"]).to_dict()
        assert d["warnings"] == ["w"]

    def test_to_dict_includes_elapsed(self):
        d = OperationResult.ok(1, elapsed_ms=5.0).to_dict()
        assert d["elapsed_ms"] == 5.0

    def test_to_dict_includes_metadata(self):
        d = OperationResult.ok(1, metadata={"k": "v"}).to_dict()
        assert d["metadata"] == {"k": "v"}


# =====================================================================
# OperationError
# =====================================================================


class TestOperationError:
    def test_frozen(self):
        err = OperationError(code="X", message="m")
        # frozen=True means assignment raises
        try:
            err.code = "Y"  # type: ignore[misc]
            assert False, "Expected FrozenInstanceError"
        except AttributeError:
            pass

    def test_defaults(self):
        err = OperationError(code="A", message="B")
        assert err.category is None
        assert err.details == {}
        assert err.retryable is False


# =====================================================================
# PagedResult
# =====================================================================


class TestPagedResult:
    def test_from_items_basic(self):
        pr = PagedResult.from_items(["a", "b"], total=5, limit=2, offset=0)
        assert pr.success is True
        assert pr.data == ["a", "b"]
        assert pr.total == 5
        assert pr.limit == 2
        assert pr.offset == 0
        assert pr.has_more is True

    def test_from_items_no_more(self):
        pr = PagedResult.from_items(["a"], total=1, limit=50, offset=0)
        assert pr.has_more is False

    def test_from_items_last_page(self):
        pr = PagedResult.from_items(["c"], total=3, limit=1, offset=2)
        assert pr.has_more is False

    def test_to_dict_includes_pagination(self):
        pr = PagedResult.from_items([], total=0)
        d = pr.to_dict()
        assert d["total"] == 0
        assert d["limit"] == 50
        assert d["offset"] == 0
        assert d["has_more"] is False


# =====================================================================
# Timer
# =====================================================================


class TestTimer:
    def test_timer_returns_positive(self):
        t = start_timer()
        assert t.elapsed_ms >= 0
