"""
Alerting framework protocol and base implementations.

Provides a unified interface for sending alerts to:
- Slack (webhooks)
- Email (SMTP)
- ServiceNow (incidents)
- PagerDuty
- Custom webhooks

Design Principles:
- #3 Registry-Driven: Channels registered by type
- #4 Protocol over Inheritance: Protocol defines interface
- #13 Observable: Delivery tracking and metrics

Usage:
    from spine.framework.alerts import SlackChannel, alert_registry
    
    # Create and register a channel
    slack = SlackChannel(
        name="ops-alerts",
        webhook_url="https://hooks.slack.com/...",
        min_severity=AlertSeverity.ERROR,
    )
    alert_registry.register(slack)
    
    # Send an alert
    alert = Alert(
        severity=AlertSeverity.ERROR,
        title="Pipeline failed",
        message="FINRA ingestion failed due to timeout",
        source="finra_ingest",
    )
    alert_registry.send_to_all(alert)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from spine.core.errors import SpineError, TransientError


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    def _order(self) -> list[AlertSeverity]:
        return [AlertSeverity.INFO, AlertSeverity.WARNING, 
                AlertSeverity.ERROR, AlertSeverity.CRITICAL]
    
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
    source: str  # Pipeline, workflow, or service name
    
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
    def ok(cls, channel_name: str, message: str | None = None) -> DeliveryResult:
        return cls(channel_name=channel_name, success=True, message=message)
    
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


# =============================================================================
# CONSOLE CHANNEL (Development/Testing)
# =============================================================================


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
                AlertSeverity.INFO: "\033[34m",     # Blue
                AlertSeverity.WARNING: "\033[33m",  # Yellow
                AlertSeverity.ERROR: "\033[31m",    # Red
                AlertSeverity.CRITICAL: "\033[35m", # Magenta
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


# =============================================================================
# SLACK CHANNEL
# =============================================================================


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
        import urllib.request
        import urllib.error
        
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


# =============================================================================
# EMAIL CHANNEL
# =============================================================================


class EmailChannel(BaseChannel):
    """
    Email channel using SMTP.
    
    Sends alerts via email.
    """
    
    def __init__(
        self,
        name: str,
        smtp_host: str,
        from_address: str,
        recipients: list[str],
        *,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        use_tls: bool = True,
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        **kwargs: Any,
    ):
        super().__init__(name, ChannelType.EMAIL, min_severity=min_severity, **kwargs)
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_address = from_address
        self._recipients = recipients
        self._use_tls = use_tls
    
    def _build_message(self, alert: Alert) -> str:
        """Build email message."""
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{alert.severity.value}] {alert.title}"
        msg["From"] = self._from_address
        msg["To"] = ", ".join(self._recipients)
        
        # Plain text
        text = f"""
{alert.severity.value}: {alert.title}

Source: {alert.source}
Domain: {alert.domain or 'N/A'}
Time: {alert.created_at.isoformat()}

{alert.message}
"""
        if alert.error:
            text += f"\nError: {alert.error.message}"
        
        msg.attach(MIMEText(text, "plain"))
        
        return msg.as_string()
    
    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert via email."""
        import smtplib
        
        try:
            if self._use_tls:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port)
            
            if self._smtp_user and self._smtp_password:
                server.login(self._smtp_user, self._smtp_password)
            
            message = self._build_message(alert)
            server.sendmail(self._from_address, self._recipients, message)
            server.quit()
            
            return DeliveryResult.ok(self._name)
            
        except smtplib.SMTPException as e:
            return DeliveryResult.fail(self._name, TransientError(str(e), cause=e))
        except Exception as e:
            return DeliveryResult.fail(self._name, e)


# =============================================================================
# WEBHOOK CHANNEL
# =============================================================================


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
        import urllib.request
        import urllib.error
        
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


# =============================================================================
# ALERT REGISTRY
# =============================================================================


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
        return [
            name for name, channel in self._channels.items()
            if channel.channel_type == channel_type
        ]
    
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
