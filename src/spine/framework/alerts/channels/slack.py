"""Slack webhook alert channel."""

from __future__ import annotations

from typing import Any

from spine.core.errors import TransientError
from spine.framework.alerts.base import BaseChannel
from spine.framework.alerts.protocol import (
    Alert,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)


class SlackChannel(BaseChannel):
    """
    Slack webhook channel.

    Sends alerts to Slack via incoming webhooks.
    """

    def __init__(
        self,
        name: str,
        webhook_url: str,
        *,
        channel: str | None = None,
        username: str = "Spine Alerts",
        icon_emoji: str = ":warning:",
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        **kwargs: Any,
    ):
        super().__init__(name, ChannelType.SLACK, min_severity=min_severity, **kwargs)
        self._webhook_url = webhook_url
        self._channel = channel
        self._username = username
        self._icon_emoji = icon_emoji

    def _build_payload(self, alert: Alert) -> dict[str, Any]:
        """Build Slack message payload."""
        severity_emoji = {
            AlertSeverity.INFO: ":information_source:",
            AlertSeverity.WARNING: ":warning:",
            AlertSeverity.ERROR: ":x:",
            AlertSeverity.CRITICAL: ":rotating_light:",
        }

        severity_color = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#daa038",
            AlertSeverity.ERROR: "#d63f3f",
            AlertSeverity.CRITICAL: "#8b0000",
        }

        fields = [
            {"title": "Source", "value": alert.source, "short": True},
            {"title": "Severity", "value": alert.severity.value, "short": True},
        ]

        if alert.domain:
            fields.append({"title": "Domain", "value": alert.domain, "short": True})

        if alert.execution_id:
            fields.append({"title": "Execution", "value": alert.execution_id, "short": True})

        attachment = {
            "color": severity_color.get(alert.severity, "#808080"),
            "title": f"{severity_emoji.get(alert.severity, '')} {alert.title}",
            "text": alert.message,
            "fields": fields,
            "ts": int(alert.created_at.timestamp()),
        }

        payload = {
            "username": self._username,
            "icon_emoji": self._icon_emoji,
            "attachments": [attachment],
        }

        if self._channel:
            payload["channel"] = self._channel

        return payload

    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert to Slack."""
        import json
        import urllib.error
        import urllib.request

        payload = self._build_payload(alert)

        try:
            req = urllib.request.Request(
                self._webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                return DeliveryResult.ok(self._name, message=response.read().decode())

        except urllib.error.URLError as e:
            return DeliveryResult.fail(self._name, TransientError(str(e), cause=e))
        except Exception as e:
            return DeliveryResult.fail(self._name, e)
