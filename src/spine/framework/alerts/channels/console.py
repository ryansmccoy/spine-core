"""Console alert channel for development and testing."""

from __future__ import annotations

from typing import Any

from spine.framework.alerts.base import BaseChannel
from spine.framework.alerts.protocol import (
    Alert,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)


class ConsoleChannel(BaseChannel):
    """
    Console output channel for development.

    Prints alerts to stdout with formatting.
    """

    def __init__(
        self,
        name: str = "console",
        *,
        min_severity: AlertSeverity = AlertSeverity.INFO,
        color: bool = True,
        **kwargs: Any,
    ):
        super().__init__(name, ChannelType.CONSOLE, min_severity=min_severity, **kwargs)
        self._color = color

    def send(self, alert: Alert) -> DeliveryResult:
        """Print alert to console."""
        if self._color:
            colors = {
                AlertSeverity.INFO: "\033[34m",  # Blue
                AlertSeverity.WARNING: "\033[33m",  # Yellow
                AlertSeverity.ERROR: "\033[31m",  # Red
                AlertSeverity.CRITICAL: "\033[35m",  # Magenta
            }
            reset = "\033[0m"
            color = colors.get(alert.severity, "")
        else:
            color = reset = ""

        print(f"{color}[{alert.severity.value}] {alert.title}{reset}")
        print(f"  Source: {alert.source}")
        if alert.domain:
            print(f"  Domain: {alert.domain}")
        print(f"  Message: {alert.message}")
        print()

        return DeliveryResult.ok(self._name)
