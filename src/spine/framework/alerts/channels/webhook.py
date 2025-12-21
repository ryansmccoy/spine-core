"""Generic webhook alert channel.

Manifesto:
    Any HTTP endpoint should be a valid alert target.  The
    generic webhook channel POSTs JSON to a user-defined URL
    so custom integrations (PagerDuty, Teams, etc.) work
    without dedicated channel code.

Tags:
    spine-core, framework, alerts, webhook, generic, HTTP-POST

Doc-Types:
    api-reference
"""

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


class WebhookChannel(BaseChannel):
    """
    Generic webhook channel.

    POSTs alert data to a URL.
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        **kwargs: Any,
    ):
        super().__init__(name, ChannelType.WEBHOOK, min_severity=min_severity, **kwargs)
        self._url = url
        self._headers = headers or {}

    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert to webhook."""
        import json
        import urllib.error
        import urllib.request

        payload = alert.to_dict()

        headers = {"Content-Type": "application/json"}
        headers.update(self._headers)

        try:
            req = urllib.request.Request(
                self._url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                return DeliveryResult.ok(
                    self._name,
                    response={"status": response.status},
                )

        except urllib.error.URLError as e:
            return DeliveryResult.fail(self._name, TransientError(str(e), cause=e))
        except Exception as e:
            return DeliveryResult.fail(self._name, e)
