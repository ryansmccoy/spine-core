"""Tests for spine.ops.context — OperationContext."""

from spine.ops.context import OperationContext


class TestOperationContext:
    def test_defaults(self, mock_conn):
        ctx = OperationContext(conn=mock_conn)
        assert ctx.caller == "sdk"
        assert ctx.user is None
        assert ctx.dry_run is False
        assert ctx.metadata == {}
        assert ctx.request_id  # auto-generated UUID

    def test_custom_fields(self, mock_conn):
        ctx = OperationContext(
            conn=mock_conn,
            caller="api",
            user="admin",
            dry_run=True,
            metadata={"trace": "abc"},
        )
        assert ctx.caller == "api"
        assert ctx.user == "admin"
        assert ctx.dry_run is True
        assert ctx.metadata["trace"] == "abc"

    def test_request_id_unique(self, mock_conn):
        c1 = OperationContext(conn=mock_conn)
        c2 = OperationContext(conn=mock_conn)
        assert c1.request_id != c2.request_id
