"""
Alerting framework protocol and data classes.

Defines the protocol (interface) for alert channels and core data types.
Concrete implementations are in channels/ and base.py.

Design Principles:
- #4 Protocol over Inheritance: Protocol defines interface
- Separation of concerns: protocol.py has contracts, channels/ has implementations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from spine.core.errors import SpineError


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def _order(self) -> list[AlertSeverity]:
        return [
            AlertSeverity.INFO,
            AlertSeverity.WARNING,
            AlertSeverity.ERROR,
            AlertSeverity.CRITICAL,
        ]

    def __lt__(self, other: AlertSeverity) -> bool:
        return self._order().index(self) < self._order().index(other)

    def __le__(self, other: AlertSeverity) -> bool:
        return self._order().index(self) <= self._order().index(other)

    def __ge__(self, other: AlertSeverity) -> bool:
        return self._order().index(self) >= self._order().index(other)

    def __gt__(self, other: AlertSeverity) -> bool:
        return self._order().index(self) > self._order().index(other)


class ChannelType(str, Enum):
    """Alert channel types."""

    SLACK = "slack"
    EMAIL = "email"
    SERVICENOW = "servicenow"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"
    CONSOLE = "console"  # For development/testing


@dataclass
class Alert:
    """
    An alert to be sent to one or more channels.

    Contains all information needed to notify about an event.
    """

    # Required
    severity: AlertSeverity
    title: str
    message: str
    source: str  # Operation, workflow, or service name

    # Optional context
    domain: str | None = None
    execution_id: str | None = None
    run_id: str | None = None
    error: SpineError | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    # For deduplication/throttling
    fingerprint: str | None = None

    def __post_init__(self):
        # Generate fingerprint if not provided
        if self.fingerprint is None:
            parts = [self.severity.value, self.source, self.title]
            if self.domain:
                parts.append(self.domain)
            self.fingerprint = "|".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "fingerprint": self.fingerprint,
        }
        if self.domain:
            result["domain"] = self.domain
        if self.execution_id:
            result["execution_id"] = self.execution_id
        if self.run_id:
            result["run_id"] = self.run_id
        if self.error:
            result["error"] = self.error.to_dict()
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class DeliveryResult:
    """Result of alert delivery attempt."""

    channel_name: str
    success: bool
    message: str | None = None
    response: dict[str, Any] | None = None
    error: Exception | None = None
    delivered_at: datetime = field(default_factory=datetime.now)
    attempt: int = 1

    @classmethod
    def ok(cls, channel_name: str, message: str | None = None, **kwargs: Any) -> DeliveryResult:
        return cls(channel_name=channel_name, success=True, message=message, **kwargs)

    @classmethod
    def fail(cls, channel_name: str, error: Exception, attempt: int = 1) -> DeliveryResult:
        return cls(
            channel_name=channel_name,
            success=False,
            error=error,
            message=str(error),
            attempt=attempt,
        )


@runtime_checkable
class AlertChannel(Protocol):
    """
    Protocol for alert channels.

    Implementations must provide:
    - name: Unique channel identifier
    - channel_type: Type classification
    - send(): Deliver an alert
    """

    @property
    def name(self) -> str:
        """Unique channel name."""
        ...

    @property
    def channel_type(self) -> ChannelType:
        """Channel type."""
        ...

    @property
    def min_severity(self) -> AlertSeverity:
        """Minimum severity to send."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether channel is enabled."""
        ...

    def should_send(self, alert: Alert) -> bool:
        """Check if alert should be sent to this channel."""
        ...

    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert to the channel."""
        ...


__all__ = [
    # Enums
    "AlertSeverity",
    "ChannelType",
    # Data classes
    "Alert",
    "DeliveryResult",
    # Protocols
    "AlertChannel",
    # Re-exports for backward compatibility (moved to separate modules)
    # These are resolved via __getattr__ below.
    "BaseChannel",  # noqa: F822
    "ConsoleChannel",  # noqa: F822
    "SlackChannel",  # noqa: F822
    "EmailChannel",  # noqa: F822
    "WebhookChannel",  # noqa: F822
    "AlertRegistry",  # noqa: F822
    "alert_registry",  # noqa: F822
    "send_alert",  # noqa: F822
]


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
# Implementations moved to base.py, channels/, and registry.py but are
# still importable from here so existing ``from ...protocol import X`` works.
# ---------------------------------------------------------------------------
def __getattr__(name: str):
    if name == "BaseChannel":
        from spine.framework.alerts.base import BaseChannel

        return BaseChannel
    if name in ("ConsoleChannel", "SlackChannel", "EmailChannel", "WebhookChannel"):
        import spine.framework.alerts.channels as _ch

        return getattr(_ch, name)
    if name in ("AlertRegistry", "alert_registry", "send_alert"):
        from spine.framework.alerts import registry as _reg

        return getattr(_reg, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
