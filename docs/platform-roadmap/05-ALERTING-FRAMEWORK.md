# Alerting Framework

> **Purpose:** Send failure notifications to Slack, Email, and ServiceNow.
> **Tier:** Intermediate (Slack/Email), Advanced (ServiceNow)
> **Module:** `spine.framework.alerts`
> **Last Updated:** 2026-01-11

---

## Overview

Current state:
- No alerting capability
- Errors logged but not notified
- Manual monitoring required

Target state:
- Unified `AlertChannel` protocol
- Multiple channel implementations: Slack, Email, ServiceNow
- Severity-based routing
- Alert throttling to prevent spam
- Integration with error framework

---

## Design Principles

1. **Protocol-Based** - Easy to add new channels
2. **Registry-Driven** - Add channels without modifying code
3. **Severity-Driven** - Route by error severity
4. **Throttled** - Prevent alert fatigue
5. **Templated** - Consistent message format
6. **Async-Ready** - Non-blocking sends (future)

> **Design Principle: Write Once (#1)**
> 
> Adding a new alert channel (e.g., PagerDuty, Teams) should NOT require 
> modifying existing code. Use the `@ALERT_CHANNELS.register()` decorator.

---

## Alert Severity Levels

| Severity | Description | Channels | Example |
|----------|-------------|----------|---------|
| `CRITICAL` | System down, data loss | Slack + Email + ServiceNow | Database connection failed |
| `ERROR` | Pipeline failed | Slack + Email | Transform error |
| `WARNING` | Degraded but working | Slack | Rate limit hit |
| `INFO` | Notable event | Slack (optional) | Pipeline completed |

---

## Core Types

```python
# spine/framework/alerts/types.py
"""
Alert framework types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class Alert:
    """
    An alert to be sent to notification channels.
    
    Immutable dataclass with all alert context.
    """
    severity: AlertSeverity | str
    title: str
    message: str
    source: str  # Pipeline or component name
    execution_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # Normalize severity to enum
        if isinstance(self.severity, str):
            object.__setattr__(self, "severity", AlertSeverity(self.severity))
    
    @property
    def is_critical(self) -> bool:
        return self.severity == AlertSeverity.CRITICAL
    
    @property
    def is_error(self) -> bool:
        return self.severity in (AlertSeverity.CRITICAL, AlertSeverity.ERROR)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "execution_id": self.execution_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class AlertResult:
    """Result of sending an alert."""
    sent: bool
    channel: str
    error: str | None = None
    response: dict[str, Any] | None = None


# =============================================================================
# Alert Channel Protocol
# =============================================================================

class AlertChannel(Protocol):
    """
    Protocol for alert channels.
    
    All channels must implement send().
    """
    
    @property
    def name(self) -> str:
        """Channel name for logging."""
        ...
    
    def send(self, alert: Alert) -> AlertResult:
        """
        Send alert to channel.
        
        Returns AlertResult indicating success/failure.
        """
        ...
    
    def should_send(self, alert: Alert) -> bool:
        """
        Check if alert should be sent based on severity.
        
        Default implementation checks min_severity.
        """
        ...
```

---

## Slack Channel (Intermediate Tier)

```python
# spine/framework/alerts/slack.py
"""
Slack alert channel.

Sends alerts to Slack via webhook or Bot API.
"""

import json
import logging
from dataclasses import dataclass

import requests

from .types import Alert, AlertResult, AlertSeverity, AlertChannel


log = logging.getLogger(__name__)


@dataclass
class SlackConfig:
    """Slack channel configuration."""
    webhook_url: str
    channel: str | None = None  # Override webhook default
    username: str = "Spine Alerts"
    min_severity: AlertSeverity = AlertSeverity.WARNING
    icon_emoji: str = ":warning:"
    
    @classmethod
    def from_env(cls) -> "SlackConfig":
        """Create from environment variables."""
        import os
        return cls(
            webhook_url=os.environ["SPINE_SLACK_WEBHOOK"],
            channel=os.environ.get("SPINE_SLACK_CHANNEL"),
            min_severity=AlertSeverity(os.environ.get("SPINE_ALERT_MIN_SEVERITY", "WARNING")),
        )


class SlackChannel:
    """
    Slack alert channel using webhooks.
    
    Features:
    - Color-coded by severity
    - Rich message formatting
    - Metadata in fields
    """
    
    name = "slack"
    
    # Severity to color mapping
    COLORS = {
        AlertSeverity.CRITICAL: "#FF0000",  # Red
        AlertSeverity.ERROR: "#FFA500",     # Orange
        AlertSeverity.WARNING: "#FFFF00",   # Yellow
        AlertSeverity.INFO: "#00FF00",      # Green
    }
    
    # Severity to emoji mapping
    EMOJIS = {
        AlertSeverity.CRITICAL: ":rotating_light:",
        AlertSeverity.ERROR: ":x:",
        AlertSeverity.WARNING: ":warning:",
        AlertSeverity.INFO: ":information_source:",
    }
    
    def __init__(self, config: SlackConfig):
        self.config = config
    
    def should_send(self, alert: Alert) -> bool:
        """Check if alert meets minimum severity."""
        severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]
        alert_index = severity_order.index(alert.severity)
        min_index = severity_order.index(self.config.min_severity)
        return alert_index >= min_index
    
    def send(self, alert: Alert) -> AlertResult:
        """Send alert to Slack."""
        if not self.should_send(alert):
            return AlertResult(
                sent=False,
                channel=self.name,
                error=f"Below minimum severity {self.config.min_severity.value}",
            )
        
        payload = self._build_payload(alert)
        
        try:
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            
            log.info(f"Sent Slack alert: {alert.title}")
            return AlertResult(
                sent=True,
                channel=self.name,
                response={"status_code": response.status_code},
            )
            
        except requests.RequestException as e:
            log.error(f"Failed to send Slack alert: {e}")
            return AlertResult(
                sent=False,
                channel=self.name,
                error=str(e),
            )
    
    def _build_payload(self, alert: Alert) -> dict:
        """Build Slack message payload."""
        emoji = self.EMOJIS.get(alert.severity, ":bell:")
        color = self.COLORS.get(alert.severity, "#808080")
        
        # Build fields from metadata
        fields = [
            {
                "title": "Source",
                "value": alert.source,
                "short": True,
            },
            {
                "title": "Severity",
                "value": alert.severity.value,
                "short": True,
            },
        ]
        
        if alert.execution_id:
            fields.append({
                "title": "Execution ID",
                "value": alert.execution_id,
                "short": True,
            })
        
        # Add metadata fields
        for key, value in alert.metadata.items():
            fields.append({
                "title": key.replace("_", " ").title(),
                "value": str(value),
                "short": True,
            })
        
        payload = {
            "username": self.config.username,
            "icon_emoji": self.config.icon_emoji,
            "attachments": [
                {
                    "color": color,
                    "title": f"{emoji} {alert.title}",
                    "text": alert.message,
                    "fields": fields,
                    "footer": "Spine Platform",
                    "ts": int(alert.timestamp.timestamp()),
                }
            ],
        }
        
        if self.config.channel:
            payload["channel"] = self.config.channel
        
        return payload
```

---

## Email Channel (Intermediate Tier)

```python
# spine/framework/alerts/email.py
"""
Email alert channel.

Sends alerts via SMTP.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .types import Alert, AlertResult, AlertSeverity, AlertChannel


log = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Email channel configuration."""
    smtp_host: str
    smtp_port: int
    from_address: str
    to_addresses: list[str]
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    min_severity: AlertSeverity = AlertSeverity.ERROR
    
    @classmethod
    def from_env(cls) -> "EmailConfig":
        """Create from environment variables."""
        import os
        return cls(
            smtp_host=os.environ["SPINE_SMTP_HOST"],
            smtp_port=int(os.environ.get("SPINE_SMTP_PORT", "587")),
            from_address=os.environ["SPINE_EMAIL_FROM"],
            to_addresses=os.environ["SPINE_EMAIL_TO"].split(","),
            username=os.environ.get("SPINE_SMTP_USER"),
            password=os.environ.get("SPINE_SMTP_PASSWORD"),
            use_tls=os.environ.get("SPINE_SMTP_TLS", "true").lower() == "true",
            min_severity=AlertSeverity(os.environ.get("SPINE_ALERT_MIN_SEVERITY", "ERROR")),
        )


class EmailChannel:
    """
    Email alert channel via SMTP.
    
    Features:
    - HTML formatted emails
    - Multiple recipients
    - TLS support
    """
    
    name = "email"
    
    def __init__(self, config: EmailConfig):
        self.config = config
    
    def should_send(self, alert: Alert) -> bool:
        """Check if alert meets minimum severity."""
        severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]
        alert_index = severity_order.index(alert.severity)
        min_index = severity_order.index(self.config.min_severity)
        return alert_index >= min_index
    
    def send(self, alert: Alert) -> AlertResult:
        """Send alert via email."""
        if not self.should_send(alert):
            return AlertResult(
                sent=False,
                channel=self.name,
                error=f"Below minimum severity {self.config.min_severity.value}",
            )
        
        msg = self._build_message(alert)
        
        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()
                
                if self.config.username and self.config.password:
                    server.login(self.config.username, self.config.password)
                
                server.send_message(msg)
            
            log.info(f"Sent email alert to {len(self.config.to_addresses)} recipients")
            return AlertResult(sent=True, channel=self.name)
            
        except Exception as e:
            log.error(f"Failed to send email alert: {e}")
            return AlertResult(
                sent=False,
                channel=self.name,
                error=str(e),
            )
    
    def _build_message(self, alert: Alert) -> MIMEMultipart:
        """Build email message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{alert.severity.value}] {alert.title}"
        msg["From"] = self.config.from_address
        msg["To"] = ", ".join(self.config.to_addresses)
        
        # Plain text version
        text_content = f"""
Spine Platform Alert
---------------------

Severity: {alert.severity.value}
Title: {alert.title}
Source: {alert.source}
Time: {alert.timestamp.isoformat()}
Execution ID: {alert.execution_id or 'N/A'}

Message:
{alert.message}

Metadata:
{self._format_metadata_text(alert.metadata)}
"""
        
        # HTML version
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .header {{ background: {self._severity_color(alert.severity)}; color: white; padding: 10px; }}
        .content {{ padding: 20px; }}
        .metadata {{ background: #f5f5f5; padding: 10px; margin-top: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        td {{ padding: 5px; border-bottom: 1px solid #ddd; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>{alert.severity.value}: {alert.title}</h2>
    </div>
    <div class="content">
        <p><strong>Source:</strong> {alert.source}</p>
        <p><strong>Time:</strong> {alert.timestamp.isoformat()}</p>
        <p><strong>Execution ID:</strong> {alert.execution_id or 'N/A'}</p>
        <h3>Message</h3>
        <p>{alert.message}</p>
        <div class="metadata">
            <h4>Metadata</h4>
            {self._format_metadata_html(alert.metadata)}
        </div>
    </div>
</body>
</html>
"""
        
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))
        
        return msg
    
    def _severity_color(self, severity: AlertSeverity) -> str:
        """Get color for severity."""
        colors = {
            AlertSeverity.CRITICAL: "#dc3545",
            AlertSeverity.ERROR: "#fd7e14",
            AlertSeverity.WARNING: "#ffc107",
            AlertSeverity.INFO: "#28a745",
        }
        return colors.get(severity, "#6c757d")
    
    def _format_metadata_text(self, metadata: dict) -> str:
        """Format metadata for plain text."""
        if not metadata:
            return "None"
        return "\n".join(f"  {k}: {v}" for k, v in metadata.items())
    
    def _format_metadata_html(self, metadata: dict) -> str:
        """Format metadata as HTML table."""
        if not metadata:
            return "<p>None</p>"
        rows = "".join(f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>" for k, v in metadata.items())
        return f"<table>{rows}</table>"
```

---

## ServiceNow Channel (Advanced Tier)

```python
# spine/framework/alerts/servicenow.py
"""
ServiceNow alert channel.

Creates incidents in ServiceNow for critical alerts.
"""

import logging
from dataclasses import dataclass

import requests

from .types import Alert, AlertResult, AlertSeverity, AlertChannel


log = logging.getLogger(__name__)


@dataclass
class ServiceNowConfig:
    """ServiceNow channel configuration."""
    instance_url: str  # e.g., https://company.service-now.com
    username: str
    password: str
    assignment_group: str
    category: str = "Software"
    subcategory: str = "Pipeline"
    min_severity: AlertSeverity = AlertSeverity.CRITICAL
    
    @classmethod
    def from_env(cls) -> "ServiceNowConfig":
        """Create from environment variables."""
        import os
        return cls(
            instance_url=os.environ["SPINE_SNOW_URL"],
            username=os.environ["SPINE_SNOW_USER"],
            password=os.environ["SPINE_SNOW_PASSWORD"],
            assignment_group=os.environ["SPINE_SNOW_ASSIGNMENT_GROUP"],
            category=os.environ.get("SPINE_SNOW_CATEGORY", "Software"),
            subcategory=os.environ.get("SPINE_SNOW_SUBCATEGORY", "Pipeline"),
        )


class ServiceNowChannel:
    """
    ServiceNow incident channel.
    
    Features:
    - Creates incidents via Table API
    - Maps severity to impact/urgency
    - Includes full metadata in description
    """
    
    name = "servicenow"
    
    # Map severity to ServiceNow impact (1=High, 2=Medium, 3=Low)
    IMPACT_MAP = {
        AlertSeverity.CRITICAL: "1",
        AlertSeverity.ERROR: "2",
        AlertSeverity.WARNING: "3",
        AlertSeverity.INFO: "3",
    }
    
    # Map severity to ServiceNow urgency (1=High, 2=Medium, 3=Low)
    URGENCY_MAP = {
        AlertSeverity.CRITICAL: "1",
        AlertSeverity.ERROR: "2",
        AlertSeverity.WARNING: "3",
        AlertSeverity.INFO: "3",
    }
    
    def __init__(self, config: ServiceNowConfig):
        self.config = config
    
    def should_send(self, alert: Alert) -> bool:
        """Only create incidents for critical/error alerts."""
        severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]
        alert_index = severity_order.index(alert.severity)
        min_index = severity_order.index(self.config.min_severity)
        return alert_index >= min_index
    
    def send(self, alert: Alert) -> AlertResult:
        """Create ServiceNow incident."""
        if not self.should_send(alert):
            return AlertResult(
                sent=False,
                channel=self.name,
                error=f"Below minimum severity {self.config.min_severity.value}",
            )
        
        payload = self._build_incident(alert)
        url = f"{self.config.instance_url}/api/now/table/incident"
        
        try:
            response = requests.post(
                url,
                json=payload,
                auth=(self.config.username, self.config.password),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            incident_number = result.get("result", {}).get("number", "unknown")
            
            log.info(f"Created ServiceNow incident: {incident_number}")
            return AlertResult(
                sent=True,
                channel=self.name,
                response={"incident_number": incident_number},
            )
            
        except requests.RequestException as e:
            log.error(f"Failed to create ServiceNow incident: {e}")
            return AlertResult(
                sent=False,
                channel=self.name,
                error=str(e),
            )
    
    def _build_incident(self, alert: Alert) -> dict:
        """Build ServiceNow incident payload."""
        description = f"""
Pipeline Alert: {alert.title}

Source: {alert.source}
Execution ID: {alert.execution_id or 'N/A'}
Timestamp: {alert.timestamp.isoformat()}

Message:
{alert.message}

Metadata:
{self._format_metadata(alert.metadata)}
"""
        
        return {
            "short_description": f"[{alert.severity.value}] {alert.title}",
            "description": description,
            "impact": self.IMPACT_MAP.get(alert.severity, "2"),
            "urgency": self.URGENCY_MAP.get(alert.severity, "2"),
            "assignment_group": self.config.assignment_group,
            "category": self.config.category,
            "subcategory": self.config.subcategory,
            "caller_id": "Spine Platform",
        }
    
    def _format_metadata(self, metadata: dict) -> str:
        """Format metadata for description."""
        if not metadata:
            return "None"
        return "\n".join(f"  {k}: {v}" for k, v in metadata.items())
```

---

## Channel Registry

> **Design Principle: Registry-Driven (#3)**
> 
> Adding a new channel (e.g., PagerDuty, Microsoft Teams) should NOT require
> modifying existing code. Register channels with `@ALERT_CHANNELS.register()`.

```python
# spine/framework/alerts/registry.py
"""
Alert channel registry.

Enables adding new channels without modifying existing code.
"""

from typing import Callable, TypeVar
from .types import AlertChannel


T = TypeVar("T", bound=AlertChannel)


class ChannelRegistry:
    """
    Registry for alert channels.
    
    Channels register by name. Third parties can add new channels
    without modifying this module.
    """
    
    def __init__(self):
        self._channels: dict[str, type[AlertChannel]] = {}
    
    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        """
        Register channel by name.
        
        Usage:
            @ALERT_CHANNELS.register("slack")
            class SlackChannel:
                ...
                
            @ALERT_CHANNELS.register("pagerduty")
            class PagerDutyChannel:
                ...
        """
        def decorator(cls: type[T]) -> type[T]:
            self._channels[name] = cls
            return cls
        return decorator
    
    def get(self, name: str, **config) -> AlertChannel:
        """Get channel instance by name."""
        if name not in self._channels:
            raise KeyError(f"Unknown alert channel: {name}. Available: {self.list()}")
        return self._channels[name](**config)
    
    def list(self) -> list[str]:
        """List registered channel names."""
        return list(self._channels.keys())
    
    def create_all(self, configs: dict[str, dict]) -> list[AlertChannel]:
        """
        Create all configured channels.
        
        Args:
            configs: Dict mapping channel name to config kwargs
                     e.g., {"slack": {"webhook_url": "..."}, "email": {"smtp_host": "..."}}
        
        Returns:
            List of channel instances
        """
        channels = []
        for name, config in configs.items():
            if name in self._channels:
                channels.append(self.get(name, **config))
        return channels


# Global registry instance
ALERT_CHANNELS = ChannelRegistry()


# Register built-in channels
# spine/framework/alerts/slack.py
@ALERT_CHANNELS.register("slack")
class SlackChannel:
    """Slack via webhook - registered automatically."""
    name = "slack"
    # ... implementation


# spine/framework/alerts/email.py
@ALERT_CHANNELS.register("email")
class EmailChannel:
    """Email via SMTP - registered automatically."""
    name = "email"
    # ... implementation


# spine/framework/alerts/servicenow.py
@ALERT_CHANNELS.register("servicenow")
class ServiceNowChannel:
    """ServiceNow incidents - registered automatically."""
    name = "servicenow"
    # ... implementation
```

```python
# Adding a New Channel (Third-Party):
# my_company/alerts/pagerduty.py
from spine.framework.alerts import ALERT_CHANNELS, AlertChannel

@ALERT_CHANNELS.register("pagerduty")
class PagerDutyChannel:
    """PagerDuty integration - added by third party."""
    name = "pagerduty"
    
    def __init__(self, routing_key: str, min_severity: str = "ERROR"):
        self.routing_key = routing_key
        self.min_severity = min_severity
    
    def send(self, alert: Alert) -> AlertResult:
        # ... implementation
        pass

# Now it just works:
channel = ALERT_CHANNELS.get("pagerduty", routing_key="R012ABC...")
print(ALERT_CHANNELS.list())  # ['slack', 'email', 'servicenow', 'pagerduty']
```

---

## Alert Router

```python
# spine/framework/alerts/router.py
"""
Alert router - routes alerts to appropriate channels.
"""

import logging
from typing import Any

from .types import Alert, AlertResult, AlertSeverity, AlertChannel
from spine.core.errors import SpineError, ErrorCategory


log = logging.getLogger(__name__)


class AlertRouter:
    """
    Routes alerts to appropriate channels based on severity.
    
    Features:
    - Multiple channels per severity
    - Throttling to prevent spam
    - Error category routing
    """
    
    def __init__(self):
        self._channels: list[AlertChannel] = []
        self._severity_channels: dict[AlertSeverity, list[AlertChannel]] = {}
        self._category_channels: dict[ErrorCategory, list[AlertChannel]] = {}
    
    def add_channel(self, channel: AlertChannel) -> None:
        """Add channel to router."""
        self._channels.append(channel)
    
    def add_severity_channel(
        self,
        severity: AlertSeverity,
        channel: AlertChannel,
    ) -> None:
        """Add channel for specific severity."""
        if severity not in self._severity_channels:
            self._severity_channels[severity] = []
        self._severity_channels[severity].append(channel)
    
    def add_category_channel(
        self,
        category: ErrorCategory,
        channel: AlertChannel,
    ) -> None:
        """Add channel for specific error category."""
        if category not in self._category_channels:
            self._category_channels[category] = []
        self._category_channels[category].append(channel)
    
    def send(self, alert: Alert) -> list[AlertResult]:
        """Send alert to all applicable channels."""
        results = []
        
        # Get channels for this severity
        channels = set(self._channels)
        if alert.severity in self._severity_channels:
            channels.update(self._severity_channels[alert.severity])
        
        for channel in channels:
            if channel.should_send(alert):
                result = channel.send(alert)
                results.append(result)
        
        return results
    
    def send_error(self, error: SpineError) -> list[AlertResult]:
        """Send alert from SpineError."""
        alert = Alert(
            severity=self._category_to_severity(error.category),
            title=f"Pipeline Error: {error.category.value}",
            message=error.message,
            source=error.context.pipeline or "unknown",
            execution_id=error.context.execution_id,
            metadata={
                "category": error.category.value,
                "retryable": error.retryable,
                **error.context.metadata,
            },
        )
        
        results = self.send(alert)
        
        # Also send to category-specific channels
        if error.category in self._category_channels:
            for channel in self._category_channels[error.category]:
                if channel.should_send(alert):
                    results.append(channel.send(alert))
        
        return results
    
    def _category_to_severity(self, category: ErrorCategory) -> AlertSeverity:
        """Map error category to alert severity."""
        severity_map = {
            ErrorCategory.INTERNAL: AlertSeverity.CRITICAL,
            ErrorCategory.CONFIGURATION: AlertSeverity.ERROR,
            ErrorCategory.VALIDATION: AlertSeverity.WARNING,
            ErrorCategory.SOURCE: AlertSeverity.ERROR,
            ErrorCategory.TRANSFORM: AlertSeverity.ERROR,
            ErrorCategory.LOAD: AlertSeverity.ERROR,
            ErrorCategory.TRANSIENT: AlertSeverity.WARNING,
            ErrorCategory.DEPENDENCY: AlertSeverity.ERROR,
            ErrorCategory.TIMEOUT: AlertSeverity.WARNING,
            ErrorCategory.RATE_LIMIT: AlertSeverity.INFO,
            ErrorCategory.PERMISSION: AlertSeverity.ERROR,
            ErrorCategory.RESOURCE: AlertSeverity.CRITICAL,
        }
        return severity_map.get(category, AlertSeverity.ERROR)
```

---

## Alert Throttling

```python
# spine/framework/alerts/throttle.py
"""
Alert throttling to prevent spam.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from .types import Alert, AlertResult, AlertChannel


@dataclass
class ThrottleState:
    """State for throttle tracking."""
    last_sent: float = 0.0
    count: int = 0
    suppressed: int = 0


class ThrottledChannel:
    """
    Wrapper that throttles alerts.
    
    Features:
    - Rate limiting by source
    - Aggregation of repeated alerts
    - Configurable window
    """
    
    def __init__(
        self,
        channel: AlertChannel,
        window_seconds: int = 300,  # 5 minutes
        max_per_window: int = 5,
    ):
        self.channel = channel
        self.window_seconds = window_seconds
        self.max_per_window = max_per_window
        self._state: dict[str, ThrottleState] = {}
    
    @property
    def name(self) -> str:
        return f"throttled:{self.channel.name}"
    
    def should_send(self, alert: Alert) -> bool:
        """Check channel's should_send."""
        return self.channel.should_send(alert)
    
    def send(self, alert: Alert) -> AlertResult:
        """Send alert with throttling."""
        key = f"{alert.source}:{alert.severity.value}"
        now = time.time()
        
        if key not in self._state:
            self._state[key] = ThrottleState()
        
        state = self._state[key]
        
        # Reset if outside window
        if now - state.last_sent > self.window_seconds:
            state.count = 0
            state.suppressed = 0
        
        # Check if throttled
        if state.count >= self.max_per_window:
            state.suppressed += 1
            return AlertResult(
                sent=False,
                channel=self.name,
                error=f"Throttled ({state.suppressed} suppressed)",
            )
        
        # Send alert
        result = self.channel.send(alert)
        
        if result.sent:
            state.count += 1
            state.last_sent = now
        
        return result
```

---

## Usage Examples

### Basic Setup

```python
from spine.framework.alerts import (
    AlertRouter,
    SlackChannel,
    SlackConfig,
    EmailChannel,
    EmailConfig,
    ThrottledChannel,
)

# Create channels
slack = SlackChannel(SlackConfig.from_env())
email = EmailChannel(EmailConfig.from_env())

# Add throttling
throttled_slack = ThrottledChannel(slack, window_seconds=300, max_per_window=10)

# Setup router
router = AlertRouter()
router.add_channel(throttled_slack)
router.add_channel(email)
```

### In Pipeline

```python
from spine.core.errors import SpineError, TransientError
from spine.framework.alerts import Alert, AlertSeverity

class IngestPipeline(Pipeline):
    def __init__(self, alert_router: AlertRouter):
        self.alerts = alert_router
    
    def run(self) -> PipelineResult:
        try:
            # ... pipeline logic ...
            
            # Send success alert (optional)
            self.alerts.send(Alert(
                severity=AlertSeverity.INFO,
                title="Pipeline Completed",
                message=f"Processed {count} records",
                source=self.name,
                execution_id=self.execution_id,
            ))
            
            return PipelineResult.completed()
            
        except SpineError as e:
            # Send error alert
            self.alerts.send_error(e)
            raise
```

### Module Exports

```python
# spine/framework/alerts/__init__.py
"""
Alerting framework.

Usage:
    from spine.framework.alerts import (
        Alert,
        AlertSeverity,
        AlertRouter,
        SlackChannel,
        EmailChannel,
    )
"""

from .types import Alert, AlertResult, AlertSeverity, AlertChannel
from .slack import SlackChannel, SlackConfig
from .email import EmailChannel, EmailConfig
from .servicenow import ServiceNowChannel, ServiceNowConfig
from .router import AlertRouter
from .throttle import ThrottledChannel

__all__ = [
    "Alert",
    "AlertResult",
    "AlertSeverity",
    "AlertChannel",
    "SlackChannel",
    "SlackConfig",
    "EmailChannel",
    "EmailConfig",
    "ServiceNowChannel",
    "ServiceNowConfig",
    "AlertRouter",
    "ThrottledChannel",
]
```

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SPINE_SLACK_WEBHOOK` | Slack incoming webhook URL | For Slack |
| `SPINE_SLACK_CHANNEL` | Override channel | No |
| `SPINE_SMTP_HOST` | SMTP server hostname | For Email |
| `SPINE_SMTP_PORT` | SMTP port (default 587) | No |
| `SPINE_EMAIL_FROM` | From address | For Email |
| `SPINE_EMAIL_TO` | Comma-separated recipients | For Email |
| `SPINE_SMTP_USER` | SMTP username | No |
| `SPINE_SMTP_PASSWORD` | SMTP password | No |
| `SPINE_SNOW_URL` | ServiceNow instance URL | For SNOW |
| `SPINE_SNOW_USER` | ServiceNow username | For SNOW |
| `SPINE_SNOW_PASSWORD` | ServiceNow password | For SNOW |
| `SPINE_SNOW_ASSIGNMENT_GROUP` | Assignment group | For SNOW |
| `SPINE_ALERT_MIN_SEVERITY` | Minimum severity (default WARNING) | No |

---

## Testing

```python
# tests/framework/alerts/test_router.py
import pytest
from spine.framework.alerts import (
    Alert,
    AlertSeverity,
    AlertRouter,
    AlertResult,
)


class MockChannel:
    def __init__(self, name: str, min_severity: AlertSeverity = AlertSeverity.INFO):
        self.name = name
        self.min_severity = min_severity
        self.sent_alerts: list[Alert] = []
    
    def should_send(self, alert: Alert) -> bool:
        severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]
        return severity_order.index(alert.severity) >= severity_order.index(self.min_severity)
    
    def send(self, alert: Alert) -> AlertResult:
        self.sent_alerts.append(alert)
        return AlertResult(sent=True, channel=self.name)


class TestAlertRouter:
    def test_send_to_all_channels(self):
        slack = MockChannel("slack")
        email = MockChannel("email")
        
        router = AlertRouter()
        router.add_channel(slack)
        router.add_channel(email)
        
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test",
            message="Test message",
            source="test",
        )
        
        results = router.send(alert)
        
        assert len(results) == 2
        assert all(r.sent for r in results)
        assert len(slack.sent_alerts) == 1
        assert len(email.sent_alerts) == 1
    
    def test_severity_filtering(self):
        info_channel = MockChannel("info", AlertSeverity.INFO)
        error_channel = MockChannel("error", AlertSeverity.ERROR)
        
        router = AlertRouter()
        router.add_channel(info_channel)
        router.add_channel(error_channel)
        
        warning_alert = Alert(
            severity=AlertSeverity.WARNING,
            title="Warning",
            message="Warning message",
            source="test",
        )
        
        results = router.send(warning_alert)
        
        # Only info channel should send (WARNING >= INFO)
        assert len(info_channel.sent_alerts) == 1
        assert len(error_channel.sent_alerts) == 0
```

---

## Next Steps

1. Create scheduler service: [06-SCHEDULER-SERVICE.md](./06-SCHEDULER-SERVICE.md)
2. Build workflow history: [07-WORKFLOW-HISTORY.md](./07-WORKFLOW-HISTORY.md)
3. Document integration flow: [09-INTEGRATION-FLOW.md](./09-INTEGRATION-FLOW.md)
