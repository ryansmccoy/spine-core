"""Tests for alert channels: email, slack, webhook.

Uses mocking to avoid real network calls. Covers:
- Init and properties
- Message/payload building
- send() success and failure paths
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spine.framework.alerts.channels.email import EmailChannel
from spine.framework.alerts.channels.slack import SlackChannel
from spine.framework.alerts.channels.webhook import WebhookChannel
from spine.framework.alerts.protocol import Alert, AlertSeverity, ChannelType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alert(**overrides) -> Alert:
    defaults = dict(
        severity=AlertSeverity.ERROR,
        title="Something broke",
        message="Details about the failure",
        source="test_operation",
        domain="sec",
        execution_id="exec-123",
        created_at=datetime(2026, 1, 15, 12, 0, 0),
    )
    defaults.update(overrides)
    return Alert(**defaults)


# ===========================================================================
# Email
# ===========================================================================


class TestEmailChannel:
    def test_init(self):
        ch = EmailChannel(
            name="email_alerts",
            smtp_host="smtp.example.com",
            from_address="alerts@example.com",
            recipients=["dev@example.com"],
        )
        assert ch.name == "email_alerts"
        assert ch.channel_type == ChannelType.EMAIL

    def test_build_message(self):
        ch = EmailChannel(
            name="em",
            smtp_host="localhost",
            from_address="a@b.com",
            recipients=["x@y.com"],
        )
        msg = ch._build_message(_alert())
        assert "[ERROR]" in msg
        assert "Something broke" in msg
        assert "a@b.com" in msg

    @patch("smtplib.SMTP")
    def test_send_success(self, MockSMTP):
        mock_server = MagicMock()
        MockSMTP.return_value = mock_server

        ch = EmailChannel(
            name="em",
            smtp_host="smtp.example.com",
            from_address="a@b.com",
            recipients=["x@y.com"],
            smtp_user="user",
            smtp_password="pass",
        )
        result = ch.send(_alert())
        assert result.success is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_send_no_tls(self, MockSMTP):
        mock_server = MagicMock()
        MockSMTP.return_value = mock_server

        ch = EmailChannel(
            name="em",
            smtp_host="localhost",
            from_address="a@b.com",
            recipients=["x@y.com"],
            use_tls=False,
        )
        result = ch.send(_alert())
        assert result.success is True
        mock_server.starttls.assert_not_called()

    @patch("smtplib.SMTP")
    def test_send_smtp_error(self, MockSMTP):
        import smtplib

        mock_server = MagicMock()
        mock_server.sendmail.side_effect = smtplib.SMTPException("nope")
        MockSMTP.return_value = mock_server

        ch = EmailChannel(
            name="em",
            smtp_host="localhost",
            from_address="a@b.com",
            recipients=["x@y.com"],
        )
        result = ch.send(_alert())
        assert result.success is False

    @patch("smtplib.SMTP")
    def test_send_generic_error(self, MockSMTP):
        MockSMTP.side_effect = OSError("connection refused")
        ch = EmailChannel(
            name="em",
            smtp_host="localhost",
            from_address="a@b.com",
            recipients=["x@y.com"],
        )
        result = ch.send(_alert())
        assert result.success is False


# ===========================================================================
# Slack
# ===========================================================================


class TestSlackChannel:
    def test_init(self):
        ch = SlackChannel(name="slack", webhook_url="https://hooks.slack.com/x")
        assert ch.name == "slack"
        assert ch.channel_type == ChannelType.SLACK

    def test_build_payload(self):
        ch = SlackChannel(
            name="slack",
            webhook_url="https://hooks.slack.com/x",
            channel="#alerts",
        )
        payload = ch._build_payload(_alert())
        assert payload["channel"] == "#alerts"
        assert len(payload["attachments"]) == 1
        assert "Something broke" in payload["attachments"][0]["title"]

    def test_build_payload_no_channel(self):
        ch = SlackChannel(name="slack", webhook_url="https://hooks.slack.com/x")
        payload = ch._build_payload(_alert())
        assert "channel" not in payload

    @patch("urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"ok"
        mock_urlopen.return_value = mock_response

        ch = SlackChannel(name="slack", webhook_url="https://hooks.slack.com/x")
        result = ch.send(_alert())
        assert result.success is True

    @patch("urllib.request.urlopen")
    def test_send_url_error(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("refused")
        ch = SlackChannel(name="slack", webhook_url="https://hooks.slack.com/x")
        result = ch.send(_alert())
        assert result.success is False

    @patch("urllib.request.urlopen")
    def test_send_generic_error(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("kaboom")
        ch = SlackChannel(name="slack", webhook_url="https://hooks.slack.com/x")
        result = ch.send(_alert())
        assert result.success is False


# ===========================================================================
# Webhook
# ===========================================================================


class TestWebhookChannel:
    def test_init(self):
        ch = WebhookChannel(name="wh", url="https://example.com/hook")
        assert ch.name == "wh"
        assert ch.channel_type == ChannelType.WEBHOOK

    def test_init_with_headers(self):
        ch = WebhookChannel(
            name="wh",
            url="https://example.com/hook",
            headers={"Authorization": "Bearer xyz"},
        )
        assert ch._headers == {"Authorization": "Bearer xyz"}

    @patch("urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        ch = WebhookChannel(name="wh", url="https://example.com/hook")
        result = ch.send(_alert())
        assert result.success is True

    @patch("urllib.request.urlopen")
    def test_send_url_error(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("refused")
        ch = WebhookChannel(name="wh", url="https://example.com/hook")
        result = ch.send(_alert())
        assert result.success is False

    @patch("urllib.request.urlopen")
    def test_send_generic_error(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("kaboom")
        ch = WebhookChannel(name="wh", url="https://example.com/hook")
        result = ch.send(_alert())
        assert result.success is False
