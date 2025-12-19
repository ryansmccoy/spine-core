"""Alert registry for managing and routing alerts to channels."""

from __future__ import annotations

from typing import Any

from spine.framework.alerts.protocol import (
    Alert,
    AlertChannel,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)


class AlertRegistry:
    """
    Registry for alert channels.

    Design Principle #3: Registry-Driven Discovery

    Supports:
    - Multiple channels per type
    - Filtering by severity and domain
    - Bulk sending to all matching channels
    """

    def __init__(self):
        self._channels: dict[str, AlertChannel] = {}

    def register(self, channel: AlertChannel) -> None:
        """Register an alert channel."""
        self._channels[channel.name] = channel

    def unregister(self, name: str) -> None:
        """Unregister a channel by name."""
        self._channels.pop(name, None)

    def get(self, name: str) -> AlertChannel | None:
        """Get a channel by name."""
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        """List all registered channel names."""
        return sorted(self._channels.keys())

    def list_by_type(self, channel_type: ChannelType) -> list[str]:
        """List channels of a specific type."""
        return [name for name, channel in self._channels.items() if channel.channel_type == channel_type]

    def send(self, alert: Alert, channel_name: str) -> DeliveryResult:
        """Send alert to a specific channel."""
        channel = self._channels.get(channel_name)
        if not channel:
            return DeliveryResult.fail(
                channel_name,
                ValueError(f"Channel not found: {channel_name}"),
            )

        if not channel.should_send(alert):
            return DeliveryResult(
                channel_name=channel_name,
                success=True,
                message="Filtered (severity/domain)",
            )

        return channel.send(alert)

    def send_to_all(self, alert: Alert) -> list[DeliveryResult]:
        """Send alert to all matching channels."""
        results = []
        for channel in self._channels.values():
            if channel.should_send(alert):
                results.append(channel.send(alert))
        return results

    def send_to_type(
        self,
        alert: Alert,
        channel_type: ChannelType,
    ) -> list[DeliveryResult]:
        """Send alert to all channels of a specific type."""
        results = []
        for channel in self._channels.values():
            if channel.channel_type == channel_type and channel.should_send(alert):
                results.append(channel.send(alert))
        return results


# Global registry
alert_registry = AlertRegistry()


def send_alert(
    severity: AlertSeverity,
    title: str,
    message: str,
    source: str,
    **kwargs: Any,
) -> list[DeliveryResult]:
    """
    Convenience function to send an alert to all channels.

    Usage:
        send_alert(
            AlertSeverity.ERROR,
            "Pipeline failed",
            "FINRA ingestion timed out",
            source="finra_ingest",
            domain="finra",
        )
    """
    alert = Alert(
        severity=severity,
        title=title,
        message=message,
        source=source,
        **kwargs,
    )
    return alert_registry.send_to_all(alert)
