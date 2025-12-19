"""
Alert channel base class.

Provides common functionality for alert channel implementations:
- Severity filtering
- Domain filtering
- Enable/disable
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from spine.framework.alerts.protocol import (
    Alert,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)


class BaseChannel(ABC):
    """
    Base class for alert channel implementations.

    Provides common functionality:
    - Severity filtering
    - Domain filtering
    - Enable/disable
    """

    def __init__(
        self,
        name: str,
        channel_type: ChannelType,
        *,
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        domains: list[str] | None = None,
        enabled: bool = True,
    ):
        self._name = name
        self._channel_type = channel_type
        self._min_severity = min_severity
        self._domains = domains  # None means all domains
        self._enabled = enabled

    @property
    def name(self) -> str:
        return self._name

    @property
    def channel_type(self) -> ChannelType:
        return self._channel_type

    @property
    def min_severity(self) -> AlertSeverity:
        return self._min_severity

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """Enable the channel."""
        self._enabled = True

    def disable(self) -> None:
        """Disable the channel."""
        self._enabled = False

    def should_send(self, alert: Alert) -> bool:
        """Check if alert should be sent."""
        if not self._enabled:
            return False

        if alert.severity < self._min_severity:
            return False

        if self._domains and alert.domain:
            # Check domain filter (supports wildcards)
            matched = False
            for pattern in self._domains:
                if pattern.endswith("*"):
                    if alert.domain.startswith(pattern[:-1]):
                        matched = True
                        break
                elif pattern == alert.domain:
                    matched = True
                    break
            if not matched:
                return False

        return True

    @abstractmethod
    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert to the channel."""
        ...
