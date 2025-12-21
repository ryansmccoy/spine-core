"""Tests for ``spine.ops.webhooks`` — webhook registry operations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spine.ops.webhooks import (
    WebhookTarget,
    clear_webhooks,
    dispatch_webhook,
    get_webhook_target,
    list_registered_webhooks,
    register_webhook,
)


class TestWebhookRegistry:
    def setup_method(self):
        clear_webhooks()

    def teardown_method(self):
        clear_webhooks()

    def test_register_and_list(self):
        register_webhook("wf-1", kind="workflow", description="Test wf")
        targets = list_registered_webhooks()
        assert len(targets) == 1
        assert targets[0].name == "wf-1"
        assert targets[0].kind == "workflow"

    def test_register_operation(self):
        register_webhook("op-1", kind="operation", description="Test op")
        t = get_webhook_target("op-1")
        assert t is not None
        assert t.kind == "operation"

    def test_get_missing_returns_none(self):
        assert get_webhook_target("nope") is None

    def test_clear(self):
        register_webhook("wf-1")
        clear_webhooks()
        assert list_registered_webhooks() == []

    def test_overwrite(self):
        register_webhook("wf-1", description="v1")
        register_webhook("wf-1", description="v2")
        t = get_webhook_target("wf-1")
        assert t.description == "v2"


class TestDispatchWebhook:
    @pytest.mark.asyncio
    async def test_dispatch_workflow(self):
        dispatcher = AsyncMock()
        dispatcher.submit.return_value = "run-123"

        run_id = await dispatch_webhook(
            dispatcher=dispatcher,
            name="my-wf",
            kind="workflow",
            params={"key": "val"},
        )
        assert run_id == "run-123"
        dispatcher.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_operation(self):
        dispatcher = AsyncMock()
        dispatcher.submit.return_value = "run-456"

        run_id = await dispatch_webhook(
            dispatcher=dispatcher,
            name="my-op",
            kind="operation",
            params={},
        )
        assert run_id == "run-456"


class TestWebhookTargetDataclass:
    def test_defaults(self):
        t = WebhookTarget()
        assert t.name == ""
        assert t.kind == "workflow"
        assert t.description == ""
