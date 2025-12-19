"""
Alerting framework package.

Provides a unified interface for sending alerts to various channels.
"""

from spine.framework.alerts.base import BaseChannel
from spine.framework.alerts.channels import (
    ConsoleChannel,
    EmailChannel,
    SlackChannel,
    WebhookChannel,
)
from spine.framework.alerts.protocol import (
    Alert,
    AlertChannel,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)
from spine.framework.alerts.registry import (
    AlertRegistry,
    alert_registry,
    send_alert,
)

__all__ = [
    # Enums
    "AlertSeverity",
    "ChannelType",
    # Data classes
    "Alert",
    "DeliveryResult",
    # Protocols
    "AlertChannel",
    # Base class
    "BaseChannel",
    # Implementations
    "ConsoleChannel",
    "SlackChannel",
    "EmailChannel",
    "WebhookChannel",
    # Registry
    "AlertRegistry",
    "alert_registry",
    # Functions
    "send_alert",
]
